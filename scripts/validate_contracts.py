#!/usr/bin/env python3
"""FraudCell Contract & Event Catalog Validation Script.

Validates all JSON contract examples, domain enums, and event envelopes using standard library only.
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sys
import uuid

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"

BASE_DIR = Path(__file__).resolve().parent.parent
CONTRACTS_DIR = BASE_DIR / "contracts"
EVENTS_DIR = CONTRACTS_DIR / "events"

CATALOG_EVENT_TYPES = {
    "transaction.created",
    "transaction.scored",
    "case.assigned",
    "case.decision_made",
    "transaction.blocked",
    "fraud_type.changed",
    "customer.verified",
    "sla.exceeded",
    "feedback.submitted",
    "badge.earned",
}


def validate_api_response_example(path: Path) -> bool:
    """Validate api-response.example.json schema."""
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    required_keys = {"success", "data", "error"}
    missing = required_keys - set(data.keys())
    if missing:
        print(f"[{RED}FAIL{RESET}] api-response.example.json missing keys: {missing}")
        return False

    if not isinstance(data["success"], bool):
        print(f"[{RED}FAIL{RESET}] api-response.example.json 'success' field must be boolean")
        return False

    print(f"[{GREEN}PASS{RESET}] api-response.example.json is valid")
    return True


def validate_api_error_example(path: Path) -> bool:
    """Validate api-error.example.json schema."""
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    required_keys = {"success", "data", "error"}
    missing = required_keys - set(data.keys())
    if missing:
        print(f"[{RED}FAIL{RESET}] api-error.example.json missing keys: {missing}")
        return False

    err = data.get("error")
    if not isinstance(err, dict):
        print(f"[{RED}FAIL{RESET}] api-error.example.json 'error' field must be an object")
        return False

    err_keys = {"code", "message", "details"}
    err_missing = err_keys - set(err.keys())
    if err_missing:
        print(f"[{RED}FAIL{RESET}] api-error.example.json error object missing keys: {err_missing}")
        return False

    print(f"[{GREEN}PASS{RESET}] api-error.example.json is valid")
    return True


def validate_event_envelope_example(path: Path) -> bool:
    """Validate event-envelope.example.json schema."""
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    return validate_event_envelope_data(data, path.name)


def validate_domain_enums(path: Path) -> bool:
    """Validate domain-enums.json schema and uniqueness."""
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    required_enums = {
        "roles",
        "transaction_types",
        "fraud_types",
        "ai_decisions",
        "risk_levels",
        "case_statuses",
        "customer_responses",
    }
    missing = required_enums - set(data.keys())
    if missing:
        print(f"[{RED}FAIL{RESET}] domain-enums.json missing enum categories: {missing}")
        return False

    all_ok = True
    for cat in required_enums:
        items = data.get(cat)
        if not isinstance(items, list):
            print(f"[{RED}FAIL{RESET}] domain-enums.json '{cat}' must be an array")
            all_ok = False
            continue
        if len(items) != len(set(items)):
            print(f"[{RED}FAIL{RESET}] domain-enums.json '{cat}' contains duplicate elements!")
            all_ok = False

    if all_ok:
        print(f"[{GREEN}PASS{RESET}] domain-enums.json is valid and contains no duplicate enums")
    return all_ok


def validate_event_envelope_data(data: dict, filename: str) -> bool:
    """Helper to validate event envelope field constraints."""
    required_keys = {
        "event_id",
        "event_type",
        "event_version",
        "occurred_at",
        "producer",
        "correlation_id",
        "payload",
    }
    missing = required_keys - set(data.keys())
    if missing:
        print(f"[{RED}FAIL{RESET}] {filename} missing required envelope keys: {missing}")
        return False

    # Check event_id UUID
    try:
        uuid.UUID(str(data["event_id"]))
    except (ValueError, TypeError):
        print(f"[{RED}FAIL{RESET}] {filename} 'event_id' is not a valid UUID: {data['event_id']}")
        return False

    # Check correlation_id UUID
    try:
        uuid.UUID(str(data["correlation_id"]))
    except (ValueError, TypeError):
        print(f"[{RED}FAIL{RESET}] {filename} 'correlation_id' is not a valid UUID: {data['correlation_id']}")
        return False

    # Check event_type is in catalog
    event_type = data.get("event_type")
    if event_type not in CATALOG_EVENT_TYPES:
        print(f"[{RED}FAIL{RESET}] {filename} 'event_type' '{event_type}' not in canonical catalog!")
        return False

    # Check event_version is positive int
    version = data.get("event_version")
    if not isinstance(version, int) or version <= 0:
        print(f"[{RED}FAIL{RESET}] {filename} 'event_version' must be a positive integer, got: {version}")
        return False

    # Check occurred_at is timezone-aware UTC datetime string
    occurred_at_str = str(data.get("occurred_at"))
    try:
        # Standard library datetime parsing ISO 8601
        dt_val = datetime.fromisoformat(occurred_at_str.replace("Z", "+00:00"))
        if dt_val.tzinfo is None or dt_val.tzinfo.utcoffset(dt_val) is None:
            print(f"[{RED}FAIL{RESET}] {filename} 'occurred_at' is naive (missing timezone): {occurred_at_str}")
            return False
    except ValueError as exc:
        print(f"[{RED}FAIL{RESET}] {filename} 'occurred_at' invalid ISO-8601 timestamp: {exc}")
        return False

    # Check payload is dict
    if not isinstance(data.get("payload"), dict):
        print(f"[{RED}FAIL{RESET}] {filename} 'payload' must be an object")
        return False

    print(f"[{GREEN}PASS{RESET}] {filename:<35} -> Envelope valid (type={event_type}, version={version})")
    return True


def validate_event_files() -> bool:
    """Validate all event files in contracts/events/."""
    if not EVENTS_DIR.exists():
        print(f"[{RED}FAIL{RESET}] Events directory missing: {EVENTS_DIR}")
        return False

    all_passed = True
    event_files = sorted(list(EVENTS_DIR.glob("*.json")))

    if len(event_files) < 10:
        print(f"[{RED}FAIL{RESET}] Expected at least 10 event JSON contracts, found {len(event_files)}")
        all_passed = False

    for file_path in event_files:
        try:
            with file_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not validate_event_envelope_data(data, file_path.name):
                all_passed = False
        except json.JSONDecodeError as exc:
            print(f"[{RED}FAIL{RESET}] {file_path.name} is not valid JSON: {exc}")
            all_passed = False
        except Exception as exc:
            print(f"[{RED}FAIL{RESET}] Unexpected error validating {file_path.name}: {exc}")
            all_passed = False

    return all_passed


def main() -> int:
    print("=" * 60)
    print("📋 FraudCell Technical Contracts & Event Catalog Validator")
    print("=" * 60)

    if not CONTRACTS_DIR.exists():
        print(f"[{RED}FAIL{RESET}] Contracts directory does not exist at {CONTRACTS_DIR}")
        return 1

    all_passed = True

    print("\n🔍 1. Top-Level API Contracts & Enums")
    print("-" * 60)
    files_and_validators = [
        ("api-response.example.json", validate_api_response_example),
        ("api-error.example.json", validate_api_error_example),
        ("event-envelope.example.json", validate_event_envelope_example),
        ("domain-enums.json", validate_domain_enums),
    ]

    for filename, validator in files_and_validators:
        file_path = CONTRACTS_DIR / filename
        if not file_path.exists():
            print(f"[{RED}FAIL{RESET}] Contract file missing: {filename}")
            all_passed = False
            continue

        try:
            if not validator(file_path):
                all_passed = False
        except json.JSONDecodeError as exc:
            print(f"[{RED}FAIL{RESET}] {filename} is not valid JSON: {exc}")
            all_passed = False
        except Exception as exc:
            print(f"[{RED}FAIL{RESET}] Unexpected error validating {filename}: {exc}")
            all_passed = False

    print("\n⚡ 2. Domain Event JSON Contracts (contracts/events/*.json)")
    print("-" * 60)
    if not validate_event_files():
        all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print(f"🎉 {GREEN}ALL CONTRACT & EVENT VALIDATIONS PASSED SUCCESSFULLY!{RESET}")
        print("=" * 60)
        return 0
    print(f"❌ {RED}SOME CONTRACT VALIDATIONS FAILED!{RESET}")
    print("=" * 60)
    return 1


if __name__ == "__main__":
    sys.exit(main())
