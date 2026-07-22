"""Loaded model inference and deterministic response policy."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import joblib

from app.ml.dataset import FRAUD_TYPES
from app.ml.features import build_features, risk_reasons


@dataclass(frozen=True)
class RiskPrediction:
    risk_score: float
    fraud_type: str
    decision: str
    risk_level: str
    risk_reasons: list[str]
    model_version: str


def decision_for_score(score: float) -> str:
    if score < 0.40:
        return "ONAY"
    if score <= 0.90:
        return "INCELEME"
    return "BLOK"


def risk_level_for_score(score: float) -> str:
    if score < 0.40:
        return "DUSUK"
    if score < 0.70:
        return "ORTA"
    if score <= 0.90:
        return "YUKSEK"
    return "KRITIK"


class RiskEngine:
    def __init__(self, artifact: Mapping[str, Any]) -> None:
        self.pipeline = artifact["pipeline"]
        self.model_version = str(artifact["model_version"])
        self.classes = [str(value) for value in artifact["classes"]]
        if "TEMIZ" not in self.classes or not set(self.classes).issubset(FRAUD_TYPES):
            raise RuntimeError("Model artifact contains an invalid fraud class catalog")

    @classmethod
    def load(cls, artifact_path: str | Path) -> "RiskEngine":
        path = Path(artifact_path)
        if not path.is_file():
            raise RuntimeError(f"Required model artifact is missing: {path}")
        try:
            artifact = joblib.load(path)
            return cls(artifact)
        except Exception as exc:
            raise RuntimeError("Model artifact could not be loaded safely") from exc

    def predict(self, values: Mapping[str, Any]) -> RiskPrediction:
        probabilities = self.pipeline.predict_proba([build_features(values)])[0]
        by_class = dict(zip(self.classes, probabilities, strict=True))
        risk_score = min(1.0, max(0.0, 1.0 - float(by_class["TEMIZ"])))
        fraud_type = "TEMIZ"
        if risk_score >= 0.40:
            fraud_type = max(
                (label for label in self.classes if label != "TEMIZ"),
                key=lambda label: (float(by_class[label]), label),
            )
        return RiskPrediction(
            risk_score=round(risk_score, 6),
            fraud_type=fraud_type,
            decision=decision_for_score(risk_score),
            risk_level=risk_level_for_score(risk_score),
            risk_reasons=risk_reasons(values),
            model_version=self.model_version,
        )
