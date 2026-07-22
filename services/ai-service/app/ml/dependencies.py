"""Application-scoped loaded model dependency."""
from app.core.config import settings
from app.ml.engine import RiskEngine


_risk_engine = RiskEngine.load(settings.model_artifact_path)


def get_risk_engine() -> RiskEngine:
    return _risk_engine
