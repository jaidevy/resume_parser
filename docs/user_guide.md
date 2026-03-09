# User Guide

## Resume Parsing & Standardization Agent — API Reference & Usage

---

## Overview

The Resume Parsing & Standardization Agent exposes a **REST API** for uploading resumes, extracting structured data using AI (with regex fallback), and producing standardized output. All interaction happens through the API — use the Swagger UI or any HTTP client.

---

## Accessing the API

| Interface | URL |
|-----------|-----|
| **Swagger UI** (interactive) | http://localhost:8000/swagger/ |
| **ReDoc** (reference) | http://localhost:8000/redoc/ |
| **API Root** | http://localhost:8000/api/v1/ |
| **Admin Panel** | http://localhost:8000/admin/ |

---

## API Endpoints

### 1. Upload & Process Resume

**POST** `/api/v1/resumes/upload/`

Uploads a resume file, extracts structured data, stores it in Excel, and returns the extracted result.

**Request** (multipart/form-data):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | File | Yes | Resume file (PDF, DOCX, DOC, RTF, TXT, PNG, JPG) |

**cURL example:**
```bash
curl -X POST http://localhost:8000/api/v1/resumes/upload/ \
  -F "file=@/path/to/resume.pdf"
```

**PowerShell example:**
```powershell
$file = Get-Item ".\sample_data\sample_resumes\resume_01_standard.txt"
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/resumes/upload/" `
  -Method Post -Form @{ file = $file }
```

**Python example:**
```python
import requests

url = "http://localhost:8000/api/v1/resumes/upload/"
files = {"file": open("resume.pdf", "rb")}
response = requests.post(url, files=files)
print(response.json())
```

**Success Response (201 Created):**
```json
{
  "status": "success",
  "message": "Resume processed successfully",
  "data": {
    "record_id": 1,
    "candidate_id": "CAND-a1b2c3d4",
    "file_name": "resume.pdf",
    "extracted_data": {
      "full_name": "John Doe",
      "email": "john.doe@email.com",
      "phone": "+1-555-123-4567",
      "linkedin_url": "linkedin.com/in/johndoe",
      "location": "New York, NY",
      "years_of_experience": 5,
      "education": [...],
      "work_experience": [...],
      "skills": [...],
      "certifications": [...],
      "summary": "..."
    },
    "confidence_score": 0.85,
    "extraction_method": "llm",
    "standardized_file": "/outputs/resume_01_standard_standardized.docx",
    "excel_storage": {
      "action": "created",
      "version": 1,
      "row": 2,
      "status": "success"
    }
  }
}
```

**Error Response (400):**
```json
{
  "status": "error",
  "message": "File validation failed",
  "errors": ["Unsupported file type: .exe"]
}
```

---

### 2. List All Resumes

**GET** `/api/v1/resumes/`

Returns all processed resume records from the SQLite database.

```bash
curl http://localhost:8000/api/v1/resumes/
```

---

### 3. Retrieve a Resume

**GET** `/api/v1/resumes/{id}/`

Returns a single resume record by database ID.

```bash
curl http://localhost:8000/api/v1/resumes/1/
```

---

### 4. Download Standardized Resume

**GET** `/api/v1/resumes/{id}/download/`

Downloads the generated standardized DOCX file for a resume.

```bash
curl -O http://localhost:8000/api/v1/resumes/1/download/
```

---

### 5. Email Webhook

**POST** `/api/v1/resumes/webhook/email/`

Receives resumes via email webhook (from Power Automate or similar).

**Request body (JSON):**
```json
{
  "sender": "recruiter@company.com",
  "subject": "Resume - John Doe",
  "attachment_name": "john_doe_resume.pdf",
  "attachment_content": "<base64-encoded file>"
}
```

---

### 6. Health Check

**GET** `/api/v1/resumes/health/`

Returns system status and configuration.

```bash
curl http://localhost:8000/api/v1/resumes/health/
```

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "services": {
    "database": true,
    "openai_configured": true,
    "tesseract_available": false,
    "excel_storage_configured": true,
    "excel_path": "outputs/resume_data.xlsx"
  }
}
```

