"""
Serializers for the Resume Parser API.
"""
from rest_framework import serializers
from .models import ResumeRecord, ProcessingLog, ExtractionField


# Fields stored on extracted_data that are internal metadata, not resume content
_EXTRACTED_DATA_INTERNAL_FIELDS = {
    "candidate_id", "resume_source", "original_file_name",
    "file_path", "version", "field_confidences",
}

# Canonical extracted-data field order for the API response
_EXTRACTED_DATA_FIELDS = [
    "candidate_full_name",
    "email_ids",
    "phones",
    "gender",
    "current_location",
    "geo_details",
    "total_experience",
    "work_experience",
    "key_skills",
    "education",
    "certifications",
    "linkedin_url",
    "github_url",
    "portfolio_url",
    "professional_summary",
    "projects",
]


class ExtractionFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExtractionField
        fields = ["field_name", "field_value", "confidence", "is_missing"]


class ProcessingLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessingLog
        fields = ["id", "level", "step", "message", "details", "timestamp"]


class ResumeRecordSerializer(serializers.ModelSerializer):
    extracted_data = serializers.SerializerMethodField()
    field_confidences = serializers.SerializerMethodField()
    field_quality_notes = serializers.SerializerMethodField()

    class Meta:
        model = ResumeRecord
        fields = [
            "id",
            "candidate_id",
            "original_file_name",
            "file_type",
            "file_size_bytes",
            "resume_source",
            "status",
            "version",
            "extraction_confidence",
            "extracted_data",
            "field_confidences",
            "field_quality_notes",
            "error_message",
            "created_at",
            "processed_at",
        ]
        read_only_fields = fields

    def get_extracted_data(self, obj):
        """Return only canonical resume fields, stripping internal metadata."""
        raw = obj.extracted_data or {}
        result = {}
        for field in _EXTRACTED_DATA_FIELDS:
            result[field] = raw.get(field, "" if field not in (
                "email_ids", "phones", "key_skills", "education",
                "certifications", "work_experience", "projects",
            ) else [])
        # Preserve any non-internal extra fields the LLM may have added
        for key, value in raw.items():
            if key not in _EXTRACTED_DATA_INTERNAL_FIELDS and key not in result:
                result[key] = value
        return result

    def get_field_confidences(self, obj):
        """Return per-field confidence scores from ExtractionField or extracted_data."""
        # Prefer DB-stored per-field confidence (ExtractionField model)
        fields = ExtractionField.objects.filter(resume_record=obj)
        if fields.exists():
            return {
                f.field_name: {
                    "confidence": f.confidence,
                    "is_missing": f.is_missing,
                }
                for f in fields
            }
        # Fallback: return from extracted_data blob
        raw = obj.extracted_data or {}
        fc = raw.get("field_confidences", {})
        return {k: {"confidence": v, "is_missing": v < 0.3} for k, v in fc.items()}

    def get_field_quality_notes(self, obj):
        """Return quality-issue warnings for fields where contamination was detected."""
        raw = obj.extracted_data or {}
        return raw.get("field_quality_notes", {})


class ResumeRecordListSerializer(serializers.ModelSerializer):
    """Lighter serializer for list views."""

    class Meta:
        model = ResumeRecord
        fields = [
            "id",
            "candidate_id",
            "original_file_name",
            "file_type",
            "resume_source",
            "extraction_confidence",
            "status",
            "created_at",
            "processed_at",
            "version",
        ]


class ResumeUploadSerializer(serializers.Serializer):
    """Serializer for resume file upload."""

    file = serializers.FileField(
        help_text="Resume file (.pdf, .docx, .doc, .rtf, .txt, .png, .jpg)"
    )
    source = serializers.ChoiceField(
        choices=ResumeRecord.Source.choices,
        default=ResumeRecord.Source.UPLOAD,
        help_text="Source of the resume (upload or email)",
    )

    def validate_file(self, value):
        from django.conf import settings
        import os

        # Check file size
        if value.size > settings.MAX_FILE_SIZE_BYTES:
            raise serializers.ValidationError(
                f"File too large. Maximum size is {settings.MAX_FILE_SIZE_MB} MB."
            )

        # Check file extension
        ext = os.path.splitext(value.name)[1].lower()
        if ext not in settings.SUPPORTED_FILE_TYPES:
            raise serializers.ValidationError(
                f"Unsupported file type '{ext}'. "
                f"Supported types: {', '.join(settings.SUPPORTED_FILE_TYPES)}"
            )

        return value


class ExtractedDataSerializer(serializers.Serializer):
    """Schema for the extracted resume data (JSON contract)."""

    candidate_full_name = serializers.CharField(required=False, allow_blank=True)
    email_ids = serializers.ListField(
        child=serializers.EmailField(), required=False, default=list
    )
    phones = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )
    gender = serializers.CharField(required=False, allow_blank=True)
    current_location = serializers.CharField(required=False, allow_blank=True)
    geo_details = serializers.DictField(required=False, default=dict)
    total_experience = serializers.CharField(required=False, allow_blank=True)
    work_experience = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )
    key_skills = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )
    education = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )
    certifications = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )
    linkedin_url = serializers.URLField(required=False, allow_blank=True)
    github_url = serializers.URLField(required=False, allow_blank=True)
    portfolio_url = serializers.URLField(required=False, allow_blank=True)
    professional_summary = serializers.CharField(required=False, allow_blank=True)
    projects = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )


class StandardizedResumeResponseSerializer(serializers.Serializer):
    """Response schema for standardized resume output."""

    resume_record_id = serializers.UUIDField()
    download_url = serializers.URLField()
    format = serializers.CharField()
    message = serializers.CharField()


class ProcessingStatusSerializer(serializers.Serializer):
    """Response for processing status check."""

    id = serializers.UUIDField()
    status = serializers.CharField()
    progress_message = serializers.CharField()
    extraction_confidence = serializers.FloatField()
    error_message = serializers.CharField(allow_blank=True)
