"""
Models for the Resume Parser API.

These Django models store local metadata and processing logs.
The primary resume data is stored in Dataverse; these models provide
local tracking, audit logging, and processing status.
"""
import uuid
from django.db import models
from django.utils import timezone


class ResumeRecord(models.Model):
    """
    Local tracking record for each processed resume.
    Maps to a corresponding Dataverse record.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        VALIDATING = "validating", "Validating"
        EXTRACTING = "extracting", "Extracting"
        STORING = "storing", "Storing"
        STANDARDIZING = "standardizing", "Standardizing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    class Source(models.TextChoices):
        UPLOAD = "upload", "Upload"
        EMAIL = "email", "Email"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    candidate_id = models.CharField(
        max_length=255, unique=True, blank=True, null=True,
        help_text="Unique key derived from email+phone hash or generated."
    )

    # File info
    original_file_name = models.CharField(max_length=512)
    file_type = models.CharField(max_length=20)
    file_size_bytes = models.BigIntegerField(default=0)
    file_path = models.CharField(max_length=1024, blank=True)
    resume_source = models.CharField(
        max_length=20, choices=Source.choices, default=Source.UPLOAD
    )

    # Extracted data (JSON blob stored locally for quick access)
    extracted_data = models.JSONField(default=dict, blank=True)
    extraction_confidence = models.FloatField(default=0.0)

    # Processing status
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    error_message = models.TextField(blank=True)

    # Dataverse reference
    dataverse_record_id = models.CharField(max_length=255, blank=True)

    # Output
    standardized_file_path = models.CharField(max_length=1024, blank=True)

    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    # Version handling for duplicate resumes
    version = models.IntegerField(default=1)
    previous_version_id = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Resume Record"
        verbose_name_plural = "Resume Records"

    def __str__(self):
        return f"{self.original_file_name} - {self.status}"


class ProcessingLog(models.Model):
    """
    Audit log for every processing run.
    Captures status, errors, timestamps, and file references.
    """

    class LogLevel(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"
        DEBUG = "debug", "Debug"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resume_record = models.ForeignKey(
        ResumeRecord,
        on_delete=models.CASCADE,
        related_name="logs",
        null=True,
        blank=True,
    )

    # Log details
    level = models.CharField(
        max_length=10, choices=LogLevel.choices, default=LogLevel.INFO
    )
    step = models.CharField(max_length=50, help_text="Processing step name")
    message = models.TextField()
    details = models.JSONField(default=dict, blank=True)

    # Timestamps
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Processing Log"
        verbose_name_plural = "Processing Logs"

    def __str__(self):
        return f"[{self.level}] {self.step}: {self.message[:80]}"


class ExtractionField(models.Model):
    """
    Per-field extraction detail with confidence score.
    """

    resume_record = models.ForeignKey(
        ResumeRecord,
        on_delete=models.CASCADE,
        related_name="extraction_fields",
    )
    field_name = models.CharField(max_length=100)
    field_value = models.TextField(blank=True)
    confidence = models.FloatField(default=0.0)
    is_missing = models.BooleanField(default=False)

    class Meta:
        unique_together = ("resume_record", "field_name")

    def __str__(self):
        return f"{self.field_name}: {self.field_value[:50]} ({self.confidence:.0%})"
