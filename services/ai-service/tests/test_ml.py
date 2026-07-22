import csv
import json
from pathlib import Path

import pytest

from app.ml.dataset import CSV_COLUMNS, FRAUD_TYPES
from app.ml.engine import RiskEngine, decision_for_score, risk_level_for_score
from app.ml.train import DEFAULT_ARTIFACT_DIR, DEFAULT_DATASET_PATH, train_model


def scenarios():
    low = {
        "amount": 250,
        "transaction_type": "FATURA",
        "recipient": "Elektrik Faturası",
        "source_device": "iPhone 15 Pro",
        "city": "Istanbul",
        "occurred_at": "2026-07-23T12:00:00Z",
        "transaction_frequency_24h": 2,
        "is_new_device": False,
        "home_city": "Istanbul",
    }
    medium = {
        "amount": 15000,
        "transaction_type": "TRANSFER",
        "recipient": "Demo Alıcı",
        "source_device": "New Android Device",
        "city": "Berlin",
        "occurred_at": "2026-07-23T16:00:00Z",
        "transaction_frequency_24h": 4,
        "is_new_device": True,
        "home_city": "Istanbul",
    }
    high = {
        "amount": 180000,
        "transaction_type": "TRANSFER",
        "recipient": "Yurt Dışı Alıcı",
        "source_device": "New Android Device",
        "city": "Moscow",
        "occurred_at": "2026-07-23T02:00:00Z",
        "transaction_frequency_24h": 14,
        "is_new_device": True,
        "home_city": "Istanbul",
    }
    return low, medium, high


def test_dataset_schema_size_noise_and_catalog():
    with DEFAULT_DATASET_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) >= 1000
    assert set(rows[0]) == set(CSV_COLUMNS)
    labels = {row["fraud_type"] for row in rows}
    assert labels == set(FRAUD_TYPES)
    assert any(
        float(row["amount"]) > 20_000 and row["fraud_type"] == "TEMIZ"
        for row in rows
    )
    assert any(
        row["is_new_device"] == "false" and row["fraud_type"] != "TEMIZ"
        for row in rows
    )


def test_artifacts_and_required_metrics_are_loadable():
    engine = RiskEngine.load(DEFAULT_ARTIFACT_DIR / "fraud_model.joblib")
    metrics = json.loads((DEFAULT_ARTIFACT_DIR / "training_metrics.json").read_text())
    metadata = json.loads((DEFAULT_ARTIFACT_DIR / "model_metadata.json").read_text())
    schema = json.loads((DEFAULT_ARTIFACT_DIR / "feature_schema.json").read_text())
    assert engine.model_version == "fraudcell-demo-v1"
    assert {
        "accuracy",
        "macro_f1",
        "fraud_recall",
        "confusion_matrix",
        "train_rows",
        "test_rows",
        "random_seed",
        "model_version",
    } <= set(metrics)
    assert metadata["model_type"] == "RandomForestClassifier"
    assert schema["target"] == "fraud_type"


def test_training_is_reproducible(tmp_path):
    first_data = tmp_path / "first.csv"
    second_data = tmp_path / "second.csv"
    first_metrics = train_model(
        dataset_path=first_data, artifact_dir=tmp_path / "first", regenerate_dataset=True
    )
    second_metrics = train_model(
        dataset_path=second_data, artifact_dir=tmp_path / "second", regenerate_dataset=True
    )
    assert first_data.read_bytes() == second_data.read_bytes()
    assert first_metrics == second_metrics
    first_engine = RiskEngine.load(tmp_path / "first" / "fraud_model.joblib")
    second_engine = RiskEngine.load(tmp_path / "second" / "fraud_model.joblib")
    for scenario in scenarios():
        assert first_engine.predict(scenario) == second_engine.predict(scenario)


def test_missing_model_fails_safely(tmp_path):
    with pytest.raises(RuntimeError, match="Required model artifact is missing"):
        RiskEngine.load(tmp_path / "missing.joblib")


def test_scores_vary_and_stay_in_range_with_catalog_and_reasons():
    engine = RiskEngine.load(DEFAULT_ARTIFACT_DIR / "fraud_model.joblib")
    predictions = [engine.predict(item) for item in scenarios()]
    scores = [prediction.risk_score for prediction in predictions]
    assert len(set(scores)) == 3
    assert all(0 <= score <= 1 for score in scores)
    assert all(prediction.fraud_type in FRAUD_TYPES for prediction in predictions)
    assert "Yüksek işlem tutarı" in predictions[2].risk_reasons
    assert "Gece saatinde işlem" in predictions[2].risk_reasons
    assert "Yeni cihaz" in predictions[2].risk_reasons


@pytest.mark.parametrize(
    ("score", "decision", "risk_level"),
    [
        (0.0, "ONAY", "DUSUK"),
        (0.3999, "ONAY", "DUSUK"),
        (0.40, "INCELEME", "ORTA"),
        (0.70, "INCELEME", "YUKSEK"),
        (0.90, "INCELEME", "YUKSEK"),
        (0.9001, "BLOK", "KRITIK"),
        (1.0, "BLOK", "KRITIK"),
    ],
)
def test_decision_and_risk_thresholds(score, decision, risk_level):
    assert decision_for_score(score) == decision
    assert risk_level_for_score(score) == risk_level


def test_low_medium_high_demo_scenarios_use_safe_ranges():
    engine = RiskEngine.load(DEFAULT_ARTIFACT_DIR / "fraud_model.joblib")
    low, medium, high = [engine.predict(item) for item in scenarios()]
    assert low.risk_score < 0.40
    assert low.decision == "ONAY"
    assert low.fraud_type == "TEMIZ"
    assert 0.40 <= medium.risk_score <= 0.90
    assert medium.decision == "INCELEME"
    assert high.risk_score >= 0.70
    assert high.risk_level in {"YUKSEK", "KRITIK"}
    assert low.risk_score < medium.risk_score < high.risk_score
