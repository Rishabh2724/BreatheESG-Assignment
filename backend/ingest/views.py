"""
REST API for ingestion + review.

Every endpoint is tenant-scoped: TenantScoped.get_queryset() filters by the caller's org,
so one org can never read or touch another's rows. This is how multi-tenancy is enforced
in a single shared database — disciplined query scoping, verified in tests.
"""

from django.db.models import Count, Sum
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import ActivityRecord, Facility, ImportBatch
from .pipeline.run import run_ingest
from .serializers import (
    ActivityRecordDetailSerializer, ActivityRecordSerializer, ImportBatchSerializer,
)
from .services import apply_edit, transition


class TenantScoped:
    """Mixin: restrict every queryset to the authenticated user's organization."""
    def get_queryset(self):
        return super().get_queryset().filter(org=self.request.user.org)


class ImportBatchViewSet(TenantScoped, viewsets.ModelViewSet):
    queryset = ImportBatch.objects.all()
    serializer_class = ImportBatchSerializer
    http_method_names = ["get", "post"]  # batches are created by upload, never edited

    def create(self, request, *args, **kwargs):
        """Upload a file and ingest it. multipart: source_type + file."""
        source_type = request.data.get("source_type")
        upload = request.FILES.get("file")
        if source_type not in ImportBatch.Source.values:
            return Response({"detail": f"source_type must be one of {ImportBatch.Source.values}"},
                            status=status.HTTP_400_BAD_REQUEST)
        if not upload:
            return Response({"detail": "No file uploaded (field 'file')."},
                            status=status.HTTP_400_BAD_REQUEST)

        batch = ImportBatch.objects.create(
            org=request.user.org, source_type=source_type,
            filename=upload.name, uploaded_by=request.user)
        try:
            run_ingest(batch, upload.read(), actor=request.user)
        except Exception as exc:
            batch.status = ImportBatch.Status.FAILED
            batch.save(update_fields=["status"])
            return Response({"detail": f"Ingestion failed: {exc}", "batch": batch.id},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(batch).data, status=status.HTTP_201_CREATED)


class ActivityRecordViewSet(TenantScoped, viewsets.ModelViewSet):
    queryset = ActivityRecord.objects.select_related(
        "facility", "emission_factor", "batch", "edited_by").all()
    # POST is allowed for the custom review actions only; records are never created via API
    # (they only come from ingestion), so create() is explicitly disabled below.
    http_method_names = ["get", "patch", "post"]

    def create(self, request, *args, **kwargs):
        return Response({"detail": "Records are created by ingestion, not directly."},
                        status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def get_serializer_class(self):
        return ActivityRecordDetailSerializer if self.action == "retrieve" else ActivityRecordSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if (b := params.get("batch")):
            qs = qs.filter(batch_id=b)
        if (s := params.get("status")):
            qs = qs.filter(status=s)
        if (sc := params.get("scope")):
            qs = qs.filter(scope=sc)
        if params.get("flagged") == "true":
            qs = qs.exclude(flags=[])
        return qs

    def partial_update(self, request, *args, **kwargs):
        record = self.get_object()
        changes = {k: v for k, v in request.data.items()}
        # Resolve facility id -> org-scoped instance (or None).
        if "facility" in changes:
            fid = changes["facility"]
            changes["facility"] = (Facility.objects.filter(
                org=request.user.org, id=fid).first() if fid else None)
        try:
            apply_edit(record, changes, actor=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(ActivityRecordDetailSerializer(record).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._do(request, "approve")

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._do(request, "reject")

    @action(detail=True, methods=["post"])
    def lock(self, request, pk=None):
        return self._do(request, "lock")

    def _do(self, request, action_name):
        record = self.get_object()
        try:
            transition(record, action_name, actor=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(ActivityRecordSerializer(record).data)

    @action(detail=False, methods=["post"])
    def bulk_action(self, request):
        """Body: {ids: [..], action: approve|reject|lock}. Applies to org-scoped rows only."""
        ids = request.data.get("ids", [])
        act = request.data.get("action")
        records = self.get_queryset().filter(id__in=ids)
        done, errors = [], []
        for r in records:
            try:
                transition(r, act, actor=request.user)
                done.append(r.id)
            except ValueError as exc:
                errors.append({"id": r.id, "detail": str(exc)})
        return Response({"updated": done, "errors": errors})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def summary(request):
    """Dashboard rollup for the caller's org: status counts + co2e by scope."""
    qs = ActivityRecord.objects.filter(org=request.user.org)
    by_status = dict(qs.values_list("status").annotate(n=Count("id")))
    by_scope = {
        f"scope_{row['scope']}": float(row["t"] or 0)
        for row in qs.values("scope").annotate(t=Sum("co2e_kg"))
    }
    return Response({
        "total_records": qs.count(),
        "by_status": by_status,
        "co2e_by_scope_kg": by_scope,
        "total_co2e_kg": float(qs.aggregate(t=Sum("co2e_kg"))["t"] or 0),
        "locked_co2e_kg": float(
            qs.filter(status="locked").aggregate(t=Sum("co2e_kg"))["t"] or 0),
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    u = request.user
    return Response({"username": u.username, "role": u.role,
                     "org": u.org.name if u.org else None})
