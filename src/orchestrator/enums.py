"""Enums shared by the orchestration layer."""
from django.db import models


class CaseState(models.TextChoices):
    NEW = "new", "New"
    TRIAGE = "triage", "Triage"
    QUALIFIED = "qualified", "Qualified"
    WAITING_DOC_SAMPLE = "waiting_doc_sample", "Waiting Doc Sample"
    DOC_SENT_TO_DOCAI = "doc_sent_to_docai", "Doc Sent To DocAI"
    ANALYSIS_READY = "analysis_ready", "Analysis Ready"
    PROPOSAL_DRAFT_READY = "proposal_draft_ready", "Proposal Draft Ready"
    WAITING_HUMAN_APPROVAL = "waiting_human_approval", "Waiting Human Approval"
    APPROVED_TO_SEND = "approved_to_send", "Approved To Send"
    FOLLOWUP_SCHEDULED = "followup_scheduled", "Follow-up Scheduled"
    WON = "won", "Won"
    LOST = "lost", "Lost"
    BLOCKED = "blocked", "Blocked"
    FAILED = "failed", "Failed"
    CLOSED = "closed", "Closed"


class EventType(models.TextChoices):
    LEAD_RECEIVED = "lead.received", "Lead Received"
    LEAD_QUALIFIED = "lead.qualified", "Lead Qualified"
    LEAD_DISQUALIFIED = "lead.disqualified", "Lead Disqualified"
    LEAD_SCORED = "lead.scored", "Lead Scored"
    OPPORTUNITY_CREATED = "opportunity.created", "Opportunity Created"
    OPPORTUNITY_STAGE_CHANGED = "opportunity.stage_changed", "Opportunity Stage Changed"
    FOLLOWUP_DRAFTED = "followup.drafted", "Follow-up Drafted"
    FOLLOWUP_SENT = "followup.sent", "Follow-up Sent"
    DEMO_INSIGHT_GENERATED = "demo.insight.generated", "Demo Insight Generated"
    EXECUTIVE_ALERT_RAISED = "executive.alert.raised", "Executive Alert Raised"
    DOCUMENT_SAMPLE_REQUESTED = "document.sample.requested", "Document Sample Requested"
    DOCUMENT_SAMPLE_RECEIVED = "document.sample.received", "Document Sample Received"
    DOCAI_ANALYSIS_REQUESTED = "docai.analysis.requested", "DocAI Analysis Requested"
    DOCAI_ANALYSIS_COMPLETED = "docai.analysis.completed", "DocAI Analysis Completed"
    PROPOSAL_DRAFT_GENERATED = "proposal.draft.generated", "Proposal Draft Generated"
    APPROVAL_REQUIRED = "approval.required", "Approval Required"
    APPROVAL_GRANTED = "approval.granted", "Approval Granted"
    APPROVAL_REJECTED = "approval.rejected", "Approval Rejected"
    WORKFLOW_TRANSITIONED = "workflow.transitioned", "Workflow Transitioned"
    WORKFLOW_FAILED = "workflow.failed", "Workflow Failed"


class Priority(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    CRITICAL = "critical", "Critical"


class ApprovalStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ESCALATED = "escalated", "Escalated"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    CHANGES_REQUESTED = "changes_requested", "Changes Requested"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"


class AgentCommandStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    DISPATCHED = "dispatched", "Dispatched"
    RUNNING = "running", "Running"
    SUCCEEDED = "succeeded", "Succeeded"
    TIMED_OUT = "timed_out", "Timed Out"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class DurableEventStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    PUBLISHED = "published", "Published"
    FAILED = "failed", "Failed"
    DEAD = "dead", "Dead"


class PromptLifecycleStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    CANARY = "canary", "Canary"
    DEPRECATED = "deprecated", "Deprecated"
    ARCHIVED = "archived", "Archived"


class DurableNotificationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    DISPATCHING = "dispatching", "Dispatching"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"
    FAILED_FALLBACK = "failed_fallback", "Failed Fallback"


class WorkflowStatus(models.TextChoices):
    RUNNING = "running", "Running"
    WAITING_APPROVAL = "waiting_approval", "Waiting Approval"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    BLOCKED = "blocked", "Blocked"
