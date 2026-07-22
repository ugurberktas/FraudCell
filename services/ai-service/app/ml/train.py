"""Deterministic model training entry point: python -m app.ml.train."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from app.ml.dataset import (
    DEFAULT_ROWS,
    FRAUD_TYPES,
    RANDOM_SEED,
    generate_dataset,
    load_dataset,
)
from app.ml.features import FEATURE_NAMES


MODEL_VERSION = "fraudcell-demo-v1"
SERVICE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_PATH = SERVICE_ROOT / "data" / "synthetic_fraud_transactions.csv"
DEFAULT_ARTIFACT_DIR = SERVICE_ROOT / "artifacts"


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def train_model(
    *,
    dataset_path: str | Path = DEFAULT_DATASET_PATH,
    artifact_dir: str | Path = DEFAULT_ARTIFACT_DIR,
    regenerate_dataset: bool = True,
) -> dict[str, Any]:
    dataset_path = Path(dataset_path)
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    if regenerate_dataset or not dataset_path.exists():
        generate_dataset(dataset_path, rows=DEFAULT_ROWS, random_seed=RANDOM_SEED)

    features, labels = load_dataset(dataset_path)
    x_train, x_test, y_train, y_test = train_test_split(
        features,
        labels,
        test_size=0.25,
        random_state=RANDOM_SEED,
        stratify=labels,
    )
    pipeline = Pipeline(
        [
            ("vectorizer", DictVectorizer(sparse=False)),
            (
                "classifier",
                RandomForestClassifier(
                    n_estimators=80,
                    max_depth=10,
                    min_samples_leaf=3,
                    class_weight="balanced_subsample",
                    random_state=RANDOM_SEED,
                    n_jobs=1,
                ),
            ),
        ]
    )
    pipeline.fit(x_train, y_train)
    predictions = pipeline.predict(x_test)
    fraud_truth = [label != "TEMIZ" for label in y_test]
    fraud_predictions = [label != "TEMIZ" for label in predictions]
    metrics = {
        "accuracy": round(float(accuracy_score(y_test, predictions)), 6),
        "macro_f1": round(float(f1_score(y_test, predictions, average="macro")), 6),
        "fraud_recall": round(
            float(recall_score(fraud_truth, fraud_predictions, zero_division=0)), 6
        ),
        "confusion_matrix": confusion_matrix(
            y_test, predictions, labels=FRAUD_TYPES
        ).tolist(),
        "confusion_matrix_labels": FRAUD_TYPES,
        "train_rows": len(x_train),
        "test_rows": len(x_test),
        "total_rows": len(features),
        "random_seed": RANDOM_SEED,
        "model_version": MODEL_VERSION,
    }
    artifact_path = artifact_dir / "fraud_model.joblib"
    joblib.dump(
        {
            "pipeline": pipeline,
            "model_version": MODEL_VERSION,
            "classes": list(pipeline.classes_),
            "random_seed": RANDOM_SEED,
        },
        artifact_path,
        compress=3,
    )
    dataset_hash = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    artifact_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    metadata = {
        "model_version": MODEL_VERSION,
        "model_type": "RandomForestClassifier",
        "training_data": "deterministic synthetic FraudCell demo data",
        "dataset_sha256": dataset_hash,
        "artifact_sha256": artifact_hash,
        "random_seed": RANDOM_SEED,
        "classes": list(pipeline.classes_),
    }
    feature_schema = {
        "model_version": MODEL_VERSION,
        "features": FEATURE_NAMES,
        "input_fields": [
            "amount",
            "transaction_type",
            "recipient",
            "source_device",
            "city",
            "occurred_at",
            "transaction_frequency_24h",
            "is_new_device",
            "home_city",
        ],
        "target": "fraud_type",
    }
    _write_json(artifact_dir / "model_metadata.json", metadata)
    _write_json(artifact_dir / "training_metrics.json", metrics)
    _write_json(artifact_dir / "feature_schema.json", feature_schema)
    return metrics


def main() -> None:
    metrics = train_model()
    print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
