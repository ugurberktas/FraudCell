#!/usr/bin/env python3
"""Verify that the complete live demo is prepared and usable."""
from __future__ import annotations

import sys

from demo_common import (
    DEMO_EMAILS,
    analyst_environment,
    check_health,
    compose_exec,
    compose_services,
    customer_login,
    http_json,
    rabbitmq_ping,
    required_environment,
    seed_or_check_users,
    staff_login,
)


def passed(label: str) -> None:
    print(f"[PASS] {label}")


def main() -> int:
    try:
        values = required_environment()
        check_health()
        for label in ("Identity", "Transaction", "AI", "Gamification"):
            passed(label)
        rabbitmq_ping()
        passed("RabbitMQ")
        users = seed_or_check_users(values, check=True)
        passed("Demo users")
        analyst_env = analyst_environment(users)
        compose_exec("ai-service", "app.cli.seed_demo_analysts", analyst_env, "--check")
        compose_exec("gamification-service", "app.cli.seed_demo_profiles", analyst_env, "--check")
        passed("Analyst profiles")
        running = compose_services()
        required_workers = {"transaction-outbox-worker", "gamification-worker"}
        if not required_workers.issubset(running):
            raise RuntimeError("Demo workers are not running")
        passed("Workers")
        customer_login(values)
        staff_login(DEMO_EMAILS["admin"], values["DEMO_ADMIN_PASSWORD"])
        staff_login(DEMO_EMAILS["supervisor"], values["DEMO_SUPERVISOR_PASSWORD"])
        analyst = staff_login(DEMO_EMAILS["card"], values["DEMO_ANALYST_PASSWORD"])
        http_json("GET", "/api/v1/game/leaderboard?period=daily&limit=10", token=analyst["access_token"])
        passed("Demo login")
        print("DEMO READY")
        return 0
    except Exception as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
