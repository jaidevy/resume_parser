# Data Dictionary

## Resume Parsing & Standardization Agent — Data Schema Reference

---

## 1. Django Models (SQLite — Local Metadata)

### 1.1 ResumeRecord

Primary table for tracking resume processing status.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, auto-generated | Unique record identifier |
| `candidate_id` | CharField(255) | nullable, unique | MD5 hash of email+phone for deduplication |
| `original_file_name` | CharField(512) | required | Name of the uploaded file |
| `file_type` | CharField(20) | required | File extension (.pdf, .docx, etc.) |
| `file_size_bytes` | BigIntegerField | default=0 | File size in bytes |
| `file_path` | CharField(1024) | blank | Server-side file storage path |
| `resume_source` | CharField(20) | default='upload' | Source: 'upload' or 'email' |
| `extracted_data` | JSONField | default={} | Full structured extraction result (JSON) |
| `extraction_confidence` | FloatField | default=0.0 | Overall confidence (0.0-1.0) |
| `status` | CharField(20) | default='pending' | Processing status (see below) |
| `error_message` | TextField | blank | Error details if processing failed |
| `dataverse_record_id` | CharField(255) | blank | Legacy field (Excel row reference) |
| `standardized_file_path` | CharField(1024) | blank | Path to generated DOCX |
| `created_at` | DateTimeField | auto | Record creation timestamp |
| `updated_at` | DateTimeField | auto | Last modification timestamp |
| `processed_at` | DateTimeField | nullable | Processing completion timestamp |
| `version` | IntegerField | default=1 | Version number for duplicate tracking |
| `previous_version_id` | UUIDField | nullable | Reference to previous version |

**Status Values:** `pending` → `validating` → `extracting` → `storing` → `standardizing` → `completed` | `failed`

---

### 1.2 ProcessingLog

Audit trail for every processing step.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, auto-generated | Unique log ID |
| `resume_record` | ForeignKey | CASCADE | Parent resume record |
| `level` | CharField(10) | default='info' | Log level: info, warning, error, debug |
| `step` | CharField(50) | required | Processing step (validation, parsing, extraction, etc.) |
| `message` | TextField | required | Human-readable log message |
| `details` | JSONField | default={} | Additional structured data |
| `timestamp` | DateTimeField | auto | Log entry timestamp |

---

### 1.3 ExtractionField

Per-field extraction confidence tracking.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | AutoField | PK | Auto-incremented ID |
| `resume_record` | ForeignKey | CASCADE | Parent resume record |
| `field_name` | CharField(100) | required | Name of the extracted field |
| `field_value` | TextField | blank | Extracted value (max 500 chars stored) |
| `confidence` | FloatField | default=0.0 | Field-level confidence (0.0-1.0) |
| `is_missing` | BooleanField | default=False | True if confidence < 0.3 |

**Unique Constraint:** (`resume_record`, `field_name`)

---

## 2. Excel Storage Schema (outputs/resume_data.xlsx)

Primary data store for all extracted resume fields. One row per candidate (upserted by CandidateID).

| Column | Type | Description |
|--------|------|-------------|
| `CandidateID` | Text | Unique identifier — MD5 hash of email+phone |
| `CandidateFullName` | Text | Full name of the candidate |
| `EmailIDs` | Text (JSON) | JSON array of email addresses |
| `Phones` | Text (JSON) | JSON array of phone numbers with country codes |
| `Gender` | Text | Gender only if explicitly stated in resume |
| `CurrentLocation` | Text | City/State/Country |
| `GeoDetails` | Text (JSON) | Normalized `{"city":"...","state":"...","country":"..."}` |
| `TotalExperience` | Text | Total years/months of experience |
| `WorkExperience` | Text (JSON) | Array of `{company, role, start_date, end_date, duration, summary}` |
| `KeySkills` | Text (JSON) | JSON array of skills |
| `Education` | Text (JSON) | Array of `{degree, specialization, institution, year}` |
| `Certifications` | Text (JSON) | JSON array of certification names |
| `LinkedInURL` | Text | LinkedIn profile URL |
| `GitHubURL` | Text | GitHub profile URL |
| `PortfolioURL` | Text | Portfolio website URL |
| `ProfessionalSummary` | Text | Generated 3-5 line factual summary |
| `Projects` | Text (JSON) | Array of `{name, description, technologies}` |
| `ExtractionConfidence` | Decimal | Overall extraction confidence (0.0-1.0) |
| `FieldConfidences` | Text (JSON) | Per-field confidence scores |
| `ResumeSource` | Text | 'upload' or 'email' |
| `OriginalFileName` | Text | Original uploaded file name |
| `ProcessedTimestamp` | DateTime | When the resume was processed (ISO format) |
| `Version` | Integer | Record version (incremented on resubmission) |
| `OriginalFileLink` | Text | Path/reference to original file on disk |

---

## 3. Extraction JSON Schema

The `extracted_data` JSON field (stored in both SQLite and Excel) follows this schema:

```json
{
    "candidate_full_name": "string",
    "email_ids": ["string"],
    "phones": ["string"],
    "gender": "string (only if explicitly present)",
    "current_location": "string",
    "geo_details": {"city": "string", "state": "string", "country": "string"},
    "total_experience": "string (e.g., '5 years 3 months')",
    "work_experience": [
        {
            "company": "string",
            "role": "string",
            "start_date": "string",
            "end_date": "string",
            "duration": "string",
            "summary": "string"
        }
    ],
    "key_skills": ["string"],
    "education": [
        {
            "degree": "string",
            "specialization": "string",
            "institution": "string",
            "year": "string"
        }
    ],
    "certifications": ["string"],
    "linkedin_url": "string",
    "github_url": "string",
    "portfolio_url": "string",
    "professional_summary": "string (3-5 lines, factual)",
    "projects": [
        {
            "name": "string",
            "description": "string",
            "technologies": ["string"]
        }
    ],
    "field_confidences": {
        "candidate_full_name": 0.95,
        "email_ids": 0.9,
        "...": "number (0.0-1.0)"
    },
    "candidate_id": "string (MD5 hash)"
}
```

---

## 4. Duplicate Handling

| Scenario | Behavior |
|----------|----------|
| New candidate (no matching CandidateID) | New row created in Excel, version = 1 |
| Same candidate resubmitted | Existing row updated, version incremented |
| CandidateID calculation | MD5 hash of `first_email + first_phone` |
| No email or phone | MD5 hash of candidate name used as fallback |

---

## 5. Processing Steps (Logged)

| Step | Description |
|------|-------------|
| `ingestion` | File received and initial record created |
| `validation` | File type, size, and content checks |
| `parsing` | Text extraction from file |
| `extraction` | Structured data extraction (LLM or regex) |
| `storage` | Data saved to Excel |
| `standardization` | DOCX resume generated |
| `complete` | Pipeline finished successfully |

---

## 6. Confidence Scoring

| Score Range | Meaning |
|-------------|---------|
| 1.0 | Field is clearly and explicitly stated |
| 0.7 – 0.9 | Present but partially ambiguous |
| 0.3 – 0.6 | Inferred from context |
| 0.0 – 0.2 | Not found or highly uncertain |

Missing fields are stored as blank/null with confidence marked as low (< 0.3).