---

### 7. Data Dictionary

**GET** `/api/v1/resumes/schema/`

Returns the full data extraction schema with all field definitions.

---

## Supported File Types

| Format | Extension | Notes |
|--------|-----------|-------|
| PDF | `.pdf` | Native text + OCR fallback for scanned |
| Word | `.docx` | Full paragraph & table extraction |
| Legacy Word | `.doc` | Basic text extraction |
| Rich Text | `.rtf` | Via striprtf |
| Plain Text | `.txt` | Direct read |
| Images | `.png`, `.jpg`, `.jpeg`, `.tiff`, `.bmp` | OCR via Tesseract |

**File size limit:** 10 MB

---

## Extraction Pipeline

The processing pipeline follows these steps:

```
Upload → Validate → Parse Text → Extract Data → Store in Excel → Generate DOCX
```

1. **Validate** — Check file type, size, content integrity, and password protection
2. **Parse** — Extract raw text from the file (with OCR fallback for images/scanned PDFs)
3. **Extract** — Use OpenAI (GPT-4) to extract structured fields; falls back to regex if LLM unavailable
4. **Store** — Save extracted data to Excel (.xlsx) with duplicate detection and version tracking
5. **Standardize** — Generate a clean, formatted DOCX resume output

---

## Extracted Fields

| Field | Type | Description |
|-------|------|-------------|
| `full_name` | String | Candidate's full name |
| `email` | String | Email address |
| `phone` | String | Phone number |
| `linkedin_url` | String | LinkedIn profile URL |
| `location` | String | City, state, country |
| `years_of_experience` | Number | Total years of professional experience |
| `education` | Array | List of degrees with institution, field, year |
| `work_experience` | Array | List of positions with company, title, dates, responsibilities |
| `skills` | Array | Technical and soft skills |
| `certifications` | Array | Professional certifications |
| `summary` | String | Professional summary / objective |

---

## Duplicate Handling

The system detects duplicate candidates using a **Candidate ID** (MD5 hash of normalized name + email). When a duplicate is detected:

- The existing Excel row is **updated** (not duplicated)
- The **version number** is incremented
- The latest data overwrites previous data
- Processing logs track all upload attempts

---

## Excel Data Store

All extracted data is stored in an Excel workbook at the configured path (default: `outputs/resume_data.xlsx`). The workbook contains a single sheet (`ResumeData`) with 24 columns covering all extracted fields plus metadata.

To view the data:
- Open `outputs/resume_data.xlsx` in Excel, LibreOffice Calc, or Google Sheets
- Each row represents one candidate
- Complex fields (education, work experience, skills) are stored as JSON strings in their cells

---

## Standardized DOCX Output

Each processed resume generates a standardized `.docx` file in the `outputs/` directory. The document includes:

- **Header**: Candidate name and contact information
- **Summary**: Professional summary
- **Skills**: Categorized (Technical, Frameworks, Tools, Soft Skills)
- **Work Experience**: Chronological with responsibilities
- **Education**: Degrees with details
- **Certifications**: Professional certifications

---

## Confidence Scoring

Each extraction includes a confidence score (0.0 – 1.0):

| Range | Meaning |
|-------|---------|
| 0.9 – 1.0 | High confidence — most fields extracted |
| 0.7 – 0.9 | Good confidence — core fields present |
| 0.5 – 0.7 | Moderate — some fields missing |
| < 0.5 | Low — minimal data extracted |

The confidence score is calculated based on:
- Number of fields successfully extracted
- Weighted importance of each field (name + email carry higher weight)
- Presence of structured data (education, experience)

---

## Error Handling

| HTTP Status | Meaning |
|-------------|---------|
| 200 | Success |
| 201 | Created (resume processed) |
| 400 | Bad request (validation failed) |
| 404 | Resume not found |
| 500 | Server error (check logs) |

All errors include a descriptive `message` field and optional `errors` array.
