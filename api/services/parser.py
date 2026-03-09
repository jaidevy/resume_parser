import logging

logger = logging.getLogger("api")


class ResumeParser:

    def __init__(self):
        from .document_intelligence import DocumentIntelligenceService

        self._doc_intel = DocumentIntelligenceService()

    def parse(self, file_path: str, file_type: str, needs_ocr: bool = False) -> dict:

        if self._doc_intel.is_available and self._doc_intel.supports_file_type(file_type):
            logger.info(
                "Attempting Document Intelligence extraction for %s (%s)",
                file_path,
                file_type,
            )
            result = self._doc_intel.extract_text(file_path, file_type)
            
            if result["success"]:
                text = result.get("text", "").strip()
                if len(text) < 20:
                    logger.warning(
                        "Document Intelligence returned only %d chars for %s "
                        "— treating as empty, falling back to legacy parser",
                        len(text),
                        file_path,
                    )
                    result["success"] = False
                    result["error"] = (
                        "Document Intelligence returned insufficient text "
                        f"({len(text)} chars)"
                    )
                else:
                    result.pop("tables", None)
                    return result
            logger.warning(
                "Document Intelligence failed (%s), falling back to legacy parser",
                result.get("error", "unknown"),
            )

        result = {
            "text": "",
            "pages": 0,
            "method": "text_extract",
            "success": False,
            "error": "",
        }

        # Local fallback for plain-text files
        if file_type == ".txt":
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
                if len(text.strip()) >= 20:
                    result["text"] = text
                    result["pages"] = 1
                    result["success"] = True
                    result["method"] = "text_read"
                else:
                    result["error"] = f"Text file too short ({len(text.strip())} chars)"
            except Exception as exc:
                result["error"] = f"Failed to read text file: {exc}"

        return result
