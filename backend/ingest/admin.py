"""Admin registration — lets us inspect the model directly while building."""

from django.contrib import admin

from .models import (
    ActivityRecord,
    AuditEvent,
    EmissionFactor,
    Facility,
    ImportBatch,
    Organization,
    RawRecord,
    User,
)

admin.site.register(Organization)
admin.site.register(User)
admin.site.register(Facility)
admin.site.register(EmissionFactor)


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ("id", "source_type", "filename", "status",
                    "rows_total", "rows_ok", "rows_flagged", "rows_failed", "created_at")
    list_filter = ("source_type", "status")


@admin.register(RawRecord)
class RawRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "batch", "line_no", "parse_error")
    list_filter = ("batch",)


@admin.register(ActivityRecord)
class ActivityRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "category", "scope", "quantity", "unit",
                    "co2e_kg", "status", "facility")
    list_filter = ("status", "scope", "category", "batch")
    readonly_fields = ("created_at",)


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("id", "record", "actor", "action", "field", "created_at")
    list_filter = ("action",)
