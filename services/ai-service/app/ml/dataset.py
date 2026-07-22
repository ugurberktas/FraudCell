"""Deterministic noisy synthetic FraudCell training dataset."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from math import exp, log1p
from pathlib import Path

import numpy as np


RANDOM_SEED = 20260723
DEFAULT_ROWS = 2400
FRAUD_TYPES = [
    "CALINTI_KART",
    "HESAP_ELE_GECIRME",
    "PARA_AKLAMA",
    "SUPHELI_DAVRANIS",
    "TEMIZ",
]
TRANSACTION_TYPES = ["ODEME", "TRANSFER", "FATURA", "CEKIM"]
HOME_CITIES = ["Istanbul", "Ankara", "Izmir", "Berlin"]
OTHER_CITIES = ["Berlin", "London", "Dubai", "Moscow", "New York", "Paris"]
DEVICES = ["iPhone 15 Pro", "Android Phone", "Web Browser", "Samsung Galaxy"]
NEW_DEVICES = ["New Android Device", "New iPhone", "Unknown Web Browser"]
CSV_COLUMNS = [
    "amount",
    "transaction_type",
    "recipient",
    "source_device",
    "city",
    "occurred_at",
    "transaction_frequency_24h",
    "is_new_device",
    "home_city",
    "fraud_type",
]


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + exp(-value))


def generate_dataset(
    output_path: str | Path,
    *,
    rows: int = DEFAULT_ROWS,
    random_seed: int = RANDOM_SEED,
) -> Path:
    """Generate overlapping/noisy examples; no single feature determines a label."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(random_seed)
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    records: list[dict[str, object]] = []

    for index in range(rows):
        transaction_type = str(
            rng.choice(TRANSACTION_TYPES, p=[0.30, 0.34, 0.23, 0.13])
        )
        home_city = str(rng.choice(HOME_CITIES))
        mismatch = bool(rng.random() < 0.28)
        city = str(rng.choice(OTHER_CITIES)) if mismatch else home_city
        is_new_device = bool(rng.random() < 0.25)
        source_device = str(rng.choice(NEW_DEVICES if is_new_device else DEVICES))
        hour = int(rng.integers(0, 24))
        frequency = int(min(20, max(1, round(rng.gamma(shape=2.0, scale=2.3)))))
        amount = float(
            min(
                250_000,
                max(10, rng.lognormal(mean=8.25, sigma=1.25)),
            )
        )

        risk_logit = (
            -4.50
            + 0.65 * log1p(amount / 1000.0)
            + 1.00 * float(hour < 6 or hour >= 23)
            + 1.00 * float(is_new_device)
            + 1.00 * float(mismatch)
            + 0.12 * frequency
            + 0.35 * float(transaction_type == "TRANSFER")
            - 0.30 * float(transaction_type == "FATURA")
            + float(rng.normal(0, 0.60))
        )
        is_fraud = bool(rng.random() < _sigmoid(risk_logit))

        # Small independent flips guarantee overlap and prevent deterministic labels.
        if rng.random() < 0.035:
            is_fraud = not is_fraud

        if not is_fraud:
            fraud_type = "TEMIZ"
        else:
            type_scores = {
                "CALINTI_KART": (
                    1.45 * float(transaction_type in {"ODEME", "CEKIM"})
                    + 0.85 * float(hour < 6 or hour >= 23)
                    + 0.70 * float(is_new_device)
                ),
                "HESAP_ELE_GECIRME": (
                    1.55 * float(is_new_device)
                    + 1.10 * float(mismatch)
                    + 0.07 * frequency
                ),
                "PARA_AKLAMA": (
                    1.50 * float(transaction_type == "TRANSFER")
                    + 0.55 * log1p(amount / 1000.0)
                ),
                "SUPHELI_DAVRANIS": (
                    0.16 * frequency
                    + 0.60 * float(hour < 6 or hour >= 23)
                    + 0.50 * float(mismatch)
                ),
            }
            fraud_type = max(
                type_scores,
                key=lambda item: type_scores[item] + float(rng.normal(0, 0.75)),
            )
            if rng.random() < 0.05:
                fraud_type = str(rng.choice(list(type_scores)))

        occurred_at = base_time + timedelta(days=index % 180, hours=hour)
        records.append(
            {
                "amount": f"{amount:.2f}",
                "transaction_type": transaction_type,
                "recipient": f"Synthetic Recipient {index % 71:02d}",
                "source_device": source_device,
                "city": city,
                "occurred_at": occurred_at.isoformat().replace("+00:00", "Z"),
                "transaction_frequency_24h": frequency,
                "is_new_device": str(is_new_device).lower(),
                "home_city": home_city,
                "fraud_type": fraud_type,
            }
        )

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(records)
    return path


def load_dataset(path: str | Path) -> tuple[list[dict[str, object]], list[str]]:
    from app.ml.features import build_features

    features: list[dict[str, object]] = []
    labels: list[str] = []
    with Path(path).open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            values = {
                **row,
                "amount": float(row["amount"]),
                "transaction_frequency_24h": int(row["transaction_frequency_24h"]),
                "is_new_device": row["is_new_device"].lower() == "true",
            }
            features.append(build_features(values))
            labels.append(row["fraud_type"])
    return features, labels
