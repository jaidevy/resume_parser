# Resume Parsing & Standardization Agent

An AI-powered system for parsing resumes, extracting structured data, and generating standardized outputs. Built with Django REST Framework, OpenAI GPT-4o-mini, and Azure AI Document Intelligence.

## Features

- **Multi-format Resume Parsing**: PDF, DOCX, DOC, TXT, RTF (via Azure Document Intelligence or PyMuPDF4LLM fallback)
- **AI-Powered Extraction**: OpenAI GPT-4o-mini with Pydantic schema validation
- **Confidence Scoring**: Per-field and overall extraction confidence (0.0–1.0)
- **Standardized Output**: Professional DOCX template with consistent styling
- **REST API**: Full CRUD with Swagger and ReDoc documentation
- **Streamlit UI**: Web-based upload, viewing, and dashboard
- **Excel Storage**: Extracted data stored in `.xlsx` (mirrors OneDrive/SharePoint schema)
- **Power Automate Webhook**: Email-triggered ingestion endpoint compatible with Power Automate HTTP connectors
- **Duplicate Handling**: CandidateID-based upsert with version tracking
- **Evaluation Framework**: LLM prompt and agent pipeline evaluation across 10 sample resumes

## Quick Start

```bash
# 1. Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
copy .env.example .env
# Edit .env — set OPENAI_API_KEY and optionally Azure Document Intelligence keys

# 4. Initialize database
python manage.py migrate

# 5. Run API server
python manage.py runserver

# 6. Run Streamlit UI (new terminal)
streamlit run streamlit_app.py
```

> Swagger UI available at `http://localhost:8000/swagger/` once the server is running.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/resumes/` | Upload and process a resume |
| GET | `/api/v1/resumes/` | List all resumes (paginated, filterable) |
| GET | `/api/v1/resumes/{id}/` | Get resume details |
| GET | `/api/v1/resumes/{id}/status_check/` | Check processing status |
| GET | `/api/v1/resumes/{id}/extracted_data/` | Get extracted JSON data |
| GET | `/api/v1/resumes/{id}/text_preview/` | View plain-text resume content |
| GET | `/api/v1/resumes/{id}/download/` | Download standardized DOCX |
| GET | `/api/v1/resumes/{id}/logs/` | View processing audit logs |
| GET | `/api/v1/health/` | Health check |
| GET | `/api/v1/schema/` | Excel data dictionary / schema |
| POST | `/api/v1/webhook/power-automate/` | Email-triggered ingestion (Power Automate compatible) |
| GET | `/swagger/` | Swagger UI |
| GET | `/redoc/` | ReDoc documentation |

## Running Evaluations

```bash
python -m evaluation.eval_prompts     # LLM prompt evaluation
python -m evaluation.eval_agents      # Agent pipeline evaluation
python -m evaluation.evaluation_sheet # Full evaluation sheet (10 resumes)
```

Results are saved to `evaluation/evaluation_results.xlsx` and `evaluation/evaluation_results.json`.

## Documentation

- [Technical Document](docs/Technical_Document.md) — Design, prompts/schema, connectors, limitations, and how to run


## Project Structure

```
resume_parser/
├── api/                          # Django REST API
│   ├── models.py                 # Database models (ResumeRecord, ProcessingLog)
│   ├── serializers.py            # DRF serializers
│   ├── views.py                  # API views & pipeline orchestration
│   ├── urls.py                   # URL routing
│   └── services/                 # Business logic
│       ├── validator.py          # File type, size, and readability checks
│       ├── parser.py             # Text extraction orchestrator
│       ├── document_intelligence.py  # Azure Document Intelligence connector
│       ├── extractor.py          # LLM extraction (OpenAI GPT-4o-mini)
│       ├── schemas.py            # Pydantic models (ResumeData, WorkExperience, …)
│       ├── standardizer.py       # Standardized DOCX generation
│       └── excel_storage.py      # Excel upsert & ProcessingLogs storage
├── resume_parser/                # Django project settings
├── streamlit_app.py              # Streamlit demo UI
├── evaluation/                   # LLM & agent evaluation
│   ├── eval_prompts.py           # LLM prompt evaluation
│   ├── eval_agents.py            # End-to-end agent evaluation
│   ├── evaluation_sheet.py       # 10-resume evaluation sheet
│   └── test_resumes/             # Sample resumes for evaluation
├── docs/                         # Documentation
│   └── Technical_Document.md
├── outputs/                      # Generated DOCX and raw LLM JSON outputs
├── sample_data/                  # Sample resumes for testing
└── uploads/                      # Uploaded resume files
```

## License

This project is for educational/assignment purposes.
