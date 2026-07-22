"""Shared feature extraction for training and inference."""
from __future__ import annotations

from datetime import datetime
from math import log1p
from typing import Any, Mapping


FEATURE_NAMES = [
    "log_amount",
    "transaction_type",
    "hour",
    "is_night",
    "transaction_frequency_24h",
    "is_new_device",
    "city_mismatch",
    "city",
    "device_family",
    "recipient_length",
]


def normalize_city(value: str) -> str:
    return value.strip().upper().replace("İ", "I")


def device_family(value: str) -> str:
    normalized = value.strip().lower()
    if "iphone" in normalized or "ipad" in normalized:
        return "APPLE"
    if "android" in normalized or "samsung" in normalized:
        return "ANDROID"
    if "web" in normalized or "browser" in normalized:
        return "WEB"
    return "OTHER"


def build_features(values: Mapping[str, Any]) -> dict[str, float | str]:
    occurred_at = values["occurred_at"]
    if isinstance(occurred_at, str):
        occurred_at = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
    city = normalize_city(str(values["city"]))
    home_value = values.get("home_city")
    home_city = normalize_city(str(home_value)) if home_value else city
    amount = float(values["amount"])
    frequency = int(values.get("transaction_frequency_24h") or 1)
    is_new_device = bool(values.get("is_new_device") or False)
    hour = int(occurred_at.hour)
    transaction_type = values["transaction_type"]
    transaction_type_value = getattr(transaction_type, "value", str(transaction_type))
    return {
        "log_amount": round(log1p(max(amount, 0.0) / 1000.0), 8),
        "transaction_type": str(transaction_type_value),
        "hour": float(hour),
        "is_night": float(hour < 6 or hour >= 23),
        "transaction_frequency_24h": float(frequency),
        "is_new_device": float(is_new_device),
        "city_mismatch": float(city != home_city),
        "city": city,
        "device_family": device_family(str(values["source_device"])),
        "recipient_length": float(len(str(values["recipient"]).strip())),
    }


def risk_reasons(values: Mapping[str, Any]) -> list[str]:
    occurred_at = values["occurred_at"]
    if isinstance(occurred_at, str):
        occurred_at = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
    reasons: list[str] = []
    if float(values["amount"]) >= 20_000:
        reasons.append("Yüksek işlem tutarı")
    if occurred_at.hour < 6 or occurred_at.hour >= 23:
        reasons.append("Gece saatinde işlem")
    home_city = values.get("home_city")
    if home_city and normalize_city(str(values["city"])) != normalize_city(str(home_city)):
        reasons.append("Alışılmadık şehir")
    if bool(values.get("is_new_device") or False):
        reasons.append("Yeni cihaz")
    if int(values.get("transaction_frequency_24h") or 1) >= 8:
        reasons.append("Yüksek işlem sıklığı")
    return reasons or ["Belirgin risk sinyali yok"]
