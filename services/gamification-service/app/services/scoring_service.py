from dataclasses import dataclass
from enum import Enum

from app.schemas.events import CaseDecisionData, CustomerResponse, Decision, RiskLevel


class ScoreReason(str, Enum):
    CASE_RESOLVED = "CASE_RESOLVED"
    FAST_DECISION = "FAST_DECISION"
    CONFIRMED_FRAUD = "CONFIRMED_FRAUD"
    CRITICAL_WITHIN_SLA = "CRITICAL_WITHIN_SLA"
    SLA_EXCEEDED = "SLA_EXCEEDED"
    FALSE_POSITIVE = "FALSE_POSITIVE"


@dataclass(frozen=True)
class ScoreAward:
    points: int
    reason: ScoreReason


def score_case(data: CaseDecisionData) -> list[ScoreAward]:
    awards: list[ScoreAward] = []
    if data.decision in {Decision.ONAYLANDI, Decision.BLOKLANDI}:
        awards.append(ScoreAward(10, ScoreReason.CASE_RESOLVED))
    if data.resolution_seconds < 900:
        awards.append(ScoreAward(5, ScoreReason.FAST_DECISION))
    if data.decision is Decision.BLOKLANDI and data.customer_response is CustomerResponse.BEN_YAPMADIM:
        awards.append(ScoreAward(15, ScoreReason.CONFIRMED_FRAUD))
    if data.risk_level is RiskLevel.KRITIK and not data.sla_exceeded:
        awards.append(ScoreAward(15, ScoreReason.CRITICAL_WITHIN_SLA))
    if data.sla_exceeded:
        awards.append(ScoreAward(-5, ScoreReason.SLA_EXCEEDED))
    if data.is_false_positive:
        awards.append(ScoreAward(-8, ScoreReason.FALSE_POSITIVE))
    return awards


def level_for(points: int) -> str:
    if points >= 3000:
        return "PLATIN"
    if points >= 1500:
        return "ALTIN"
    if points >= 500:
        return "GUMUS"
    return "BRONZ"
