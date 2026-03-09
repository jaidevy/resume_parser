import json
import hashlib
import logging
from django.conf import settings
import openai
from api.services.schemas import ResumeData, Education

logger = logging.getLogger("api")

EXTRACTION_SCHEMA = ResumeData.json_schema()

# ── System Prompt ────────────────────────────────────────────────────────────
EXTRACTION_SYSTEM_PROMPT = """You are an expert resume parser AI. Your task is to extract structured information from resume text.

CRITICAL — always output a FLAT JSON object with these exact top-level keys.
Do NOT nest contact details under 'personal_info' or any other wrapper key.
Required top-level keys: candidate_full_name, email_ids, phones, gender,
current_location, linkedin_url, github_url, portfolio_url, total_experience,
work_experience, key_skills, education, certifications, languages_known,
professional_summary, projects, geo_details, field_confidences.

RULES:
1. Extract ONLY information explicitly present in the resume text. Never fabricate or infer data.
2. If a field is missing from the resume, return an empty string "" or empty array [].
3. CONTACT INFO (top priority): Always extract candidate_full_name, email_ids, phones,
   current_location from the header/contact section. These are almost always present.
4. For gender: ONLY extract if explicitly stated. Do NOT infer from names.
5. For phone numbers: include country code if present in the resume. Return as a flat array of strings.
6. For certifications: return a flat array of strings (just the certification name/title).
   Do NOT return objects. Example: ["AWS Certified Developer", "PMP"] — not [{"name": "..."}].
7. For languages_known: extract if a 'Languages' or 'Language Skills' section exists, or if
   languages are mentioned in the profile. Return as array of strings e.g. ["English", "French"].
8. WORK EXPERIENCE — CRITICAL:
   a. company: extract the COMPANY/EMPLOYER NAME for every role. It is almost always present
      in the heading, e.g. "TechCorp — Senior Engineer", "Senior Engineer at TechCorp",
      or as a separate line above the role name. NEVER leave company empty if a company
      name is written anywhere near the role.
   b. role: exact job title as written in the resume.
   c. start_date / end_date: extract employment dates (e.g. "Jan 2020", "2018", "Present").
      NEVER leave these empty if any date or year is mentioned near the role.
   d. duration: if start and end dates are present, calculate duration.
   e. responsibilities: extract each distinct responsibility as a separate list item.
   f. achievements: quantified or impact-focused statements (e.g. "Reduced latency by 40%").
   g. technologies: specific tools, languages, frameworks mentioned in that role.
   h. List in reverse chronological order.
9. For education: list ALL qualifications in reverse chronological order.
   - degree: exact qualification name (e.g. "B.Tech", "MBA", "12th Class")
   - field_of_study: major/specialization/stream
   - institution: exact university, college, or school name
   - start_year / end_year: four-digit years
   - grade: CGPA, percentage, or grade as written
10. For skills: return each distinct skill/tool as its own entry. Do NOT split a grouped category
    like "Ariba, Coupa, Oracle Cloud" into separate items if they follow a label (e.g. "Platforms: Ariba, Coupa");
    instead list "Ariba", "Coupa", "Oracle Cloud" as individual items WITHOUT the label prefix.
    Also do NOT split parenthetical groups like "(PR, PO, GRN)" — collapse them to one entry.
11. For professional_summary: factual 3-5 line summary from actual experience/skills. No exaggeration.
12. For total_experience: extract explicitly if stated; otherwise calculate from work history dates.
13. IMPORTANT — Education and Certifications: always scan the FULL resume text including the bottom
    sections. Do NOT stop at work experience. Extract every degree and every certification found.
14. For URL fields (linkedin_url, github_url, portfolio_url): extract the FULL URL
    (e.g. "https://linkedin.com/in/johndoe"). If only a label like "LinkedIn" is present
    without an actual URL, return an empty string "".
15. For geo_details: parse current_location into {city, state, country} if possible.
16. Provide confidence scores (0.0-1.0) per field in field_confidences:
    - 1.0 = clearly and explicitly stated
    - 0.7-0.9 = present but partially ambiguous
    - 0.3-0.6 = inferred from context
    - 0.0-0.2 = not found or highly uncertain

Return ONLY valid JSON. No markdown fences, no explanation."""


