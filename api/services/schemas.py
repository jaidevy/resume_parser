import logging

from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    field_validator,
    model_validator,
    ConfigDict,
    AliasChoices,
)

logger = logging.getLogger("api")


# -- Nested models ------------------------------------------------------------

class GeoDetails(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    city: str = ""
    state: str = ""
    country: str = ""


class WorkExperience(BaseModel):
    """A single work-experience entry."""
    model_config = ConfigDict(populate_by_name=True)

    company: str = ""
    role: str = Field(
        default="",
        validation_alias=AliasChoices(
            "role", "job_title", "title", "position", "designation",
        ),
        description="Job title / designation",
    )
    location: str = Field(default="", description="Office location if mentioned")
    start_date: str = ""
    end_date: str = ""
    duration: str = ""
    responsibilities: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "responsibilities", "description", "duties",
        ),
    )
    achievements: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "technologies", "tools", "tech_stack", "tech",
        ),
    )

    @field_validator("responsibilities", "achievements", "technologies", mode="before")
    @classmethod
    def _coerce_to_list(cls, v):
        """Scalar string -> single-element list."""
        if isinstance(v, str):
            return [v] if v.strip() else []
        return v if isinstance(v, list) else []


class Education(BaseModel):
    """A single education entry."""
    model_config = ConfigDict(populate_by_name=True)

    degree: str = Field(
        default="",
        description="Degree name, e.g. B.Tech, MBA, 12th Class",
    )
    field_of_study: str = Field(
        default="",
        validation_alias=AliasChoices(
            "field_of_study", "specialization", "major", "stream",
            "branch", "course",
        ),
        description="Major / specialization / stream",
    )
    institution: str = Field(
        default="",
        validation_alias=AliasChoices(
            "institution", "university", "college", "school", "board",
        ),
        description="Name of university or school",
    )
    start_year: str = Field(
        default="",
        validation_alias=AliasChoices("start_year", "start_date"),
    )
    end_year: str = Field(
        default="",
        validation_alias=AliasChoices(
            "end_year", "year", "passing_year", "graduation_year", "end_date",
        ),
    )
    grade: str = Field(
        default="",
        validation_alias=AliasChoices(
            "grade", "cgpa", "gpa", "percentage", "marks", "score", "result",
        ),
    )

    @field_validator("start_year", "end_year", "grade", "degree",
                     "field_of_study", "institution", mode="before")
    @classmethod
    def _coerce_to_str(cls, v):
        """LLMs often return year fields as integers (2019 instead of '2019')."""
        if v is None:
            return ""
        return str(v).strip()


class Project(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = ""
    description: str = ""
    technologies: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "technologies", "tech_stack", "tools", "tech",
        ),
    )

    @field_validator("description", mode="before")
    @classmethod
    def _coerce_description(cls, v):
        """LLMs sometimes return bullet-point lists instead of a single string."""
        if isinstance(v, list):
            return "; ".join(str(item).strip() for item in v if str(item).strip())
        if v is None:
            return ""
        return str(v)


# -- Top-level extraction model ------------------------------------------------


