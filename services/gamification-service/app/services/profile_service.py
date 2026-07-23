from datetime import datetime, timedelta, timezone
import uuid

from app.common.exceptions import NotFoundException
from app.repositories.gamification_repository import GamificationRepository


def _period_start(period: str, now: datetime) -> datetime:
    day = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return day if period == "daily" else day - timedelta(days=day.weekday())


class ProfileService:
    def __init__(self, session, clock=lambda: datetime.now(timezone.utc)) -> None:
        self.repository = GamificationRepository(session)
        self.clock = clock

    def leaderboard(self, period: str, limit: int = 10) -> list[dict]:
        profiles = self.repository.profiles()
        points = self.repository.period_points(_period_start(period, self.clock()))
        profiles.sort(key=lambda p: (-points.get(p.analyst_id, 0), -p.total_points, str(p.analyst_id)))
        return [self._leaderboard_row(index, profile, points.get(profile.analyst_id, 0)) for index, profile in enumerate(profiles[:limit], 1)]

    @staticmethod
    def _leaderboard_row(rank, profile, period_points):
        return {
            "rank": rank,
            "analyst_id": str(profile.analyst_id),
            "period_points": period_points,
            "total_points": profile.total_points,
            "level": profile.level,
            "resolved_cases": profile.resolved_cases,
            "badges": sorted(item.badge_code for item in profile.badges),
        }

    def profile(self, analyst_id: uuid.UUID) -> dict:
        profile = self.repository.get_profile(analyst_id)
        if profile is None:
            raise NotFoundException("Analyst profile not found")
        daily = self.leaderboard("daily", 10_000)
        weekly = self.leaderboard("weekly", 10_000)
        daily_rank = next((row["rank"] for row in daily if row["analyst_id"] == str(analyst_id)), None)
        weekly_rank = next((row["rank"] for row in weekly if row["analyst_id"] == str(analyst_id)), None)
        recent = self.repository.recent_scores(analyst_id)
        return {
            "analyst_id": str(profile.analyst_id),
            "total_points": profile.total_points,
            "level": profile.level,
            "badges": sorted(item.badge_code for item in profile.badges),
            "resolved_cases": profile.resolved_cases,
            "average_points_per_case": round(profile.total_points / profile.resolved_cases, 2) if profile.resolved_cases else 0.0,
            "daily_rank": daily_rank,
            "weekly_rank": weekly_rank,
            "recent_score_entries": [
                {"points": item.points, "reason": item.reason, "occurred_at": item.occurred_at}
                for item in recent
            ],
        }
