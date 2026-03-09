# Section 7: Agent / Automation Choice Documentation

## Chosen Approach

**Django REST Framework + OpenAI GPT API + Local Excel Storage**

## Why Not the Suggested Options?

The assignment suggests three implementation approaches:

| Option | Reason Not Chosen |
|---|---|
| **Copilot Studio + Power Automate** | Requires a Microsoft 365 Business/Enterprise license with Power Platform access. Not available — no Microsoft business account. |
| **Azure OpenAI + Logic Apps/Functions** | Requires an Azure subscription with Azure OpenAI Service access (which requires separate approval). Logic Apps are a paid Azure resource. Not available due to licensing constraints. |
| **Power Apps + Power Automate + AI Builder** | Requires Power Platform premium licensing and AI Builder credits. Not available — no Microsoft business account. |

> **Constraint:** The developer does not have a Microsoft 365 Business account, which is a prerequisite for Copilot Studio, Power Automate, AI Builder, Dataverse, and SharePoint Online connectors.

## Why Django + OpenAI?

### 1. Functional Equivalence
The chosen stack fulfills **every requirement** of the assignment without depending on Microsoft business licensing:

| Assignment Requirement | Our Implementation |
|---|---|
| Resume ingestion (upload) | Django REST API with `MultiPartParser` |
| Resume ingestion (email) | Webhook endpoint ready for Power Automate / Zapier / any email automation |
| File validation | Custom `FileValidator` service (type, size, readability, OCR detection) |
| AI-powered extraction | OpenAI GPT API with structured JSON schema prompts |
| Data storage | Local Excel file (`.xlsx`) via `openpyxl` — functionally equivalent to Excel on OneDrive |
| Standardized resume output | `.docx` generation via `python-docx` |
| Processing logs & audit | Database logging + Excel `ProcessingLogs` sheet |
| Duplicate handling | Candidate ID-based upsert logic |
| API documentation | Swagger/OpenAPI via `drf-yasg` |

### 2. Portability
- The architecture is **self-contained** — runs on any machine with Python 3.10+.
- No vendor lock-in to Microsoft cloud services.
- Can be deployed to any hosting platform (Azure App Service, AWS, local server).

### 3. Migration Path to Microsoft Stack
The design is intentionally **compatible** with a future Microsoft integration:

```
Current                          Future (with M365 license)
─────────────────────────────    ─────────────────────────────
Django REST API            →     Power Apps front-end
OpenAI GPT API             →     Azure OpenAI Service
Local Excel (.xlsx)        →     Excel on SharePoint / Dataverse
Webhook endpoint           →     Power Automate flow trigger
Local file storage         →     SharePoint Document Library
```

- The **Excel schema** mirrors what would be used in SharePoint/Dataverse.
- The **webhook endpoint** (`/api/webhook/power-automate/`) is already shaped for Power Automate HTTP triggers.
- The **extraction JSON contract** can be reused as-is with Azure OpenAI.

### 4. Cost
- **$0 infrastructure cost** for development and testing (runs locally).
- Only cost is OpenAI API usage (~$0.01–$0.05 per resume with GPT-4o-mini).

## Architecture Summary

```
┌──────────────────────────────────────────────────┐
│                   Client / User                  │
│         (Browser, Postman, Power Automate)        │
└──────────────┬───────────────────┬───────────────┘
               │ Upload            │ Webhook
               ▼                   ▼
┌──────────────────────────────────────────────────┐
│              Django REST API                     │
│         (ViewSet + Swagger Docs)                 │
├──────────────────────────────────────────────────┤
│  FileValidator → ResumeParser → ResumeExtractor  │
│                                  (OpenAI GPT)    │
│  → ExcelStorageClient → ResumeStandardizer       │
│                          (.docx output)          │
├──────────────────────────────────────────────────┤
│  SQLite DB          │  Excel File (.xlsx)        │
│  (records + logs)   │  (extracted data + logs)   │
└──────────────────────────────────────────────────┘
```

## Conclusion

This approach was chosen due to **licensing constraints** (no Microsoft 365 Business account). It delivers full functional coverage of the assignment requirements using open-source and widely available tools, while maintaining a clear migration path to the Microsoft stack if enterprise licensing becomes available.