"""
API Views for the Resume Parser & Standardization Agent.

Provides REST endpoints for:
- Resume upload and processing
- Processing status tracking
- Extracted data retrieval
- Standardized resume download
- Processing logs and audit
"""
import base64
import os
import logging
from datetime import datetime
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import status, viewsets, generics
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from .models import ResumeRecord, ProcessingLog, ExtractionField
from .serializers import (
    ResumeRecordSerializer,
    ResumeRecordListSerializer,
    ResumeUploadSerializer,
    ProcessingLogSerializer,
    ProcessingStatusSerializer,
    StandardizedResumeResponseSerializer,
    ExtractedDataSerializer,
)
from .services.validator import FileValidator
from .services.parser import ResumeParser
from .services.extractor import ResumeExtractor
from .services.standardizer import ResumeStandardizer
from .services.excel_storage import ExcelStorageClient

logger = logging.getLogger("api")

def _log(record, level, step, message, details=None):
    """Persist a processing-log entry to the DB and Excel (best-effort)."""
    ProcessingLog.objects.create(
        resume_record=record,
        level=level,
        step=step,
        message=message,
        details=details or {},
    )
    try:
        ExcelStorageClient().append_log(
            level=level,
            step=step,
            message=message,
            record_id=str(record.id) if record else "",
            candidate_id=str(record.candidate_id or "") if record else "",
            original_file_name=str(record.original_file_name or "") if record else "",
            details=details or {},
        )
    except Exception as exc:
        logger.warning("Could not write log to Excel: %s", exc)


