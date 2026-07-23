#!/usr/bin/env python3
"""Safely reset only operational data belonging to fixed demo accounts."""
from __future__ import annotations

import argparse
import json
import sys

from demo_common import (
    DEMO_EMAILS,
    ROOT,
    analyst_environment,
    compose_exec,
    load_root_dotenv,
    lookup_users,
    marker_json,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm")
    args = parser.parse_args(argv)
    if args.confirm != "RESET_DEMO":
        print("Refusing reset: use --confirm RESET_DEMO", file=sys.stderr)
        return 1
    try:
        if (ROOT / ".env").exists():
            load_root_dotenv(("DEMO_CUSTOMER_GSM",))
        customer_gsm = __import__("os").getenv("DEMO_CUSTOMER_GSM", "05550000001")
        users = lookup_users(customer_gsm)
        if not users:
            print(json.dumps({"transaction": {"transactions": 0, "events": 0}, "analysts": []}))
            print("DEMO RESET COMPLETE")
            return 0
        expected = set(DEMO_EMAILS.values()) | {"customer"}
        if set(users) != expected:
            missing = sorted(expected - set(users))
            raise RuntimeError("Partial demo identity set; missing: " + ", ".join(missing))
        analyst_env = analyst_environment(users)
        tx_output = compose_exec(
            "transaction-service",
            "app.cli.reset_demo_data",
            {"DEMO_CUSTOMER_ID": users["customer"]["id"]},
        )
        tx_result = marker_json(tx_output, "DEMO_RESET_JSON=")
        game_env = dict(analyst_env)
        game_env["DEMO_EVENT_IDS"] = ",".join(tx_result["event_ids"])
        compose_exec("gamification-service", "app.cli.reset_demo_profiles", game_env)
        compose_exec("ai-service", "app.cli.reset_demo_analysts", analyst_env)
        compose_exec(
            "identity-service",
            "app.cli.reset_demo_identity",
            {"DEMO_CUSTOMER_GSM": customer_gsm},
        )
        print(json.dumps({"transaction": tx_result, "analysts": list(analyst_env.values())}, sort_keys=True))
        print("DEMO RESET COMPLETE")
        return 0
    except Exception as exc:
        print(f"DEMO RESET FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
