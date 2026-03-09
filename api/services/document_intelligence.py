import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from django.conf import settings

logger = logging.getLogger("api")

# File types supported by Document Intelligence
SUPPORTED_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class DocumentIntelligenceService:


    def __init__(self):
        self.endpoint = getattr(settings, "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "")
        self.api_key = getattr(settings, "AZURE_DOCUMENT_INTELLIGENCE_KEY", "")
        self._client = None

    # ── Public API ───────────────────────────────────────────────────────

    @property
    def is_available(self) -> bool:
        """Check whether the service is properly configured."""
        return bool(self.endpoint and self.api_key)

    def supports_file_type(self, file_type: str) -> bool:
        """Return True if Document Intelligence can handle this extension."""
        return file_type.lower() in SUPPORTED_CONTENT_TYPES

    def extract_text(self, file_path: str, file_type: str) -> dict:
      
        result = {
            "text": "",
            "pages": 0,
            "method": "document_intelligence",
            "success": False,
            "error": "",
            "tables": [],
        }

        if not self.is_available:
            result["error"] = (
                "Azure Document Intelligence is not configured. "
                "Set AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and "
                "AZURE_DOCUMENT_INTELLIGENCE_KEY in your environment."
            )
            return result

        content_type = SUPPORTED_CONTENT_TYPES.get(file_type.lower())
        if not content_type:
            result["error"] = (
                f"File type '{file_type}' is not supported by Document Intelligence."
            )
            return result

        try:
            client = self._get_client()
            
            with open(file_path, "rb") as f:
                poller = client.begin_analyze_document(
                    model_id="prebuilt-layout",
                    body=f,
                    content_type=content_type,
                )
                doc_result = poller.result()

            # Extract text content
            result["text"] = doc_result.content or ""
            result["pages"] = len(doc_result.pages) if doc_result.pages else 0

            # Extract tables (useful for structured resume sections)
            if doc_result.tables:
                for table in doc_result.tables:
                    rows: list[list[str]] = []
                    max_row = max(
                        (cell.row_index for cell in table.cells), default=-1
                    )
                    max_col = max(
                        (cell.column_index for cell in table.cells), default=-1
                    )
                    # Pre-fill grid
                    for _ in range(max_row + 1):
                        rows.append([""] * (max_col + 1))
                    for cell in table.cells:
                        rows[cell.row_index][cell.column_index] = (
                            cell.content or ""
                        )
                    result["tables"].append(rows)

            result["success"] = bool(result["text"].strip())

            # ── Dump raw DI output to file for debugging ────────────
            self._dump_raw_output(file_path, result)

            logger.info(
                "Document Intelligence extracted %d chars, %d pages, %d tables",
                len(result["text"]),
                result["pages"],
                len(result["tables"]),
            )

        except Exception as e:
            logger.error("Document Intelligence extraction failed: %s", e)
            result["error"] = f"Document Intelligence extraction failed: {e}"

        return result

    # ── Internals ────────────────────────────────────────────────────────

    @staticmethod
    def _dump_raw_output(source_path: str, result: dict) -> None:
        """Write the raw DI output to ``outputs/`` for debugging."""
        try:
            out_dir = Path(__file__).resolve().parents[2] / "outputs"
            out_dir.mkdir(exist_ok=True)
            stem = Path(source_path).stem
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            # --- raw text ---
            txt_file = out_dir / f"di_raw_{stem}_{ts}.txt"
            txt_file.write_text(result.get("text", ""), encoding="utf-8")
            # --- metadata + tables as JSON ---
            meta_file = out_dir / f"di_raw_{stem}_{ts}.json"
            meta = {
                "source": source_path,
                "pages": result.get("pages", 0),
                "text_length": len(result.get("text", "")),
                "tables": result.get("tables", []),
                "success": result.get("success", False),
                "error": result.get("error", ""),
            }
            meta_file.write_text(
                json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            logger.info("DI raw output saved to %s", txt_file)
        except Exception as exc:
            logger.warning("Could not dump DI raw output: %s", exc)

    def _get_client(self):
        """Lazily create and cache the Document Intelligence client."""
        if self._client is None:
            try:
                from azure.ai.documentintelligence import DocumentIntelligenceClient
                from azure.core.credentials import AzureKeyCredential
            except ImportError as exc:
                raise ImportError(
                    "azure-ai-documentintelligence package is not installed. "
                    "Run: pip install azure-ai-documentintelligence"
                ) from exc

            self._client = DocumentIntelligenceClient(
                endpoint=self.endpoint,
                credential=AzureKeyCredential(self.api_key),
            )
        return self._client
