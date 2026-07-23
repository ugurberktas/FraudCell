from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.events.envelope import EventEnvelope
from app.events.types import EventType
from app.models import AnalystProfile, Badge, ProcessedEvent, ScoreLedger
from app.repositories.gamification_repository import GamificationRepository
from app.schemas.events import CaseDecisionData, CustomerResponse, Decision, FeedbackSubmittedData
from app.services.scoring_service import level_for, score_case


@dataclass(frozen=True)
class ProcessResult:
    duplicate: bool
    points: int
    badge_earned: bool


class InvalidEvent(ValueError):
    pass


class EventService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = GamificationRepository(session)

    def process(self, raw: dict) -> ProcessResult:
        try:
            envelope = EventEnvelope.model_validate(raw)
            if envelope.event_version != 1:
                raise InvalidEvent("unsupported event type or version")
            if envelope.event_type is EventType.FEEDBACK_SUBMITTED:
                FeedbackSubmittedData.model_validate(envelope.payload)
                return self._mark_processed(envelope)
            if envelope.event_type is not EventType.CASE_DECISION_MADE:
                raise InvalidEvent("unsupported event type or version")
            data = CaseDecisionData.model_validate(envelope.payload)
        except ValidationError as exc:
            raise InvalidEvent("invalid case decision event") from exc

        if self.repository.is_processed(envelope.event_id):
            self.session.rollback()
            return ProcessResult(True, 0, False)

        try:
            profile = self.repository.get_profile(data.analyst_id, for_update=True)
            if profile is None:
                profile = AnalystProfile(analyst_id=data.analyst_id)
                self.session.add(profile)
                self.session.flush()

            awards = score_case(data)
            for award in awards:
                self.session.add(ScoreLedger(
                    event_id=envelope.event_id,
                    analyst_id=data.analyst_id,
                    points=award.points,
                    reason=award.reason.value,
                    occurred_at=envelope.occurred_at,
                ))
            points = sum(item.points for item in awards)
            profile.total_points += points
            profile.resolved_cases += 1
            profile.level = level_for(profile.total_points)
            profile.updated_at = datetime.now(timezone.utc)

            badge_earned = False
            confirmed = data.decision is Decision.BLOKLANDI and data.customer_response is CustomerResponse.BEN_YAPMADIM
            existing_badge = any(item.badge_code == "ILK_YAKALAMA" for item in profile.badges)
            if confirmed and not existing_badge:
                self.session.add(Badge(
                    analyst_id=data.analyst_id,
                    badge_code="ILK_YAKALAMA",
                    source_event_id=envelope.event_id,
                ))
                badge_earned = True
            self.session.add(ProcessedEvent(event_id=envelope.event_id, event_type=envelope.event_type.value))
            self.session.commit()
            return ProcessResult(False, points, badge_earned)
        except IntegrityError:
            self.session.rollback()
            if self.repository.is_processed(envelope.event_id):
                return ProcessResult(True, 0, False)
            raise
        except Exception:
            self.session.rollback()
            raise

    def _mark_processed(self, envelope: EventEnvelope) -> ProcessResult:
        if self.repository.is_processed(envelope.event_id):
            self.session.rollback()
            return ProcessResult(True, 0, False)
        try:
            self.session.add(
                ProcessedEvent(
                    event_id=envelope.event_id,
                    event_type=envelope.event_type.value,
                )
            )
            self.session.commit()
            return ProcessResult(False, 0, False)
        except IntegrityError:
            self.session.rollback()
            if self.repository.is_processed(envelope.event_id):
                return ProcessResult(True, 0, False)
            raise
        except Exception:
            self.session.rollback()
            raise