def _run_pipeline(record, uploaded_file, source):

    try:
        # Step 1: Validate
        record.status = ResumeRecord.Status.VALIDATING
        record.save()
        _log(record, "info", "validation", "Starting file validation")

        validator = FileValidator()
        validation_result = validator.validate(uploaded_file)

        if not validation_result["valid"]:
            error_msg = "; ".join(validation_result["errors"])
            record.status = ResumeRecord.Status.FAILED
            record.error_message = error_msg
            record.save()
            _log(record, "error", "validation", error_msg)
            # Read first bytes for diagnostic info
            try:
                uploaded_file.seek(0)
                first_bytes = uploaded_file.read(16)
                uploaded_file.seek(0)
                first_hex = first_bytes.hex()
                first_ascii = first_bytes.decode("ascii", errors="replace")
            except Exception:
                first_hex, first_ascii = "unavailable", "unavailable"
            return Response(
                {
                    "error": error_msg,
                    "record_id": str(record.id),
                    "debug_first_16_hex": first_hex,
                    "debug_first_16_ascii": first_ascii,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_path = validator.save_uploaded_file(uploaded_file)
        record.file_path = file_path
        record.save()
        _log(record, "info", "validation", "File validated and saved successfully")

        # Step 2: Parse / Extract text
        record.status = ResumeRecord.Status.EXTRACTING
        record.save()
        _log(record, "info", "parsing", "Starting text extraction")

        parser = ResumeParser()
        parse_result = parser.parse(
            file_path,
            validation_result["file_type"],
            validation_result["needs_ocr"],
        )

        if not parse_result["success"]:
            error_msg = parse_result.get("error", "Text extraction failed")
            record.status = ResumeRecord.Status.FAILED
            record.error_message = error_msg
            record.save()
            _log(record, "error", "parsing", error_msg)
            return Response(
                {"error": error_msg, "record_id": str(record.id)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        _log(
            record, "info", "parsing",
            f"Text extracted: {len(parse_result['text'])} chars, "
            f"{parse_result['pages']} pages, method: {parse_result['method']}",
        )

        # Step 3: Extract structured data
        _log(record, "info", "extraction", "Starting AI-powered data extraction")

        extractor = ResumeExtractor()
        extracted_data = extractor.extract(parse_result["text"])
        extracted_data["resume_source"] = str(source)
        extracted_data["original_file_name"] = uploaded_file.name

        # Guard: warn if all core fields came back empty
        core_fields = (
            "candidate_full_name", "email_ids", "phones",
            "key_skills", "work_experience", "education",
        )
        if not any(bool(extracted_data.get(f)) for f in core_fields):
            logger.warning(
                "All core fields empty after extraction for '%s'. "
                "The resume text may not have been readable.",
                uploaded_file.name,
            )
            _log(
                record, "warning", "extraction",
                "Extraction returned empty for all core fields. "
                "The uploaded file may be image-only, encrypted, or corrupt.",
            )

        confidence = extractor.calculate_overall_confidence(extracted_data)
        candidate_id = extracted_data.get("candidate_id", "")

        # If another record already exists for this candidate, merge into it
        # to avoid a UNIQUE constraint violation on candidate_id.
        if candidate_id:
            existing = ResumeRecord.objects.filter(
                candidate_id=candidate_id
            ).exclude(pk=record.pk).first()
            if existing:
                ProcessingLog.objects.filter(resume_record=record).update(
                    resume_record=existing
                )
                record.delete()
                record = existing
                record.file_path = file_path
                record.original_file_name = uploaded_file.name
                record.file_size_bytes = uploaded_file.size
                record.file_type = os.path.splitext(uploaded_file.name)[1].lower()

        record.extracted_data = extracted_data
        record.extraction_confidence = confidence
        record.candidate_id = candidate_id
        record.save()

        for field_name, field_conf in extracted_data.get("field_confidences", {}).items():
            ExtractionField.objects.update_or_create(
                resume_record=record,
                field_name=field_name,
                defaults={
                    "field_value": str(extracted_data.get(field_name, ""))[:500],
                    "confidence": field_conf,
                    "is_missing": field_conf < 0.3,
                },
            )

        _log(
            record, "info", "extraction",
            f"Data extracted. Confidence: {confidence:.2f}. "
            f"Candidate: {extracted_data.get('candidate_full_name', 'Unknown')}",
        )

        # Step 4: Store in Excel
        record.status = ResumeRecord.Status.STORING
        record.save()
        _log(record, "info", "storage", "Saving to Excel")

        excel_client = ExcelStorageClient()
        extracted_data["file_path"] = file_path
        xl_result = excel_client.upsert_record(extracted_data)
        record.dataverse_record_id = xl_result.get("id") or ""
        record.version = xl_result.get("version") or record.version
        _log(
            record, "info", "storage",
            f"Excel {xl_result.get('action', 'saved')}: "
            f"row {xl_result.get('row', 'N/A')}, version {xl_result.get('version', 1)}",
        )

        # Step 5: Generate standardized resume
        record.status = ResumeRecord.Status.STANDARDIZING
        record.save()
        _log(record, "info", "standardization", "Generating standardized resume")

        standardizer = ResumeStandardizer()
        try:
            output_path = standardizer.generate_docx(extracted_data)
            record.standardized_file_path = output_path
        except Exception as exc:
            logger.warning("DOCX generation failed: %s", exc)
            _log(record, "warning", "standardization", f"DOCX generation failed: {exc}")

        # Step 6: Complete
        record.status = ResumeRecord.Status.COMPLETED
        record.processed_at = timezone.now()
        record.save()
        _log(record, "info", "complete", "Resume processing completed successfully")

        result_serializer = ResumeRecordSerializer(record)
        resp_status = (
            status.HTTP_200_OK if (record.version or 1) > 1 else status.HTTP_201_CREATED
        )
        return Response(result_serializer.data, status=resp_status)

    except Exception as exc:
        logger.error("Pipeline processing error: %s", exc)
        record.status = ResumeRecord.Status.FAILED
        record.error_message = str(exc)
        record.save()
        _log(record, "error", "processing", f"Unexpected error: {exc}")
        return Response(
            {"error": f"Processing failed: {exc}", "record_id": str(record.id)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )



class ResumeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Resume Records.

    Provides list, retrieve, and upload functionality for resume processing.
    """

    queryset = ResumeRecord.objects.all()
    serializer_class = ResumeRecordSerializer
    parser_classes = [MultiPartParser, FormParser]

    def get_serializer_class(self) -> type:
        if self.action == "list":
            return ResumeRecordListSerializer
        return ResumeRecordSerializer

    @swagger_auto_schema(
        operation_description=(
            "List all processed resume records with pagination and filtering."
        ),
        manual_parameters=[
            openapi.Parameter(
                "status",
                openapi.IN_QUERY,
                description="Filter by processing status",
                type=openapi.TYPE_STRING,
                enum=["pending", "validating", "extracting", "storing", "standardizing", "completed", "failed"],
            ),
            openapi.Parameter(
                "source",
                openapi.IN_QUERY,
                description="Filter by resume source",
                type=openapi.TYPE_STRING,
                enum=["upload", "email"],
            ),
        ],
        responses={200: ResumeRecordListSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        # Apply filters
        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        source_filter = request.query_params.get("source")
        if source_filter:
            queryset = queryset.filter(resume_source=source_filter)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @swagger_auto_schema(
        operation_description="Retrieve detailed information about a specific resume record.",
        responses={200: ResumeRecordSerializer()},
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_description=(
            "Upload a resume file for processing.\n\n"
            "Supported formats: .pdf, .docx, .doc, .rtf, .txt, .png, .jpg\n"
            "Maximum file size: 10 MB\n\n"
            "The processing pipeline:\n"
            "1. Validate file type, size, and readability\n"
            "2. Extract text (OCR for images/scanned PDFs)\n"
            "3. Parse and extract structured fields using AI\n"
            "4. Store data in Excel\n"
            "5. Generate standardized resume document\n"
        ),
        request_body=ResumeUploadSerializer,
        responses={
            201: ResumeRecordSerializer(),
            400: "Validation error",
            500: "Processing error",
        },
        consumes=["multipart/form-data"],
    )
    def create(self, request, *args, **kwargs):
        """Upload and process a resume file."""
        serializer = ResumeUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated: dict = serializer.validated_data  # type: ignore[assignment]
        uploaded_file = validated["file"]
        source = validated.get("source", ResumeRecord.Source.UPLOAD)

        #find duplicate by file name to support re-uploads without creating new records each time
        existing_by_name = (
            ResumeRecord.objects.filter(original_file_name=uploaded_file.name)
            .order_by("-created_at")
            .first()
        )

        if existing_by_name:
            record = existing_by_name
            record.previous_version_id = record.id
            record.version = (record.version or 1) + 1
            record.file_type = os.path.splitext(uploaded_file.name)[1].lower()
            record.file_size_bytes = uploaded_file.size
            record.resume_source = source
            record.status = ResumeRecord.Status.PENDING
            record.error_message = ""
            record.extracted_data = {}
            record.extraction_confidence = 0.0
            record.dataverse_record_id = ""
            record.standardized_file_path = ""
            record.processed_at = None
            record.save()
            _log(
                record, "info", "ingestion",
                f"Re-upload detected for '{uploaded_file.name}' — updating existing record "
                f"(version {record.version})",
            )
        else:
            record = ResumeRecord.objects.create(
                original_file_name=uploaded_file.name,
                file_type=os.path.splitext(uploaded_file.name)[1].lower(),
                file_size_bytes=uploaded_file.size,
                resume_source=source,
                status=ResumeRecord.Status.PENDING,
            )
            _log(record, "info", "ingestion", f"Resume received: {uploaded_file.name}")

        return _run_pipeline(record, uploaded_file, source)

    @swagger_auto_schema(
        method="get",
        operation_description="Check the processing status of a resume.",
        responses={200: ProcessingStatusSerializer()},
    )
    @action(detail=True, methods=["get"])
    def status_check(self, request, pk=None):
        """Check processing status of a resume."""
        record = self.get_object()
        return Response({
            "id": str(record.id),
            "status": record.status,
            "progress_message": self._get_progress_message(record.status),
            "extraction_confidence": record.extraction_confidence,
            "error_message": record.error_message,
        })

    @swagger_auto_schema(
        method="get",
        operation_description="Download the standardized resume document.",
        responses={
            200: openapi.Response(
                description="Standardized resume file",
                schema=openapi.Schema(type=openapi.TYPE_FILE),
            ),
            404: "File not found or not yet generated",
        },
    )
    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """Download standardized resume."""
        record = self.get_object()

        if not record.standardized_file_path or not os.path.exists(
            record.standardized_file_path
        ):
            raise Http404("Standardized resume not available. Processing may still be in progress.")

        return FileResponse(
            open(record.standardized_file_path, "rb"),
            as_attachment=True,
            filename=os.path.basename(record.standardized_file_path),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    @swagger_auto_schema(
        method="get",
        operation_description="Get the extracted data for a resume record.",
        responses={200: ExtractedDataSerializer()},
    )
    @action(detail=True, methods=["get"])
    def extracted_data(self, request, pk=None):
        """Get extracted structured data."""
        record = self.get_object()
        return Response(record.extracted_data)

    @swagger_auto_schema(
        method="get",
        operation_description="Get the standardized resume as plain text (for chat/preview).",
        responses={200: openapi.Response(description="Plain text resume")},
    )
    @action(detail=True, methods=["get"])
    def text_preview(self, request, pk=None):
        """Get standardized resume as text."""
        record = self.get_object()
        if not record.extracted_data:
            return Response(
                {"error": "No extracted data available"},
                status=status.HTTP_404_NOT_FOUND,
            )
        standardizer = ResumeStandardizer()
        text = standardizer.generate_text_output(record.extracted_data)
        return Response({"text": text})

    @swagger_auto_schema(
        method="get",
        operation_description="Get processing logs for a resume record.",
        responses={200: ProcessingLogSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def logs(self, request, pk=None):
        """Get processing logs for a resume."""
        record = self.get_object()
        logs = ProcessingLog.objects.filter(resume_record=record)
        serializer = ProcessingLogSerializer(logs, many=True)
        return Response(serializer.data)

    @swagger_auto_schema(
        method="get",
        operation_description=(
            "Get per-field confidence scores for a resume record.\n\n"
            "Each field includes:\n"
            "- confidence: float (0.0–1.0)\n"
            "- is_missing: true if confidence < 0.3\n"
            "- field_value: extracted value (truncated)"
        ),
        responses={200: openapi.Response(description="Per-field confidence map")},
    )
    @action(detail=True, methods=["get"])
    def field_confidences(self, request, pk=None):
        """Get per-field extraction confidence scores and quality warnings."""
        record = self.get_object()
        fields = ExtractionField.objects.filter(resume_record=record)
        if fields.exists():
            data = {
                f.field_name: {
                    "confidence": f.confidence,
                    "is_missing": f.is_missing,
                    "field_value": f.field_value[:200],
                }
                for f in fields
            }
        else:
            # Fallback to extracted_data blob
            raw = record.extracted_data or {}
            fc = raw.get("field_confidences", {})
            data = {
                k: {"confidence": v, "is_missing": v < 0.3, "field_value": ""}
                for k, v in fc.items()
            }

        # Attach any quality-issue warnings (cross-contamination, wrong field type, etc.)
        quality_notes = (record.extracted_data or {}).get("field_quality_notes", {})
        for field_name, note in quality_notes.items():
            if field_name in data:
                data[field_name]["quality_warning"] = note

        return Response(data)

    def _get_progress_message(self, current_status):
        """Get a user-friendly progress message."""
        messages = {
            ResumeRecord.Status.PENDING: "Resume received. Waiting to process...",
            ResumeRecord.Status.VALIDATING: "Validating file format and content...",
            ResumeRecord.Status.EXTRACTING: "Extracting information from resume...",
            ResumeRecord.Status.STORING: "Saving extracted data...",
            ResumeRecord.Status.STANDARDIZING: "Generating standardized resume...",
            ResumeRecord.Status.COMPLETED: "Processing complete! Resume is ready.",
            ResumeRecord.Status.FAILED: "Processing failed. Please check error details.",
        }
        return messages.get(current_status, "Processing...")


@swagger_auto_schema(
    method="get",
    operation_description="Health check endpoint. Returns API status.",
    responses={
        200: openapi.Response(
            description="API is healthy",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "status": openapi.Schema(type=openapi.TYPE_STRING),
                    "version": openapi.Schema(type=openapi.TYPE_STRING),
                    "excel_storage_configured": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    "openai_configured": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                },
            ),
        )
    },
)
@api_view(["GET"])
def health_check(request):
    """API health check endpoint."""
    excel_client = ExcelStorageClient()
    return Response({
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": timezone.now().isoformat(),
        "excel_storage_configured": excel_client.is_configured,
        "excel_path": excel_client.excel_path,
        "openai_configured": bool(settings.OPENAI_API_KEY),
        "supported_formats": settings.SUPPORTED_FILE_TYPES,
        "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
    })


@swagger_auto_schema(
    method="get",
    operation_description="Get the Excel storage schema / data dictionary.",
    responses={200: openapi.Response(description="Schema definition")},
)
@api_view(["GET"])
def data_dictionary(request):
    """Return the Excel storage data dictionary / schema."""
    from .services.excel_storage import EXCEL_SCHEMA

    return Response(EXCEL_SCHEMA)


@swagger_auto_schema(
    method="post",
    operation_description=(
        "Webhook endpoint for Power Automate flows.\n"
        "Receives resume processing requests from email triggers."
    ),
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "file_url": openapi.Schema(type=openapi.TYPE_STRING, description="URL of the resume file"),
            "file_name": openapi.Schema(type=openapi.TYPE_STRING, description="Name of the file"),
            "sender_email": openapi.Schema(type=openapi.TYPE_STRING, description="Email sender"),
            "source": openapi.Schema(type=openapi.TYPE_STRING, default="email"),
        },
    ),
    responses={202: "Processing started"},
)
@api_view(["POST"])
def power_automate_webhook(request):
    """
    Webhook for Power Automate email flow integration.

    This endpoint is called when a new email with resume attachment
    is received in the configured group mailbox.
    """
    data = request.data
    file_url = data.get("file_url", "")
    file_name = data.get("file_name", "unknown")
    sender_email = data.get("sender_email", "")

    if not file_url:
        return Response(
            {"error": "file_url is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Create pending record for email-sourced resume
    record = ResumeRecord.objects.create(
        original_file_name=file_name,
        file_type=os.path.splitext(file_name)[1].lower(),
        resume_source=ResumeRecord.Source.EMAIL,
        status=ResumeRecord.Status.PENDING,
    )

    ProcessingLog.objects.create(
        resume_record=record,
        level="info",
        step="ingestion",
        message=f"Resume received from email: {sender_email}",
        details={"file_url": file_url, "sender": sender_email},
    )
    try:
        ExcelStorageClient().append_log(
            level="info",
            step="ingestion",
            message=f"Resume received from email: {sender_email}",
            record_id=str(record.id),
            candidate_id="",
            original_file_name=file_name,
            details={"file_url": file_url, "sender": sender_email},
        )
    except Exception as exc:
        logger.warning(f"Could not write log to Excel: {exc}")

    # TODO: Download file from URL and process asynchronously
    # For now, return acceptance response
    return Response(
        {
            "message": "Resume processing request accepted",
            "record_id": str(record.id),
            "status": "pending",
        },
        status=status.HTTP_202_ACCEPTED,
    )


# ---------------------------------------------------------------------------
# n8n Webhook
# ---------------------------------------------------------------------------

_N8N_EXT_CONTENT_TYPE = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".rtf": "text/rtf",
    ".txt": "text/plain",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


@swagger_auto_schema(
    method="post",
    operation_description=(
        "Webhook for n8n email-triggered resume processing.\n\n"
        "n8n sends the email attachment as base64-encoded JSON.\n\n"
        "```json\n"
        "{\n"
        '  "file_name": "resume.pdf",\n'
        '  "file_content_base64": "<base64>",\n'
        '  "sender_email": "applicant@example.com",\n'
        '  "subject": "Job Application"\n'
        "}\n"
        "```"
    ),
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["file_content_base64"],
        properties={
            "file_name": openapi.Schema(type=openapi.TYPE_STRING),
            "file_content_base64": openapi.Schema(type=openapi.TYPE_STRING),
            "sender_email": openapi.Schema(type=openapi.TYPE_STRING),
            "subject": openapi.Schema(type=openapi.TYPE_STRING),
        },
    ),
    responses={
        201: ResumeRecordSerializer(),
        200: ResumeRecordSerializer(),
        400: "Validation / input error",
        500: "Pipeline processing error",
    },
)
@api_view(["POST"])
def n8n_webhook(request):
    """
    Webhook for n8n email-flow integration.

    Expects a JSON body with base64-encoded file content
    (from n8n Code node → HTTP Request node).
    """
    data = request.data
    file_name = data.get("file_name") or "resume.pdf"
    file_content_b64 = data.get("file_content_base64", "")
    sender_email = data.get("sender_email", "")
    subject = data.get("subject", "")

    if not file_content_b64:
        return Response(
            {"error": "'file_content_base64' is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ── Decode base64 ────────────────────────────────────────────────────
    try:
        import re as _re
        # Strip data-URI prefix if present
        if "," in file_content_b64:
            file_content_b64 = file_content_b64.split(",", 1)[1]
        # Normalise URL-safe base64 chars
        file_content_b64 = file_content_b64.replace("-", "+").replace("_", "/")
        # Remove any non-base64 characters (whitespace, newlines, etc.)
        file_content_b64 = _re.sub(r"[^A-Za-z0-9+/]", "", file_content_b64)
        # Fix padding
        remainder = len(file_content_b64) % 4
        if remainder == 1:
            file_content_b64 = file_content_b64[:-1]
        elif remainder in (2, 3):
            file_content_b64 += "=" * (4 - remainder)
        file_bytes = base64.b64decode(file_content_b64)
    except Exception as exc:
        return Response(
            {"error": f"Failed to decode base64 content: {exc}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    ext = os.path.splitext(file_name)[1].lower()
    file_size = len(file_bytes)
    logger.info("[n8n] '%s': %d bytes, first 16 hex: %s",
                file_name, file_size, file_bytes[:16].hex())

    if file_size < 64:
        return Response(
            {
                "error": (
                    f"Decoded file is only {file_size} bytes — too small to be "
                    "a real resume. Make sure the n8n Code node uses "
                    "this.helpers.getBinaryDataBuffer() to read the actual file."
                ),
                "decoded_bytes": file_size,
                "first_16_hex": file_bytes[:16].hex(),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    content_type = _N8N_EXT_CONTENT_TYPE.get(ext, "application/octet-stream")
    uploaded_file = SimpleUploadedFile(
        name=file_name, content=file_bytes, content_type=content_type,
    )

    # ── Create / update the tracking record ──────────────────────────────
    source = ResumeRecord.Source.EMAIL
    existing = (
        ResumeRecord.objects.filter(original_file_name=file_name)
        .order_by("-created_at")
        .first()
    )
    if existing:
        record = existing
        record.previous_version_id = record.id
        record.version = (record.version or 1) + 1
        record.file_type = ext
        record.file_size_bytes = file_size
        record.resume_source = source
        record.status = ResumeRecord.Status.PENDING
        record.error_message = ""
        record.extracted_data = {}
        record.extraction_confidence = 0.0
        record.dataverse_record_id = ""
        record.standardized_file_path = ""
        record.processed_at = None
        record.save()
        _log(
            record, "info", "ingestion",
            f"Re-upload via n8n for '{file_name}' — updating existing record "
            f"(version {record.version})",
            {"sender": sender_email, "subject": subject},
        )
    else:
        record = ResumeRecord.objects.create(
            original_file_name=file_name,
            file_type=ext,
            file_size_bytes=file_size,
            resume_source=source,
            status=ResumeRecord.Status.PENDING,
        )
        _log(
            record, "info", "ingestion",
            f"Resume received via n8n from: {sender_email}",
            {"sender": sender_email, "subject": subject, "file_bytes": file_size},
        )

    return _run_pipeline(record, uploaded_file, source)
