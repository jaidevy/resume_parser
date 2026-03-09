"""
Streamlit Chat UI for Resume Parser & Standardization Agent.

Run:
    streamlit run streamlit_app.py

Requires the Django API server running at http://localhost:8000
"""
import os
import json
import time
import requests
import streamlit as st
from datetime import datetime

# ── Configuration ────────────────────────────────────────────────────────────
API_BASE_URL = os.getenv("RESUME_API_URL", "http://localhost:8000/api/v1")
SUPPORTED_EXTENSIONS = [".pdf", ".docx", ".rtf", ".txt", ".png", ".jpg", ".jpeg"]

# ── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Resume Parser Agent",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Chat-style messages */
    .chat-user {
        background: #e3f2fd;
        border-radius: 12px 12px 2px 12px;
        padding: 12px 16px;
        margin: 8px 0;
        max-width: 80%;
        margin-left: auto;
        color: #1a1a1a;
    }
    .chat-bot {
        background: #f5f5f5;
        border-radius: 12px 12px 12px 2px;
        padding: 12px 16px;
        margin: 8px 0;
        max-width: 80%;
        color: #1a1a1a;
    }
    /* Confidence bar */
    .confidence-bar {
        height: 8px;
        border-radius: 4px;
        margin: 2px 0;
    }
    .conf-high { background: linear-gradient(90deg, #4caf50, #66bb6a); }
    .conf-med  { background: linear-gradient(90deg, #ff9800, #ffb74d); }
    .conf-low  { background: linear-gradient(90deg, #f44336, #e57373); }
    /* Sidebar section headers */
    .sidebar-header {
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #888;
        margin-top: 16px;
        margin-bottom: 4px;
    }
    /* Field card */
    .field-card {
        background: #fafafa;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 10px 14px;
        margin: 6px 0;
    }
    /* Status badge */
    .status-badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .status-completed { background: #c8e6c9; color: #2e7d32; }
    .status-failed    { background: #ffcdd2; color: #c62828; }
    .status-pending   { background: #fff9c4; color: #f57f17; }
    .status-processing{ background: #bbdefb; color: #1565c0; }
    div[data-testid="stSidebar"] > div { padding-top: 1rem; }
</style>
""", unsafe_allow_html=True)


# ── Session State Initialization ─────────────────────────────────────────────
def init_session():
    defaults = {
        "messages": [],
        "current_record": None,
        "processing": False,
        "history": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()


# ── API Helpers ──────────────────────────────────────────────────────────────
def api_upload_resume(file) -> dict:
    """Upload a resume file to the Django API and return the response."""
    try:
        resp = requests.post(
            f"{API_BASE_URL}/resumes/",
            files={"file": (file.name, file.getvalue(), file.type or "application/octet-stream")},
            data={"source": "upload"},
            timeout=120,
        )
        return resp.json() if resp.status_code in (200, 201) else {"error": resp.text, "status_code": resp.status_code}
    except requests.ConnectionError:
        return {"error": "Cannot connect to the API server. Make sure the Django server is running at " + API_BASE_URL}
    except Exception as e:
        return {"error": str(e)}


def api_get_record(record_id: str) -> dict:
    try:
        resp = requests.get(f"{API_BASE_URL}/resumes/{record_id}/", timeout=30)
        return resp.json() if resp.ok else {}
    except Exception:
        return {}


def api_get_logs(record_id: str) -> list:
    try:
        resp = requests.get(f"{API_BASE_URL}/resumes/{record_id}/logs/", timeout=30)
        return resp.json() if resp.ok else []
    except Exception:
        return []


def api_get_field_confidences(record_id: str) -> dict:
    try:
        resp = requests.get(f"{API_BASE_URL}/resumes/{record_id}/field_confidences/", timeout=30)
        return resp.json() if resp.ok else {}
    except Exception:
        return {}


def api_get_download_url(record_id: str) -> str:
    return f"{API_BASE_URL}/resumes/{record_id}/download/"


def api_get_text_preview(record_id: str) -> str:
    try:
        resp = requests.get(f"{API_BASE_URL}/resumes/{record_id}/text_preview/", timeout=30)
        if resp.ok:
            return resp.json().get("text", "")
    except Exception:
        pass
    return ""


def api_health() -> dict:
    try:
        resp = requests.get(f"{API_BASE_URL}/health/", timeout=5)
        return resp.json() if resp.ok else {"status": "unreachable"}
    except Exception:
        return {"status": "unreachable"}


def api_list_resumes() -> list:
    try:
        resp = requests.get(f"{API_BASE_URL}/resumes/", timeout=15)
        if resp.ok:
            data = resp.json()
            return data.get("results", data) if isinstance(data, dict) else data
    except Exception:
        pass
    return []


def add_message(role: str, content: str, data: dict = None):
    st.session_state.messages.append({
        "role": role,
        "content": content,
        "data": data,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    })


def confidence_color(score: float) -> str:
    if score >= 0.7:
        return "conf-high"
    elif score >= 0.4:
        return "conf-med"
    return "conf-low"


def confidence_label(score: float) -> str:
    if score >= 0.9:
        return "Very High"
    elif score >= 0.7:
        return "High"
    elif score >= 0.5:
        return "Medium"
    elif score >= 0.3:
        return "Low"
    return "Very Low"


def format_field_name(name: str) -> str:
    return name.replace("_", " ").title()


# ── Sidebar ──────────────────────────────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.markdown("## 📄 Resume Parser")
        st.caption("AI-powered resume extraction & standardization")

        # ── API Status ───────────────────────────────────────────────
        health = api_health()
        if health.get("status") == "healthy":
            st.success("API Connected", icon="✅")
        else:
            st.error("API Unreachable — Start the Django server", icon="❌")

        st.divider()

        # ── History / Previous Resumes ───────────────────────────────
        st.markdown('<p class="sidebar-header">Previous Resumes</p>', unsafe_allow_html=True)
        records = api_list_resumes()
        if records:
            for rec in records[:10]:
                status_cls = "status-completed" if rec.get("status") == "completed" else (
                    "status-failed" if rec.get("status") == "failed" else "status-pending"
                )
                col1, col2 = st.columns([3, 1])
                with col1:
                    fname = rec.get("original_file_name", "Unknown")
                    if len(fname) > 28:
                        fname = fname[:25] + "..."
                    if st.button(f"{fname}", key=f"hist_{rec['id']}", use_container_width=True):
                        load_record(rec["id"])
                with col2:
                    st.markdown(
                        f'<span class="status-badge {status_cls}">{rec.get("status", "?")}</span>',
                        unsafe_allow_html=True,
                    )
        else:
            st.caption("No resumes uploaded yet")

        st.divider()

        # ── Metadata Panel (shown when a record is loaded) ──────────
        record = st.session_state.current_record
        if record:
            render_sidebar_metadata(record)


def render_sidebar_metadata(record: dict):
    """Render all metadata about the current record in the sidebar."""
    record_id = record.get("id", "")

    # ── Record Info ──────────────────────────────────────────────
    st.markdown('<p class="sidebar-header">Record Info</p>', unsafe_allow_html=True)
    st.markdown(f"**File:** {record.get('original_file_name', 'N/A')}")
    st.markdown(f"**Type:** `{record.get('file_type', 'N/A')}`")
    size_kb = (record.get("file_size_bytes", 0) or 0) / 1024
    st.markdown(f"**Size:** {size_kb:.1f} KB")
    st.markdown(f"**Source:** {record.get('resume_source', 'N/A')}")
    st.markdown(f"**Version:** {record.get('version', 1)}")
    st.markdown(f"**Status:** {record.get('status', 'N/A')}")
    if record.get("created_at"):
        st.markdown(f"**Created:** {record['created_at'][:19]}")
    if record.get("processed_at"):
        st.markdown(f"**Processed:** {record['processed_at'][:19]}")

    st.divider()

    # ── Overall Confidence ───────────────────────────────────────
    st.markdown('<p class="sidebar-header">Overall Confidence</p>', unsafe_allow_html=True)
    overall = record.get("extraction_confidence", 0)
    st.metric("Extraction Confidence", f"{overall:.0%}")
    st.progress(min(overall, 1.0))
    st.caption(confidence_label(overall))

    st.divider()

    # ── Per-Field Confidence Scores ──────────────────────────────
    st.markdown('<p class="sidebar-header">Field Confidence Scores</p>', unsafe_allow_html=True)
    field_conf = record.get("field_confidences") or {}
    if not field_conf and record_id:
        field_conf = api_get_field_confidences(record_id)

    if field_conf:
        # Sort by confidence ascending so low-confidence fields are visible first
        sorted_fields = sorted(
            field_conf.items(),
            key=lambda x: x[1].get("confidence", 0) if isinstance(x[1], dict) else x[1],
        )
        for field_name, info in sorted_fields:
            if isinstance(info, dict):
                conf = info.get("confidence", 0)
                is_missing = info.get("is_missing", False)
                quality_warning = info.get("quality_warning", "")
            else:
                conf = float(info)
                is_missing = conf < 0.3
                quality_warning = ""

            col1, col2 = st.columns([3, 1])
            with col1:
                label = format_field_name(field_name)
                if is_missing:
                    label += " ⚠️"
                st.caption(label)
                st.markdown(
                    f'<div class="confidence-bar {confidence_color(conf)}" '
                    f'style="width:{max(conf * 100, 5):.0f}%"></div>',
                    unsafe_allow_html=True,
                )
            with col2:
                st.caption(f"{conf:.0%}")

            if quality_warning:
                st.warning(quality_warning, icon="⚠️")
    else:
        st.caption("No field-level confidence data available")

    st.divider()

    # ── Quality Notes ────────────────────────────────────────────
    quality_notes = record.get("field_quality_notes") or {}
    if quality_notes:
        st.markdown('<p class="sidebar-header">⚠️ Quality Warnings</p>', unsafe_allow_html=True)
        for field, note in quality_notes.items():
            st.warning(f"**{format_field_name(field)}:** {note}", icon="⚠️")
        st.divider()

    # ── Processing Logs ──────────────────────────────────────────
    st.markdown('<p class="sidebar-header">Processing Logs</p>', unsafe_allow_html=True)
    if record_id:
        logs = api_get_logs(record_id)
        if logs:
            for log in logs[:20]:
                icon = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "debug": "🔍"}.get(
                    log.get("level", "info"), "ℹ️"
                )
                ts = log.get("timestamp", "")[:19]
                step = log.get("step", "")
                msg = log.get("message", "")
                with st.expander(f"{icon} [{step}] {msg[:50]}{'…' if len(msg)>50 else ''}", expanded=False):
                    st.caption(f"**Time:** {ts}")
                    st.caption(f"**Level:** {log.get('level', 'info')}")
                    st.caption(f"**Step:** {step}")
                    st.write(msg)
                    if log.get("details"):
                        st.json(log["details"])
        else:
            st.caption("No processing logs available")

    # ── Error Info ────────────────────────────────────────────────
    if record.get("error_message"):
        st.divider()
        st.markdown('<p class="sidebar-header">Error Details</p>', unsafe_allow_html=True)
        st.error(record["error_message"])


def load_record(record_id: str):
    """Load a record from history and display it in the chat."""
    record = api_get_record(record_id)
    if record:
        st.session_state.current_record = record
        st.session_state.messages = []
        add_message("assistant", f"Loaded resume: **{record.get('original_file_name', 'Unknown')}**")
        if record.get("extracted_data"):
            add_message("assistant", "Here are the extracted details:", data=record)
        st.rerun()


# ── Extracted Data Display ───────────────────────────────────────────────────
def render_extracted_data(record: dict):
    """Render structured extracted data in a visually appealing layout."""
    data = record.get("extracted_data", {})
    if not data:
        st.info("No extracted data available for this resume.")
        return

    # ── Personal Info Section ────────────────────────────────────
    st.markdown("### Personal Information")
    cols = st.columns(2)
    with cols[0]:
        st.markdown(f"**Name:** {data.get('candidate_full_name', 'N/A')}")
        emails = data.get("email_ids", [])
        if emails:
            st.markdown(f"**Email:** {', '.join(emails) if isinstance(emails, list) else emails}")
        phones = data.get("phones", [])
        if phones:
            st.markdown(f"**Phone:** {', '.join(phones) if isinstance(phones, list) else phones}")
    with cols[1]:
        st.markdown(f"**Location:** {data.get('current_location', 'N/A')}")
        st.markdown(f"**Gender:** {data.get('gender', 'N/A') or 'Not specified'}")
        st.markdown(f"**Total Experience:** {data.get('total_experience', 'N/A')}")

    # ── Links ────────────────────────────────────────────────────
    links = []
    if data.get("linkedin_url"):
        links.append(f"[LinkedIn]({data['linkedin_url']})")
    if data.get("github_url"):
        links.append(f"[GitHub]({data['github_url']})")
    if data.get("portfolio_url"):
        links.append(f"[Portfolio]({data['portfolio_url']})")
    if links:
        st.markdown("**Links:** " + " · ".join(links))

    # ── Geo Details ──────────────────────────────────────────────
    geo = data.get("geo_details", {})
    if geo and isinstance(geo, dict) and any(geo.values()):
        parts = [v for v in [geo.get("city"), geo.get("state"), geo.get("country")] if v]
        if parts:
            st.markdown(f"**Geo:** {', '.join(parts)}")

    st.divider()

    # ── Professional Summary ─────────────────────────────────────
    summary = data.get("professional_summary", "")
    if summary:
        st.markdown("### Professional Summary")
        st.markdown(summary)
        st.divider()

    # ── Key Skills ───────────────────────────────────────────────
    skills = data.get("key_skills", [])
    if skills:
        st.markdown("### Key Skills")
        # Display as tag-style chips
        cols = st.columns(min(len(skills), 5))
        chunk_size = max(1, len(skills) // 5 + 1)
        for i, col in enumerate(cols):
            with col:
                for skill in skills[i * chunk_size: (i + 1) * chunk_size]:
                    st.markdown(f"• {skill}")
        st.divider()

    # ── Work Experience ──────────────────────────────────────────
    experience = data.get("work_experience", [])
    if experience:
        st.markdown("### Work Experience")
        for i, exp in enumerate(experience):
            if isinstance(exp, dict):
                role = exp.get("role", exp.get("title", "Unknown Role"))
                company = exp.get("company", "Unknown Company")
                start = exp.get("start_date", "")
                end = exp.get("end_date", "")
                duration = exp.get("duration", "")

                date_str = f"{start} – {end}" if start or end else ""
                if duration:
                    date_str += f" ({duration})" if date_str else duration

                with st.expander(f"**{role}** at {company} {' · ' + date_str if date_str else ''}", expanded=i == 0):
                    responsibilities = exp.get("responsibilities", [])
                    if responsibilities:
                        st.markdown("**Responsibilities:**")
                        for r in responsibilities:
                            st.markdown(f"  - {r}")

                    achievements = exp.get("achievements", [])
                    if achievements:
                        st.markdown("**Achievements:**")
                        for a in achievements:
                            st.markdown(f"  - 🏆 {a}")

                    techs = exp.get("technologies", [])
                    if techs:
                        st.markdown(f"**Technologies:** {', '.join(techs)}")
            else:
                st.markdown(f"- {exp}")
        st.divider()

    # ── Education ────────────────────────────────────────────────
    education = data.get("education", [])
    if education:
        st.markdown("### Education")
        for edu in education:
            if isinstance(edu, dict):
                degree = edu.get("degree", "")
                field = edu.get("field_of_study", "")
                inst = edu.get("institution", "Unknown")
                start_y = edu.get("start_year", "")
                end_y = edu.get("end_year", "")
                grade = edu.get("grade", "")

                title = f"{degree}"
                if field:
                    title += f" in {field}"
                year_str = f"{start_y}–{end_y}" if start_y or end_y else ""

                st.markdown(f"**{title}** — {inst}")
                extras = []
                if year_str:
                    extras.append(year_str)
                if grade:
                    extras.append(f"Grade: {grade}")
                if extras:
                    st.caption(" · ".join(extras))
            else:
                st.markdown(f"- {edu}")
        st.divider()

    # ── Certifications ───────────────────────────────────────────
    certs = data.get("certifications", [])
    if certs:
        st.markdown("### Certifications")
        for cert in certs:
            st.markdown(f"- {cert}")
        st.divider()

    # ── Projects ─────────────────────────────────────────────────
    projects = data.get("projects", [])
    if projects:
        st.markdown("### Projects")
        for proj in projects:
            if isinstance(proj, dict):
                name = proj.get("name", proj.get("title", "Unnamed Project"))
                desc = proj.get("description", "")
                techs = proj.get("technologies", [])
                with st.expander(f"**{name}**"):
                    if desc:
                        st.write(desc)
                    if techs:
                        st.markdown(f"**Tech:** {', '.join(techs)}")
            else:
                st.markdown(f"- {proj}")
        st.divider()

    # ── Languages Known ──────────────────────────────────────────
    languages = data.get("languages_known", [])
    if languages:
        st.markdown("### Languages")
        st.markdown(", ".join(languages))


# ── Chat Message Renderer ───────────────────────────────────────────────────
def render_chat():
    """Render the chat message history."""
    for msg_idx, msg in enumerate(st.session_state.messages):
        role = msg["role"]
        content = msg["content"]
        ts = msg.get("timestamp", "")

        if role == "user":
            with st.chat_message("user", avatar="👤"):
                st.markdown(content)
                st.caption(ts)
        else:
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(content)
                # If message contains record data, render the full extracted view
                if msg.get("data"):
                    record = msg["data"]
                    render_extracted_data(record)

                    # Download button
                    record_id = record.get("id", "")
                    if record.get("status") == "completed" and record_id:
                        st.markdown("---")
                        cols = st.columns([2, 1, 1])
                        with cols[0]:
                            download_url = api_get_download_url(record_id)
                            st.markdown(f"### [Download Standardized Resume]({download_url})")
                        with cols[1]:
                            if st.button("Text Preview", key=f"preview_{msg_idx}_{record_id}"):
                                text = api_get_text_preview(record_id)
                                if text:
                                    st.text_area("Standardized Resume (Text)", text, height=400)
                                else:
                                    st.warning("Text preview not available")
                        with cols[2]:
                            if st.button("Refresh", key=f"refresh_{msg_idx}_{record_id}"):
                                load_record(record_id)

                st.caption(ts)


# ── Main Application ─────────────────────────────────────────────────────────
def main():
    render_sidebar()

    # ── Header ───────────────────────────────────────────────────
    st.title("Resume Parser Agent")
    st.caption("Upload a resume to extract structured data and generate a standardized document")

    # ── Welcome message ──────────────────────────────────────────
    if not st.session_state.messages:
        add_message(
            "assistant",
            "Hello! I'm the Resume Parser Agent.\n\n"
            "**Upload a resume** using the file uploader below and I'll:\n"
            "1. Validate the file format\n"
            "2. Extract all structured information\n"
            "3. Store the data\n"
            "4. Generate a standardized resume\n\n"
            "Supported formats: **PDF, DOCX, DOC, RTF, TXT, PNG, JPG**\n\n"
            "Check the **sidebar** for metadata, confidence scores, and processing logs.",
        )

    # ── Render chat history ──────────────────────────────────────
    render_chat()

    # ── File Upload Area ─────────────────────────────────────────
    st.divider()
    uploaded_file = st.file_uploader(
        "📎 Upload a resume",
        type=[ext.lstrip(".") for ext in SUPPORTED_EXTENSIONS],
        help="Supported: PDF, DOCX, DOC, RTF, TXT, PNG, JPG (max 10 MB)",
        key="file_uploader",
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        process_btn = st.button(
            "Process Resume",
            type="primary",
            disabled=uploaded_file is None or st.session_state.processing,
            use_container_width=True,
        )

    if process_btn and uploaded_file:
        st.session_state.processing = True

        # User message
        size_kb = uploaded_file.size / 1024
        add_message("user", f"Uploaded **{uploaded_file.name}** ({size_kb:.1f} KB)")

        # Processing message
        add_message("assistant", "Processing your resume… This may take a moment.")

        # Show processing spinner
        with st.spinner("Validating, extracting, and standardizing your resume..."):
            result = api_upload_resume(uploaded_file)

        if "error" in result and not result.get("id"):
            add_message("assistant", f"**Error:** {result['error']}")
            st.session_state.processing = False
            st.rerun()
        else:
            record_id = result.get("id", "")
            # Fetch full record details
            record = api_get_record(record_id) if record_id else result
            if not record.get("extracted_data") and result.get("extracted_data"):
                record = result

            st.session_state.current_record = record

            # Remove the "processing" message
            st.session_state.messages = [
                m for m in st.session_state.messages
                if "Processing your resume" not in m.get("content", "")
            ]

            status_val = record.get("status", "unknown")
            confidence = record.get("extraction_confidence", 0)
            name = (record.get("extracted_data") or {}).get("candidate_full_name", "Unknown Candidate")

            if status_val == "completed":
                add_message(
                    "assistant",
                    f"**Resume processed successfully!**\n\n"
                    f"**Candidate:** {name}\n"
                    f"**Confidence:** {confidence:.0%} {confidence_label(confidence)}\n\n"
                    f"Here are the extracted details:",
                    data=record,
                )
            elif status_val == "failed":
                add_message(
                    "assistant",
                    f"Processing completed with errors.\n\n"
                    f"**Error:** {record.get('error_message', 'Unknown error')}\n\n"
                    f"Partial data may be available below:",
                    data=record if record.get("extracted_data") else None,
                )
            else:
                add_message(
                    "assistant",
                    f"Processing status: **{status_val}**\n\n"
                    f"The resume may still be processing. Check back shortly.",
                    data=record if record.get("extracted_data") else None,
                )

            # Save to history
            if record_id and record_id not in [h.get("id") for h in st.session_state.history]:
                st.session_state.history.append({
                    "id": record_id,
                    "name": record.get("original_file_name", uploaded_file.name),
                    "status": status_val,
                })

            st.session_state.processing = False
            st.rerun()

    # ── Chat Input for Questions ─────────────────────────────────
    user_input = st.chat_input("Ask about the extracted data or upload another resume...")
    if user_input:
        add_message("user", user_input)
        # Simple Q&A based on current record
        record = st.session_state.current_record
        if record and record.get("extracted_data"):
            data = record["extracted_data"]
            answer = handle_user_question(user_input, data, record)
            add_message("assistant", answer)
        else:
            add_message("assistant", "Please upload a resume first so I can answer questions about it.")
        st.rerun()


def handle_user_question(question: str, data: dict, record: dict) -> str:
    """Handle free-text questions about the extracted data."""
    q = question.lower().strip()

    if any(w in q for w in ["name", "who", "candidate"]):
        return f"The candidate's name is **{data.get('candidate_full_name', 'N/A')}**."

    if any(w in q for w in ["email", "mail"]):
        emails = data.get("email_ids", [])
        return f"Email(s): **{', '.join(emails)}**" if emails else "No email addresses found."

    if any(w in q for w in ["phone", "call", "mobile", "number"]):
        phones = data.get("phones", [])
        return f"Phone(s): **{', '.join(phones)}**" if phones else "No phone numbers found."

    if any(w in q for w in ["skill", "technology", "tech"]):
        skills = data.get("key_skills", [])
        return f"**Key Skills:** {', '.join(skills)}" if skills else "No skills extracted."

    if any(w in q for w in ["experience", "work", "job", "company"]):
        exp = data.get("work_experience", [])
        if exp:
            lines = []
            for e in exp:
                if isinstance(e, dict):
                    lines.append(f"- **{e.get('role', 'N/A')}** at {e.get('company', 'N/A')}")
                else:
                    lines.append(f"- {e}")
            return f"**Work Experience:**\n" + "\n".join(lines)
        return "No work experience extracted."

    if any(w in q for w in ["education", "degree", "university", "college"]):
        edu = data.get("education", [])
        if edu:
            lines = []
            for e in edu:
                if isinstance(e, dict):
                    lines.append(f"- **{e.get('degree', 'N/A')}** from {e.get('institution', 'N/A')}")
                else:
                    lines.append(f"- {e}")
            return "**Education:**\n" + "\n".join(lines)
        return "No education data extracted."

    if any(w in q for w in ["certif", "certificate"]):
        certs = data.get("certifications", [])
        return f"**Certifications:** {', '.join(certs)}" if certs else "No certifications found."

    if any(w in q for w in ["summary", "profile", "about"]):
        return data.get("professional_summary", "No professional summary available.")

    if any(w in q for w in ["confidence", "score", "accuracy"]):
        conf = record.get("extraction_confidence", 0)
        return f"Overall extraction confidence: **{conf:.0%}** {confidence_label(conf)}"

    if any(w in q for w in ["location", "city", "country", "where"]):
        loc = data.get("current_location", "N/A")
        geo = data.get("geo_details", {})
        geo_str = ""
        if geo:
            geo_str = " (" + ", ".join(f"{k}: {v}" for k, v in geo.items() if v) + ")"
        return f"**Location:** {loc}{geo_str}"

    if any(w in q for w in ["download", "standardized", "docx", "document"]):
        record_id = record.get("id", "")
        if record_id:
            url = api_get_download_url(record_id)
            return f"[Download the standardized resume]({url})"
        return "No standardized document available yet."

    if any(w in q for w in ["link", "linkedin", "github", "portfolio"]):
        links = []
        if data.get("linkedin_url"):
            links.append(f"[LinkedIn]({data['linkedin_url']})")
        if data.get("github_url"):
            links.append(f"[GitHub]({data['github_url']})")
        if data.get("portfolio_url"):
            links.append(f"[Portfolio]({data['portfolio_url']})")
        return " · ".join(links) if links else "No profile links found."

    if any(w in q for w in ["project"]):
        projects = data.get("projects", [])
        if projects:
            lines = []
            for p in projects:
                if isinstance(p, dict):
                    lines.append(f"- **{p.get('name', p.get('title', 'N/A'))}**: {p.get('description', '')[:100]}")
                else:
                    lines.append(f"- {p}")
            return "**Projects:**\n" + "\n".join(lines)
        return "No projects found."

    if any(w in q for w in ["all", "everything", "full", "complete"]):
        return (
            f"Here's a complete summary:\n\n"
            f"**Name:** {data.get('candidate_full_name', 'N/A')}\n"
            f"**Email:** {', '.join(data.get('email_ids', []))}\n"
            f"**Phone:** {', '.join(data.get('phones', []))}\n"
            f"**Location:** {data.get('current_location', 'N/A')}\n"
            f"**Experience:** {data.get('total_experience', 'N/A')}\n"
            f"**Skills:** {', '.join(data.get('key_skills', [])[:10])}\n"
            f"**Education:** {len(data.get('education', []))} entries\n"
            f"**Work Experience:** {len(data.get('work_experience', []))} roles\n"
            f"**Confidence:** {record.get('extraction_confidence', 0):.0%}"
        )

    return (
        "I can answer questions about the extracted resume data. Try asking about:\n"
        "- **Name**, **email**, **phone**, **location**\n"
        "- **Skills**, **experience**, **education**\n"
        "- **Certifications**, **projects**, **summary**\n"
        "- **Confidence scores**, **download link**\n"
        "- **Everything** — for a full summary"
    )


if __name__ == "__main__":
    main()
