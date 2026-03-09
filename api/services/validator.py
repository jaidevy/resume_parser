import os
import logging
import zipfile
from pathlib import Path
from django.conf import settings

logger = logging.getLogger("api")

# Supported MIME types mapped to extensions
MIME_TYPE_MAP = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/rtf": ".rtf",
    "text/rtf": ".rtf",
    "text/plain": ".txt",
    "image/png": ".png",
    "image/jpeg": ".jpg",
}


class ValidationError(Exception):

    def __init__(self, message: str, code: str = "validation_error"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class FileValidator:

    def __init__(self):
        self.max_size = settings.MAX_FILE_SIZE_BYTES
        self.supported_types = settings.SUPPORTED_FILE_TYPES

    def validate(self, file) -> dict:
    
        result = {
            "valid": True,
            "file_type": "",
            "file_size": 0,
            "errors": [],
            "needs_ocr": False,
            "warnings": [],
        }

        # 1. Check file exists and is not empty
        if not file:
            result["valid"] = False
            result["errors"].append("No file provided.")
            return result

        if file.size == 0:
            result["valid"] = False
            result["errors"].append("File is empty (0 bytes).")
            return result

        result["file_size"] = file.size

        # 2. Check file size
        if file.size > self.max_size:
            result["valid"] = False
            result["errors"].append(
                f"File size ({file.size / (1024*1024):.1f} MB) exceeds "
                f"maximum allowed size ({settings.MAX_FILE_SIZE_MB} MB)."
            )
            return result

        # 3. Check file extension
        ext = os.path.splitext(file.name)[1].lower()
        result["file_type"] = ext

        if ext not in self.supported_types:
            result["valid"] = False
            result["errors"].append(
                f"Unsupported file type '{ext}'. "
                f"Supported: {', '.join(self.supported_types)}"
            )
            return result

        # 4. Check if file needs OCR (image files)
        if ext in [".png", ".jpg", ".jpeg"]:
            result["needs_ocr"] = True
            result["warnings"].append(
                "Image file detected. OCR will be used for text extraction."
            )

        # 5. Basic content validation
        try:
            content_check = self._check_content(file, ext)
            if not content_check["readable"]:
                if content_check.get("password_protected"):
                    result["valid"] = False
                    result["errors"].append(
                        content_check.get("error_detail")
                        or "File appears to be password-protected. "
                        "Please upload an unprotected file."
                    )
                elif content_check.get("corrupted"):
                    result["valid"] = False
                    result["errors"].append(
                        content_check.get("error_detail")
                        or "File appears to be corrupted or unreadable. "
                        "Please re-export and re-upload."
                    )
                elif content_check.get("empty_content"):
                    # For PDFs that might be scanned images
                    if ext == ".pdf":
                        result["needs_ocr"] = True
                        result["warnings"].append(
                            "PDF contains no extractable text. "
                            "OCR will be attempted."
                        )
                    else:
                        result["valid"] = False
                        result["errors"].append(
                            content_check.get("error_detail")
                            or "File contains no readable text content."
                        )
                else:
                    result["valid"] = False
                    result["errors"].append(
                        content_check.get("error_detail")
                        or "File content could not be read."
                    )
        except Exception as e:
            logger.warning(f"Content validation warning: {e}")
            result["warnings"].append(f"Could not fully validate content: {str(e)}")

        # Reset file position after reading
        file.seek(0)

        logger.info(
            f"Validation complete for '{file.name}': "
            f"valid={result['valid']}, type={result['file_type']}"
        )
        return result

    def _check_content(self, file, ext: str) -> dict:
  
        result = {
            "readable": True,
            "password_protected": False,
            "empty_content": False,
            "corrupted": False,
            "error_detail": "",
        }

        try:
            # Read first bytes to check magic numbers
            header = file.read(min(8192, file.size))
            file.seek(0)

            if ext == ".pdf":
                # ── PDF checks ──────────────────────────────────────────
                if not header.startswith(b"%PDF"):
                    result["readable"] = False
                    result["corrupted"] = True
                    result["error_detail"] = (
                        "File does not start with a valid PDF header. "
                        "It may be corrupted or not a real PDF."
                    )
                    return result

                # Quick header-level encryption marker
                if b"/Encrypt" in header:
                    result["readable"] = False
                    result["password_protected"] = True
                    result["error_detail"] = (
                        "PDF contains an /Encrypt dictionary — "
                        "it is password-protected."
                    )
                    return result

                # Deep check with PyPDF2 (catches encryption beyond first 8 KB)
                try:
                    import PyPDF2

                    file.seek(0)
                    reader = PyPDF2.PdfReader(file)
                    if reader.is_encrypted:
                        # Try decrypting with empty password (some PDFs are
                        # encrypted but have an empty owner password).
                        try:
                            if reader.decrypt("") == 0:
                                result["readable"] = False
                                result["password_protected"] = True
                                result["error_detail"] = (
                                    "PDF is encrypted and requires a password."
                                )
                                return result
                        except Exception:
                            result["readable"] = False
                            result["password_protected"] = True
                            result["error_detail"] = (
                                "PDF is encrypted and could not be decrypted."
                            )
                            return result

                    # Check page count — 0-page PDF is effectively empty
                    if len(reader.pages) == 0:
                        result["readable"] = False
                        result["empty_content"] = True
                        result["error_detail"] = "PDF has zero pages."
                        return result

                    file.seek(0)
                except ImportError:
                    logger.debug("PyPDF2 not installed; skipping deep PDF check")
                    file.seek(0)
                except Exception as pdf_err:
                    file.seek(0)
                    result["readable"] = False
                    result["corrupted"] = True
                    result["error_detail"] = (
                        f"PDF could not be read — file may be corrupted: {pdf_err}"
                    )
                    return result

            elif ext == ".docx":
                # ── DOCX checks ─────────────────────────────────────────
                if not header.startswith(b"PK"):
                    result["readable"] = False
                    result["corrupted"] = True
                    result["error_detail"] = (
                        "DOCX file does not have a valid ZIP/PK header. "
                        "It may be corrupted or not a real DOCX."
                    )
                    return result

                # DOCX is a ZIP archive — try opening it
                try:
                    file.seek(0)
                    zf = zipfile.ZipFile(file)
                    names = zf.namelist()

                    # Standard DOCX must contain word/document.xml
                    if "word/document.xml" not in names:
                        # Check for EncryptedPackage (MS Office encryption)
                        if "EncryptedPackage" in names or "EncryptionInfo" in names:
                            result["readable"] = False
                            result["password_protected"] = True
                            result["error_detail"] = (
                                "DOCX is encrypted / password-protected."
                            )
                        else:
                            result["readable"] = False
                            result["corrupted"] = True
                            result["error_detail"] = (
                                "DOCX archive missing word/document.xml — "
                                "file may be corrupted."
                            )
                        return result

                    zf.close()
                    file.seek(0)
                except zipfile.BadZipFile:
                    result["readable"] = False
                    result["corrupted"] = True
                    result["error_detail"] = (
                        "DOCX file is not a valid ZIP archive — "
                        "file may be corrupted."
                    )
                    file.seek(0)
                    return result
                except Exception as docx_err:
                    file.seek(0)
                    result["readable"] = False
                    result["corrupted"] = True
                    result["error_detail"] = (
                        f"Could not open DOCX: {docx_err}"
                    )
                    return result

            elif ext == ".doc":
                # ── Legacy DOC checks ───────────────────────────────────
                # OLE Compound File must start with D0 CF 11 E0
                if not header.startswith(b"\xd0\xcf\x11\xe0"):
                    result["readable"] = False
                    result["corrupted"] = True
                    result["error_detail"] = (
                        "DOC file does not have a valid OLE header."
                    )
                    return result

                # Check for Word encryption by properly parsing the OLE
                # compound file and inspecting the WordDocument stream's
                # FibBase flags (bit 8 of the 16-bit field at offset 0x0A).
                try:
                    import olefile

                    file.seek(0)
                    ole = olefile.OleFileIO(file)

                    # EncryptedPackage / EncryptionInfo → definitely encrypted
                    if ole.exists("EncryptedPackage") or ole.exists("EncryptionInfo"):
                        result["readable"] = False
                        result["password_protected"] = True
                        result["error_detail"] = (
                            "DOC file is encrypted / password-protected."
                        )
                        ole.close()
                        file.seek(0)
                        return result

                    # Read FibBase from WordDocument stream
                    if ole.exists("WordDocument"):
                        word_stream = ole.openstream("WordDocument").read(12)
                        if len(word_stream) >= 12:
                            # FibBase flags at offset 0x0A (little-endian u16)
                            # Bit 8 (0x0100) = fEncrypted
                            flags = int.from_bytes(
                                word_stream[0x0A:0x0C], "little"
                            )
                            if flags & 0x0100:
                                result["readable"] = False
                                result["password_protected"] = True
                                result["error_detail"] = (
                                    "DOC file is password-protected "
                                    "(fEncrypted flag set in FibBase)."
                                )
                                ole.close()
                                file.seek(0)
                                return result

                    ole.close()
                    file.seek(0)
                except ImportError:
                    logger.debug(
                        "olefile not installed; skipping deep DOC check"
                    )
                    file.seek(0)
                except Exception as doc_err:
                    logger.debug("DOC encryption check error: %s", doc_err)
                    file.seek(0)

            elif ext == ".rtf":
                # RTF must start with {\rtf
                if not header.startswith(b"{\\rtf"):
                    result["readable"] = False
                    result["corrupted"] = True
                    result["error_detail"] = (
                        "RTF file does not start with {\\rtf header."
                    )
                    return result

            elif ext == ".txt":
                # Check for readable text
                try:
                    header.decode("utf-8")
                except UnicodeDecodeError:
                    try:
                        header.decode("latin-1")
                    except UnicodeDecodeError:
                        result["readable"] = False
                        result["error_detail"] = (
                            "Text file could not be decoded as UTF-8 or Latin-1."
                        )
                        return result

                if len(header.strip()) == 0:
                    result["readable"] = False
                    result["empty_content"] = True
                    result["error_detail"] = "Text file is empty."

            elif ext in [".png", ".jpg", ".jpeg"]:
                # Validate image magic bytes
                valid_image = (
                    header.startswith(b"\x89PNG")          # PNG
                    or header.startswith(b"\xff\xd8\xff")  # JPEG
                )
                if not valid_image:
                    result["readable"] = False
                    result["corrupted"] = True
                    result["error_detail"] = (
                        f"Image file ({ext}) has invalid header bytes — "
                        "file may be corrupted."
                    )
                    return result

        except Exception as e:
            logger.warning(f"Content check error: {e}")
            result["error_detail"] = str(e)

        return result

    def save_uploaded_file(self, file) -> str:
        """
        Save uploaded file to the upload directory.

        Returns:
            str: Path to the saved file.
        """
        import uuid

        upload_dir = settings.UPLOAD_DIR
        # Generate unique filename
        unique_name = f"{uuid.uuid4().hex}_{file.name}"
        file_path = os.path.join(upload_dir, unique_name)

        with open(file_path, "wb+") as destination:
            for chunk in file.chunks():
                destination.write(chunk)

        logger.info(f"File saved: {file_path}")
        return file_path
