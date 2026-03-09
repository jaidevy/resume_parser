# Setup Guide

## Resume Parsing & Standardization Agent — Installation & Configuration

---

## Prerequisites

- **Python 3.10+** installed
- **pip** package manager
- **Git** (optional, for version control)
- **Tesseract OCR** (optional, for image/scanned PDF support)
- **OpenAI API key** (for LLM-based extraction; regex fallback available without it)

---

## Step 1: Clone / Download the Project

```bash
git clone <repository-url> resume_parser
cd resume_parser
```

---

## Step 2: Create Virtual Environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

---

## Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Key Dependencies:

| Package | Purpose |
|---------|---------|
| Django | Web framework |
| djangorestframework | REST API |
| drf-yasg | Swagger/OpenAPI docs |
| python-docx | DOCX parsing & generation |
| PyPDF2, pymupdf4llm | PDF parsing (with table & multi-column support) |
| striprtf | RTF parsing |
| pytesseract, Pillow | OCR for images |
| openai | LLM extraction |
| openpyxl | Excel (.xlsx) storage |
| pytest, pytest-django | Testing |

---

## Step 4: Configure Environment Variables

Copy and edit the `.env` file:

```bash
# Windows
copy .env .env.local
notepad .env

# Linux/macOS
cp .env .env.local
nano .env
```

### Required Settings:
```env
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_DEBUG=True
```

### Optional — OpenAI (for LLM-based extraction):
```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4
```

### Optional — Tesseract OCR:
```env
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

### Excel Storage:
```env
EXCEL_OUTPUT_PATH=outputs/resume_data.xlsx
```

> **Note:** If OpenAI is not configured, the system falls back to regex-based extraction. Excel storage is always available.

---

## Step 5: Initialize the Database

```bash
python manage.py makemigrations api
python manage.py migrate
```

---

## Step 6: Create a Superuser (Optional)

```bash
python manage.py createsuperuser
```

---

## Step 7: Run the Django API Server

```bash
python manage.py runserver
```

The API is now available at:
- **API Root**: http://localhost:8000/api/v1/
- **Swagger UI**: http://localhost:8000/swagger/
- **ReDoc**: http://localhost:8000/redoc/
- **Admin**: http://localhost:8000/admin/

---

## Step 8: Run Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest api/tests/test_extractor.py -v

# Run with coverage
pytest --cov=api --cov-report=html
```

---

## Step 9: Run Evaluations

```bash
# LLM prompt evaluation (requires OpenAI key)
python -m evaluation.eval_prompts

# Agent pipeline evaluation
python -m evaluation.eval_agents

# Evaluation sheet (extracted vs expected for 10 resumes)
python -m evaluation.evaluation_sheet
```

---

## Step 10: Set Up Tesseract OCR (Optional)

### Windows:
1. Download installer from: https://github.com/UB-Mannheim/tesseract/wiki
2. Install to `C:\Program Files\Tesseract-OCR\`
3. Set in `.env`: `TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe`

### macOS:
```bash
brew install tesseract
```

### Linux:
```bash
sudo apt-get install tesseract-ocr
```

---

## Project Structure

```
resume_parser/
├── manage.py                  # Django management
├── requirements.txt           # Python dependencies
├── pytest.ini                 # Test configuration
├── .env                       # Environment variables
├── resume_parser/             # Django project settings
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── api/                       # Django REST API app
│   ├── models.py              # Database models (SQLite)
│   ├── serializers.py         # API serializers
│   ├── views.py               # API views & processing pipeline
│   ├── urls.py                # API routes
│   ├── admin.py               # Admin panel configuration
│   ├── services/              # Business logic
│   │   ├── validator.py       # File validation
│   │   ├── parser.py          # Text extraction
│   │   ├── ocr.py             # OCR processing
│   │   ├── extractor.py       # Data extraction (LLM + regex)
│   │   ├── excel_storage.py   # Excel storage (primary data store)
│   │   ├── standardizer.py    # Resume standardization (DOCX output)
│   │   └── dataverse.py       # Dataverse client (optional, inactive)
│   ├── tests/                 # Unit tests
│   └── migrations/
├── evaluation/                # Evaluation & benchmarking
│   ├── eval_prompts.py        # LLM prompt accuracy tests
│   ├── eval_agents.py         # End-to-end pipeline tests
│   └── evaluation_sheet.py    # Extracted vs expected comparison
├── sample_data/               # 10 sample resumes for testing
│   └── sample_resumes/
├── docs/                      # Documentation
├── uploads/                   # Uploaded resume files (runtime)
├── outputs/                   # Standardized DOCX + Excel data (runtime)
└── templates/                 # Django templates
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| `No module named 'api'` | Ensure you're in the project root directory |
| Database errors | Run `python manage.py migrate` |
| Tesseract not found | Install Tesseract and set `TESSERACT_CMD` in `.env` |
| OpenAI errors | Verify API key and model name in `.env` |
| Port 8000 in use | Use `python manage.py runserver 8001` |
| Excel file locked | Close the file in other applications |