class ResumeData(BaseModel):
    """
    Canonical Pydantic schema for structured resume data.

    Only enforces **shape** (types, aliases, defaults).  All intelligent
    extraction, cleaning, and enrichment is done by the LLM prompt.
    """
    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
    )

    candidate_full_name: str = Field(
        default="",
        validation_alias=AliasChoices(
            "candidate_full_name", "name", "full_name", "candidate_name",
        ),
    )
    email_ids: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "email_ids", "email", "emails", "email_address",
        ),
    )
    phones: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "phones", "phone", "mobile", "phone_number", "contact_number",
        ),
    )
    gender: str = Field(
        default="",
        description="Gender ONLY if explicitly stated. Do NOT infer.",
    )
    current_location: str = Field(
        default="",
        validation_alias=AliasChoices(
            "current_location", "location", "address",
        ),
    )
    geo_details: GeoDetails = Field(default_factory=GeoDetails)
    total_experience: str = Field(
        default="",
        description="Total years/months of experience",
    )
    work_experience: list[WorkExperience] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "work_experience", "experience", "experiences",
            "employment", "employment_history",
        ),
    )
    key_skills: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "key_skills", "skills", "core_skills", "technical_skills",
            "technologies",
        ),
    )
    education: list[Education] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "education", "academics", "academic_background",
            "academic_qualifications", "educational_qualifications",
            "educational_background", "qualifications",
        ),
    )
    certifications: list[str] = Field(
        default_factory=list,
        description="Flat list of certification names",
    )
    linkedin_url: str = Field(
        default="",
        validation_alias=AliasChoices(
            "linkedin_url", "linkedin", "linkedin_profile",
        ),
    )
    github_url: str = Field(
        default="",
        validation_alias=AliasChoices(
            "github_url", "github", "github_profile",
        ),
    )
    portfolio_url: str = Field(
        default="",
        validation_alias=AliasChoices(
            "portfolio_url", "portfolio", "website",
        ),
    )
    professional_summary: str = Field(
        default="",
        validation_alias=AliasChoices(
            "professional_summary", "summary", "objective", "profile",
        ),
    )
    projects: list[Project] = Field(default_factory=list)
    languages_known: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "languages_known", "languages", "language_skills",
            "spoken_languages",
        ),
    )
    field_confidences: dict[str, float] = Field(default_factory=dict)
    candidate_id: str = ""

    # -- Pre-validators --------------------------------------------------------

    @model_validator(mode="before")
    @classmethod
    def _normalise_input(cls, values: dict) -> dict:
        """Light structural fix-ups before Pydantic type coercion.

        1. Flatten `personal_info` wrapper some LLMs emit.
        2. Coerce non-dict / non-list values to the expected container type
           so Pydantic doesn't reject the whole payload.
        """
        if not isinstance(values, dict):
            return values

        # --- geo_details must be dict ---
        gd = values.get("geo_details")
        if gd is not None and not isinstance(gd, dict):
            values["geo_details"] = {}

        # --- list-of-object fields must be list ---
        _LIST_KEYS = (
            "work_experience", "experience", "experiences",
            "employment", "employment_history",
            "education", "academics", "academic_background",
            "academic_qualifications", "educational_qualifications",
            "educational_background", "qualifications",
            "projects",
        )
        for key in _LIST_KEYS:
            val = values.get(key)
            if val is not None and not isinstance(val, list):
                values[key] = [val] if isinstance(val, dict) else []

        # --- Flatten nested personal_info ---
        pi = values.pop("personal_info", None)
        if isinstance(pi, dict):
            _PI_MAP = {
                "name": "candidate_full_name",
                "full_name": "candidate_full_name",
                "email": "email_ids",
                "emails": "email_ids",
                "phone": "phones",
                "phones": "phones",
                "mobile": "phones",
                "location": "current_location",
                "address": "current_location",
                "gender": "gender",
                "linkedin": "linkedin_url",
                "github": "github_url",
            }
            for alias, canonical in _PI_MAP.items():
                if alias in pi and not values.get(canonical):
                    values[canonical] = pi[alias]

        return values

    # -- Field-level coercion (scalar <-> list, dict -> string) ----------------

    @field_validator("email_ids", "phones", "key_skills",
                     "certifications", "languages_known", mode="before")
    @classmethod
    def _coerce_to_str_list(cls, v):
        """Accept a scalar string or list; always return `list[str]`."""
        if isinstance(v, str):
            return [v.strip()] if v.strip() else []
        if not isinstance(v, list):
            return []
        # Flatten dicts that sometimes appear in certifications
        out: list[str] = []
        for item in v:
            if isinstance(item, dict):
                name = (
                    item.get("name")
                    or item.get("title")
                    or item.get("certification")
                    or ""
                )
                if name:
                    out.append(str(name).strip())
            elif isinstance(item, str) and item.strip():
                out.append(item.strip())
        return out

    @field_validator("field_confidences", mode="before")
    @classmethod
    def _normalise_confidence_keys(cls, v):
        """Map aliased confidence keys -> canonical field names and clamp."""
        if not isinstance(v, dict):
            return {}
        _ALIASES = {
            "name": "candidate_full_name", "full_name": "candidate_full_name",
            "candidate_name": "candidate_full_name",
            "email": "email_ids", "emails": "email_ids",
            "phone": "phones", "mobile": "phones",
            "location": "current_location", "address": "current_location",
            "linkedin": "linkedin_url", "github": "github_url",
            "portfolio": "portfolio_url", "website": "portfolio_url",
            "skills": "key_skills", "core_skills": "key_skills",
            "technical_skills": "key_skills", "technologies": "key_skills",
            "experience": "work_experience", "experiences": "work_experience",
            "academics": "education", "qualifications": "education",
            "summary": "professional_summary", "objective": "professional_summary",
            "languages": "languages_known",
        }
        normalised: dict[str, float] = {}
        for k, val in v.items():
            canonical: str = _ALIASES.get(k) or k
            try:
                score = max(0.0, min(1.0, float(val)))
            except (TypeError, ValueError):
                score = 0.0
            if canonical in normalised:
                normalised[canonical] = max(normalised[canonical], score)
            else:
                normalised[canonical] = score
        return normalised

    # -- Serialisation helpers -------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise to a plain dict (by canonical field name)."""
        return self.model_dump(by_alias=False)

    @classmethod
    def from_llm_response(cls, data: dict) -> "ResumeData":
        """
        Construct a validated `ResumeData` from a raw LLM JSON dict.

        On validation failure the error is logged and a best-effort
        partial result is returned so the pipeline never silently
        drops all data.
        """
        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            logger.error(
                "Pydantic validation failed for LLM response (%d error(s)). "
                "Attempting lenient re-parse.  Errors: %s",
                exc.error_count(),
                exc.errors(),
            )
            bad_fields = {e["loc"][0] for e in exc.errors() if e.get("loc")}
            cleaned = {k: v for k, v in data.items() if k not in bad_fields}
            try:
                return cls.model_validate(cleaned)
            except ValidationError:
                logger.error(
                    "Lenient re-parse also failed; returning empty ResumeData"
                )
                return cls()

    @classmethod
    def empty(cls) -> "ResumeData":
        """Return a blank instance with all defaults."""
        return cls()

    @classmethod
    def json_schema(cls) -> dict:
        """Return the JSON-Schema representation for prompt engineering."""
        return cls.model_json_schema()
