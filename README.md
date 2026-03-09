# Resume Parsing & Standardization Agent

An AI-powered system for parsing resumes, extracting structured data, and generating standardized outputs. Built with Django REST Framework, integrates with Microsoft Copilot Studio, Power Automate, and Dataverse.

## Features

- **Multi-format Resume Parsing**: PDF, DOCX, DOC, TXT, RTF, and images (via OCR)
- **AI-Powered Extraction**: GPT-4/Azure OpenAI with regex fallback
- **Standardized Output**: Professional DOCX template with skill categorization
- **REST API**: Full CRUD with Swagger documentation
- **Streamlit UI**: Web-based upload, viewing, and dashboard
- **Copilot Studio Integration**: Conversational agent for Microsoft Teams
- **Power Automate Flows**: Workflow automation for resume processing
- **Dataverse Storage**: Cloud-native data persistence
- **Comprehensive Testing**: 100+ unit tests with evaluation framework

## Quick Start

```bash
# 1. Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
copy .env.example .env
# Edit .env with your settings

# 4. Initialize database
python manage.py makemigrations api
python manage.py migrate

# 5. Run API server
python manage.py runserver

# 6. Run Streamlit UI (new terminal)
cd streamlit_app && streamlit run app.py
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/resumes/` | Upload and process a resume |
| GET | `/api/v1/resumes/` | List all resumes |
| GET | `/api/v1/resumes/{id}/` | Get resume details |
| GET | `/api/v1/resumes/{id}/status_check/` | Check processing status |
| GET | `/api/v1/resumes/{id}/extracted_data/` | Get extracted data |
| GET | `/api/v1/resumes/{id}/download/` | Download standardized DOCX |
| GET | `/api/v1/health/` | Health check |
| GET | `/swagger/` | Swagger UI |
| GET | `/redoc/` | ReDoc documentation |

## Running Tests

```bash
pytest                          # All tests
pytest -v                       # Verbose
pytest api/tests/test_extractor.py  # Specific file
pytest --cov=api                # With coverage
```

## Running Evaluations

```bash
python -m evaluation.eval_prompts     # LLM prompt evaluation
python -m evaluation.eval_agents      # Agent pipeline evaluation
python -m evaluation.evaluation_sheet # Full evaluation sheet (10 resumes)
```

## Documentation

- [Architecture](docs/architecture.md)
- [Setup Guide](docs/setup_guide.md)
- [User Guide](docs/user_guide.md)
- [Data Dictionary](docs/data_dictionary.md)
- [Copilot Studio Setup](copilot_studio/README.md)
- [Power Automate Setup](copilot_studio/power_automate/README.md)

## Project Structure

```
resume_parser/
├── api/                  # Django REST API
│   ├── models.py         # Database models
│   ├── serializers.py    # API serializers
│   ├── views.py          # API views
│   ├── services/         # Business logic
│   │   ├── validator.py  # File validation
│   │   ├── parser.py     # Text extraction
│   │   ├── ocr.py        # OCR processing
│   │   ├── extractor.py  # Data extraction (LLM + regex)
│   │   ├── dataverse.py  # Dataverse integration
│   │   └── standardizer.py  # Resume standardization
│   └── tests/            # Unit tests (100+)
├── streamlit_app/        # Streamlit frontend
├── evaluation/           # LLM & agent evaluation
├── copilot_studio/       # Copilot Studio + Power Automate config
├── docs/                 # Documentation
└── sample_data/          # 10 sample resumes
```

## License

This project is for educational/assignment purposes.
