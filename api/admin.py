from django.contrib import admin
from .models import ResumeRecord, ProcessingLog, ExtractionField


@admin.register(ResumeRecord)
class ResumeRecordAdmin(admin.ModelAdmin):
    list_display = [
        "original_file_name",
        "candidate_id",
        "status",
        "extraction_confidence",
        "resume_source",
        "created_at",
        "processed_at",
    ]
    list_filter = ["status", "resume_source", "file_type"]
    search_fields = ["original_file_name", "candidate_id"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(ProcessingLog)
class ProcessingLogAdmin(admin.ModelAdmin):
    list_display = ["level", "step", "message", "timestamp"]
    list_filter = ["level", "step"]
    search_fields = ["message"]


@admin.register(ExtractionField)
class ExtractionFieldAdmin(admin.ModelAdmin):
    list_display = ["resume_record", "field_name", "confidence", "is_missing"]
    list_filter = ["field_name", "is_missing"]
