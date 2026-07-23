#!/usr/bin/env python3
"""Prepare every deterministic FraudCell demo identity/profile in one command."""
from __future__ import annotations

import sys

from demo_common import (
    DEMO_EMAILS,
    analyst_environment,
    check_health,
    compose_exec,
    customer_login,
    required_environment,
    seed_or_check_users,
    staff_login,
)


def main() -> int:
    try:
        values = required_environment()
        print("[1/8] Platform health")
        check_health()
        print("[2/8] Identity demo users")
        users = seed_or_check_users(values)
        analyst_env = analyst_environment(users)
        print("[3/8] AI analyst profiles")
        compose_exec("ai-service", "app.cli.seed_demo_analysts", analyst_env)
        print("[4/8] Gamification profiles")
        compose_exec("gamification-service", "app.cli.seed_demo_profiles", analyst_env)
        print("[5/8] Demo customer")
        if users["customer"]["role"] != "CUSTOMER":
            raise RuntimeError("Demo customer role is invalid")
        print("[6/8] Customer login smoke")
        customer_login(values)
        print("[7/8] Staff login smoke")
        staff_login(DEMO_EMAILS["admin"], values["DEMO_ADMIN_PASSWORD"])
        staff_login(DEMO_EMAILS["supervisor"], values["DEMO_SUPERVISOR_PASSWORD"])
        staff_login(DEMO_EMAILS["card"], values["DEMO_ANALYST_PASSWORD"])
        print("[8/8] Platform summary")
        for email in DEMO_EMAILS.values():
            account = users[email]
            print(f"{email} {account['role']} {account['id']}")
        print(f"{users['customer']['gsm']} CUSTOMER {users['customer']['id']}")
        print("DEMO READY")
        return 0
    except Exception as exc:
        print(f"DEMO PREPARE FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
