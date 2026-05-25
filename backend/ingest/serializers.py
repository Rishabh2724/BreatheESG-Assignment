from rest_framework import serializers

from .models import ActivityRecord, AuditEvent, EmissionFactor, Facility, ImportBatch, RawRecord


class FacilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Facility
        fields = ["id", "code", "name", "country"]


class EmissionFactorSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmissionFactor
        fields = ["id", "category", "region", "fuel_type", "factor_value",
                  "factor_unit", "currency", "source"]


class ImportBatchSerializer(serializers.ModelSerializer):
    source_type_display = serializers.CharField(source="get_source_type_display", read_only=True)
    uploaded_by = serializers.CharField(source="uploaded_by.username", default=None, read_only=True)

    class Meta:
        model = ImportBatch
        fields = ["id", "source_type", "source_type_display", "filename", "status",
                  "rows_total", "rows_ok", "rows_flagged", "rows_failed",
                  "uploaded_by", "created_at"]


class RawRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawRecord
        fields = ["line_no", "payload", "parse_error"]


class AuditEventSerializer(serializers.ModelSerializer):
    actor = serializers.CharField(source="actor.username", default=None, read_only=True)

    class Meta:
        model = AuditEvent
        fields = ["id", "actor", "action", "field", "old_value", "new_value", "created_at"]


class ActivityRecordSerializer(serializers.ModelSerializer):
    """List/summary shape. The detail endpoint adds raw_record + audit trail."""
    source_type = serializers.CharField(source="batch.source_type", read_only=True)
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    facility = FacilitySerializer(read_only=True)
    emission_factor = EmissionFactorSerializer(read_only=True)
    edited_by = serializers.CharField(source="edited_by.username", default=None, read_only=True)

    class Meta:
        model = ActivityRecord
        fields = ["id", "batch", "source_type", "scope", "category", "category_display",
                  "quantity", "unit", "original_quantity", "original_unit",
                  "period_start", "period_end", "co2e_kg",
                  "emission_factor", "facility", "status", "flags",
                  "edited_by", "edited_at", "created_at"]


class ActivityRecordDetailSerializer(ActivityRecordSerializer):
    raw_record = RawRecordSerializer(read_only=True)
    audit_events = AuditEventSerializer(many=True, read_only=True)

    class Meta(ActivityRecordSerializer.Meta):
        fields = ActivityRecordSerializer.Meta.fields + ["raw_record", "audit_events"]