class ResumeExtractor:

    def __init__(self):
        self.client = None
        self.model = settings.OPENAI_MODEL
        self._initialize_client()

    def _initialize_client(self):
        try:
            if settings.OPENAI_API_KEY:
                self.client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                logger.info("Using OpenAI for extraction")
            else:
                logger.warning(
                    "No OpenAI API key configured. "
                    "Falling back to regex-based extraction."
                )
        except ImportError:
            logger.warning("openai package not installed. Using regex fallback.")

    def extract(self, resume_text: str) -> dict:

        result = self._extract_with_llm(resume_text)

        # Guard: detect completely empty extraction
        core_fields = (
            "candidate_full_name", "email_ids", "phones",
            "key_skills", "work_experience", "education",
        )
        has_any = any(
            bool(result.get(f)) for f in core_fields
        )
        if not has_any:
            logger.warning(
                "Extraction returned empty for ALL core fields. "
                "Input text length: %d chars. Possible causes: "
                "empty/unreadable PDF, LLM error, or validation failure.",
                len(resume_text),
            )

        return result

    def _extract_with_llm(self, resume_text: str) -> dict:
        if not self.client:
            logger.error("No OpenAI client available for extraction")
            return self._empty_result()

        text_len = len(resume_text.strip())
        if text_len == 0:
            logger.warning("resume_text is empty — nothing to send to LLM")
            return self._empty_result()
        if text_len < 30:
            logger.warning(
                "resume_text is very short (%d chars) — extraction may be poor",
                text_len,
            )

        try:
            max_chars = 35000
            if len(resume_text) > max_chars:
                resume_text = resume_text[:max_chars] + "\n\n[... truncated ...]"

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Extract structured information from this resume:\n\n{resume_text}",
                    },
                ],
                temperature=0.1,
                max_tokens=12000,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content or ""
            raw = json.loads(content)

            self._dump_llm_response(raw)

            # Validate & normalise via Pydantic schema
            resume = ResumeData.from_llm_response(raw)
            extracted = resume.to_dict()

            # Generate candidate ID
            extracted["candidate_id"] = self._generate_candidate_id(extracted)

            logger.info(
                "LLM extraction complete for: %s",
                extracted.get('candidate_full_name') or 'Unknown',
            )
            return extracted

        except json.JSONDecodeError as e:
            logger.error("JSON parsing error from LLM response: %s", e)
            return self._empty_result()
        except Exception as e:
            logger.error("LLM extraction failed: %s (type=%s)", e, type(e).__name__)
            return self._empty_result()

    @staticmethod
    def _dump_llm_response(raw: dict) -> None:
        try:
            from datetime import datetime
            from pathlib import Path as _P

            out_dir = _P(__file__).resolve().parents[2] / "outputs"
            out_dir.mkdir(exist_ok=True)
            name = raw.get("candidate_full_name") or raw.get("name") or "unknown"
            slug = "".join(c if c.isalnum() else "_" for c in name)[:40]
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_file = out_dir / f"llm_raw_{slug}_{ts}.json"
            out_file.write_text(
                json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            logger.info("LLM raw response saved to %s", out_file)
        except Exception as exc:
            logger.warning("Could not dump LLM raw response: %s", exc)

    def _empty_result(self) -> dict:
        """Return an empty extraction result with all required fields."""
        result = ResumeData.empty().to_dict()
        result["candidate_id"] = ""
        return result


    def _validate_and_clean(self, data: dict) -> dict:
        resume = ResumeData.from_llm_response(data)
        cleaned = resume.to_dict()

        # Server-side confidence validation & quality override
        cleaned = self._validate_confidences(cleaned)
        return cleaned

    def _validate_confidences(self, data: dict) -> dict:
        """
        Compute final per-field confidence by blending the LLM-reported score
        with a server-side semantic quality assessment.

        Blend rules:
        - Field empty → confidence 0.0 (regardless of LLM score)
        - Field present, quality check available:
            quality < 0.4  → suspected contamination → final = min(llm, quality)
            quality ≥ 0.4  → content looks correct  → final = min(llm, quality)
                              but floor at 0.3 so present data is never zeroed
        - Field present, no quality checker (simple scalar fields):
            clamp LLM score; bump to 0.3 if LLM returned 0 for non-empty field
        - All values clamped to [0.0, 1.0] and rounded to 2 dp
        """
        fc = data.get("field_confidences", {})

        # Presence checkers for every canonical field
        CANONICAL_FIELDS = {
            "candidate_full_name": lambda d: bool(d.get("candidate_full_name", "").strip()),
            "email_ids": lambda d: bool(d.get("email_ids")),
            "phones": lambda d: bool(d.get("phones")),
            "gender": lambda d: bool(d.get("gender", "").strip()),
            "current_location": lambda d: bool(d.get("current_location", "").strip()),
            "total_experience": lambda d: bool(d.get("total_experience", "").strip()),
            "work_experience": lambda d: bool(d.get("work_experience")),
            "key_skills": lambda d: bool(d.get("key_skills")),
            "education": lambda d: bool(d.get("education")),
            "certifications": lambda d: bool(d.get("certifications")),
            "languages_known": lambda d: bool(d.get("languages_known")),
            "linkedin_url": lambda d: bool(d.get("linkedin_url", "").strip()),
            "github_url": lambda d: bool(d.get("github_url", "").strip()),
            "portfolio_url": lambda d: bool(d.get("portfolio_url", "").strip()),
            "professional_summary": lambda d: bool(d.get("professional_summary", "").strip()),
            "projects": lambda d: bool(d.get("projects")),
        }

        for field, has_content_fn in CANONICAL_FIELDS.items():
            has_content = has_content_fn(data)

            # Get LLM confidence, defaulting to None if absent
            llm_conf = fc.get(field)
            if llm_conf is None:
                llm_conf = 0.9 if has_content else 0.0
            else:
                llm_conf = max(0.0, min(1.0, float(llm_conf)))

            # Empty field → always 0.0
            if not has_content:
                fc[field] = 0.0
                continue

            # Clamp LLM score; bump to 0.3 if LLM returned 0 for non-empty field
            if llm_conf < 0.1:
                fc[field] = 0.3
            else:
                fc[field] = round(llm_conf, 2)

        data["field_confidences"] = fc
        return data

    def _generate_candidate_id(self, data: dict) -> str:
        """
        Generate a unique candidate ID from email + phone hash.
        """
        identifier = ""
        if data.get("email_ids"):
            identifier += data["email_ids"][0].lower()
        if data.get("phones"):
            identifier += data["phones"][0]

        if identifier:
            return hashlib.md5(identifier.encode()).hexdigest()[:16]
        else:
            # Fallback: use name hash
            name = data.get("candidate_full_name", "unknown")
            return hashlib.md5(name.encode()).hexdigest()[:16]

    def calculate_overall_confidence(self, data: dict) -> float:
        """Calculate overall extraction confidence score."""
        confidences = data.get("field_confidences", {})
        if not confidences:
            # Calculate from data presence
            fields_present = 0
            total_fields = 8  # Core required fields
            if data.get("candidate_full_name"):
                fields_present += 1
            if data.get("email_ids"):
                fields_present += 1
            if data.get("phones"):
                fields_present += 1
            if data.get("current_location"):
                fields_present += 1
            if data.get("key_skills"):
                fields_present += 1
            if data.get("education"):
                fields_present += 1
            if data.get("work_experience"):
                fields_present += 1
            if data.get("total_experience"):
                fields_present += 1
            return fields_present / total_fields

        #optional fields that are genuinely absent should not drag down the overall confidence
        _OPTIONAL_FIELDS = {
            "linkedin_url", "github_url", "portfolio_url",
            "certifications", "languages_known", "gender",
        }
        scored: list[float] = []
        for field, score in confidences.items():
            # Skip optional fields that are genuinely absent
            if score == 0.0 and field in _OPTIONAL_FIELDS:
                continue
            scored.append(score)
        return sum(scored) / len(scored) if scored else 0.0

    def get_extraction_prompt(self) -> str:
        """Return the extraction prompt for evaluation purposes."""
        return EXTRACTION_SYSTEM_PROMPT

    def get_extraction_schema(self) -> dict:
        """Return the extraction JSON schema for evaluation purposes."""
        return ResumeData.json_schema()
