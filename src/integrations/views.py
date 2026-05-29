"""DRF Views for ERP Integrations."""
from rest_framework import generics, permissions, status, views
from rest_framework.response import Response

from .models import ERPConnection, ERPFieldMapping, ERPSyncLog, SyncStatus
from .serializers import (
    ApproveSyncSerializer,
    ERPConnectionListSerializer,
    ERPConnectionSerializer,
    ERPFieldMappingSerializer,
    ERPSyncLogSerializer,
    SyncDocumentSerializer,
    TestConnectionSerializer,
)
from .services import (
    ERPSyncError,
    sync_cliente,
    sync_conta_pagar,
    sync_conta_receber,
    check_erp_connection,
)
from .tasks import task_approve_and_execute


class ERPConnectionListCreateView(generics.ListCreateAPIView):
    """List all connections or create a new one."""

    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "GET":
            return ERPConnectionListSerializer
        return ERPConnectionSerializer

    def get_queryset(self):
        return ERPConnection.objects.all()


class ERPConnectionDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Get, update or delete a connection."""

    serializer_class = ERPConnectionSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = ERPConnection.objects.all()


class TestConnectionView(views.APIView):
    """Test if an ERP connection is working."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = TestConnectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            connection = ERPConnection.objects.get(id=serializer.validated_data["connection_id"])
        except ERPConnection.DoesNotExist:
            return Response({"error": "Connection not found"}, status=status.HTTP_404_NOT_FOUND)

        result = check_erp_connection(connection)
        return Response({
            "success": result.success,
            "error_message": result.error_message,
            "error_code": result.error_code,
        }, status=status.HTTP_200_OK if result.success else status.HTTP_400_BAD_REQUEST)


class SyncDocumentView(views.APIView):
    """Sync an extracted document to ERP."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = SyncDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            connection = ERPConnection.objects.get(id=data["connection_id"])
        except ERPConnection.DoesNotExist:
            return Response({"error": "Connection not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            entity_type = data["entity_type"]
            extracted_data = data["extracted_data"]
            correlation_id = data.get("correlation_id", "")
            codigo = data.get("codigo_cliente_fornecedor")

            if entity_type == "conta_pagar":
                sync_log = sync_conta_pagar(
                    connection, extracted_data, correlation_id, codigo
                )
            elif entity_type == "conta_receber":
                sync_log = sync_conta_receber(
                    connection, extracted_data, correlation_id, codigo
                )
            elif entity_type == "cliente":
                sync_log = sync_cliente(connection, extracted_data, correlation_id)
            else:
                return Response(
                    {"error": f"Unsupported entity type: {entity_type}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return Response(
                ERPSyncLogSerializer(sync_log).data,
                status=status.HTTP_201_CREATED if sync_log.status == SyncStatus.SUCCESS else status.HTTP_202_ACCEPTED,
            )

        except ERPSyncError as e:
            return Response(
                {"error": str(e), "error_code": e.error_code},
                status=status.HTTP_400_BAD_REQUEST,
            )


class ApproveSyncView(views.APIView):
    """Approve a pending sync and execute it."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ApproveSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        sync_log_id = str(serializer.validated_data["sync_log_id"])
        approved_by = serializer.validated_data.get("approved_by", request.user.get_full_name())

        try:
            ERPSyncLog.objects.get(id=sync_log_id, status=SyncStatus.AWAITING_APPROVAL)
        except ERPSyncLog.DoesNotExist:
            return Response(
                {"error": "Sync log not found or not awaiting approval"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Dispatch async execution
        task_approve_and_execute.delay(sync_log_id, approved_by)

        return Response(
            {"message": "Sync approved and queued for execution", "sync_log_id": sync_log_id},
            status=status.HTTP_202_ACCEPTED,
        )


class ERPSyncLogListView(generics.ListAPIView):
    """List sync logs with filtering."""

    serializer_class = ERPSyncLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = ERPSyncLog.objects.select_related("connection").all()

        # Filters
        connection_id = self.request.query_params.get("connection_id")
        if connection_id:
            queryset = queryset.filter(connection_id=connection_id)

        entity_type = self.request.query_params.get("entity_type")
        if entity_type:
            queryset = queryset.filter(entity_type=entity_type)

        sync_status = self.request.query_params.get("status")
        if sync_status:
            queryset = queryset.filter(status=sync_status)

        return queryset[:100]


class ERPSyncStatsView(views.APIView):
    """Dashboard stats for ERP integrations."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from django.db.models import Avg, Count, Q
        from django.utils import timezone as tz

        last_24h = tz.now() - tz.timedelta(hours=24)
        last_7d = tz.now() - tz.timedelta(days=7)

        logs_24h = ERPSyncLog.objects.filter(created_at__gte=last_24h)
        logs_7d = ERPSyncLog.objects.filter(created_at__gte=last_7d)

        stats = {
            "connections": {
                "total": ERPConnection.objects.count(),
                "active": ERPConnection.objects.filter(is_active=True).count(),
                "circuit_open": ERPConnection.objects.filter(is_circuit_open=True).count(),
            },
            "last_24h": {
                "total": logs_24h.count(),
                "success": logs_24h.filter(status=SyncStatus.SUCCESS).count(),
                "failed": logs_24h.filter(status=SyncStatus.FAILED).count(),
                "awaiting_approval": logs_24h.filter(status=SyncStatus.AWAITING_APPROVAL).count(),
                "avg_duration_ms": logs_24h.filter(duration_ms__isnull=False).aggregate(
                    avg=Avg("duration_ms")
                )["avg"],
            },
            "last_7d": {
                "total": logs_7d.count(),
                "success": logs_7d.filter(status=SyncStatus.SUCCESS).count(),
                "failed": logs_7d.filter(status=SyncStatus.FAILED).count(),
                "by_entity_type": list(
                    logs_7d.values("entity_type").annotate(count=Count("id")).order_by("-count")
                ),
            },
        }

        return Response(stats)


class ERPFieldMappingListCreateView(generics.ListCreateAPIView):
    """List/create field mappings for a connection."""

    serializer_class = ERPFieldMappingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        connection_id = self.request.query_params.get("connection_id")
        if connection_id:
            return ERPFieldMapping.objects.filter(connection_id=connection_id)
        return ERPFieldMapping.objects.all()
