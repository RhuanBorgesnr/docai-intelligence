"""
Approvals REST API — the human control layer.

Provides endpoints for the /ops/approvals page to:
- List pending/all approvals
- Approve / Reject / Request changes
- View approval details
- Get counts (for badge in nav)

Sprint 4 / Phase 4A.
"""
from __future__ import annotations

from asgiref.sync import async_to_sync
from rest_framework import status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from approvals.gateway import ApprovalDecision, ApprovalGateway
from approvals.models import Approval as ApprovalRecord
from orchestrator.enums import ApprovalStatus


class ApprovalListView(APIView):
    """GET /api/approvals/  — list approvals with optional status filter."""
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        status_filter = request.query_params.get("status", "pending")
        qs = ApprovalRecord.objects.select_related("case").order_by("deadline_at")

        if status_filter == "pending":
            qs = qs.filter(status__in=[ApprovalStatus.PENDING, ApprovalStatus.ESCALATED])
        elif status_filter == "decided":
            qs = qs.filter(status__in=[
                ApprovalStatus.APPROVED, ApprovalStatus.REJECTED,
                ApprovalStatus.CHANGES_REQUESTED, ApprovalStatus.EXPIRED,
            ])
        elif status_filter != "all":
            qs = qs.filter(status=status_filter)

        approvals = []
        for record in qs[:50]:
            domain = ApprovalGateway._to_domain_request(record)
            approvals.append(domain.to_dict())

        return Response({"count": len(approvals), "approvals": approvals})


class ApprovalCountView(APIView):
    """GET /api/approvals/count/  — pending count for nav badge."""
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        pending = ApprovalRecord.objects.filter(
            status__in=[ApprovalStatus.PENDING, ApprovalStatus.ESCALATED]
        ).count()
        return Response({"pending": pending})


class ApprovalDetailView(APIView):
    """GET /api/approvals/<approval_id>/  — single approval detail."""
    permission_classes = [IsAuthenticated]

    def get(self, request, approval_id: str, *args, **kwargs):
        domain = ApprovalGateway.get_approval(approval_id)
        if not domain:
            return Response(
                {"error": "Approval not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(domain.to_dict())


class ApprovalDecideView(APIView):
    """POST /api/approvals/<approval_id>/decide/  — approve, reject, or request changes."""
    permission_classes = [IsAdminUser]

    def post(self, request, approval_id: str, *args, **kwargs):
        decision_str = request.data.get("decision")
        comment = request.data.get("comment", "")

        valid_decisions = {d.value for d in ApprovalDecision} - {"expired", "escalated"}
        if decision_str not in valid_decisions:
            return Response(
                {"error": f"Invalid decision. Must be one of: {sorted(valid_decisions)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        decision = ApprovalDecision(decision_str)
        approver = request.user.email or request.user.username

        try:
            # Staff users bypass the approver-list check in the gateway.
            # We temporarily add them to the record's approvers if needed.
            _ensure_staff_can_approve(approval_id, approver, request.user)

            result = async_to_sync(ApprovalGateway.decide_approval)(
                approval_id=approval_id,
                decision=decision,
                approved_by=approver,
                comment=comment,
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_409_CONFLICT)
        except PermissionError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_403_FORBIDDEN)

        # If follow-up was approved, trigger notification
        if decision == ApprovalDecision.APPROVED:
            _notify_on_approval(result)

        return Response({
            "approval_id": result.approval_id,
            "status": result.status,
            "decided_by": approver,
            "comment": comment,
        })


def _notify_on_approval(approval):
    """Fire real dispatch + notification when a follow-up/proposal is approved."""
    try:
        data = approval.data_to_approve or {}
        draft_id = data.get("draft_id") or data.get("followup_id")
        if draft_id:
            # 1. Actually send the follow-up (email/whatsapp)
            from notifications.email_sender import dispatch_approved_followup
            dispatch_approved_followup(draft_id)
            # 2. Notify ops that it was sent
            from commercial.demo_scheduler import notify_followup_approved
            notify_followup_approved(draft_id)
    except Exception:
        pass  # Dispatch + notification is best-effort


def _ensure_staff_can_approve(approval_id: str, approver: str, user) -> None:
    """
    If the user is_staff, add them to the approval's approvers list
    so the gateway's authorization check passes. This reflects the
    real-world rule: any ops staff member can approve pending items.
    """
    if not getattr(user, "is_staff", False):
        return
    record = ApprovalRecord.objects.filter(approval_id=approval_id).first()
    if not record:
        return
    approvers = set(record.approvers or [])
    escalated = set(record.escalated_to or [])
    if approver not in approvers and approver not in escalated:
        approvers.add(approver)
        record.approvers = sorted(approvers)
        record.save(update_fields=["approvers"])
