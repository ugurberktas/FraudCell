"""FraudCell canonical event types enum."""
from enum import Enum


class EventType(str, Enum):
    TRANSACTION_CREATED = "transaction.created"
    TRANSACTION_SCORED = "transaction.scored"
    CASE_ASSIGNED = "case.assigned"
    CASE_DECISION_MADE = "case.decision_made"
    TRANSACTION_BLOCKED = "transaction.blocked"
    FRAUD_TYPE_CHANGED = "fraud_type.changed"
    CUSTOMER_VERIFIED = "customer.verified"
    SLA_EXCEEDED = "sla.exceeded"
    FEEDBACK_SUBMITTED = "feedback.submitted"
    BADGE_EARNED = "badge.earned"
