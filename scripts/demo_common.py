"""Shared, secret-safe orchestration helpers for FraudCell demo scripts."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
GATEWAY = os.getenv("DEMO_GATEWAY_URL", "http://localhost:8000").rstrip("/")
HEALTH_PATHS = {
    "Identity": "/api/v1/auth/health",
    "Transaction": "/api/v1/transactions/health",
    "AI": "/api/v1/ai/health",
    "Gamification": "/api/v1/game/health",
}
DEMO_EMAILS = {
    "admin": "demo.admin@fraudcell.com",
    "supervisor": "demo.supervisor@fraudcell.com",
    "card": "demo.analyst.card@fraudcell.com",
    "account": "demo.analyst.account@fraudcell.com",
    "aml": "demo.analyst.aml@fraudcell.com",
}


def _parse_dotenv_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    key, value = stripped.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not key:
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value


def load_root_dotenv(required_names: tuple[str, ...]) -> None:
    missing_before = [name for name in required_names if not os.getenv(name, "").strip()]
    if not missing_before:
        return
    dotenv = ROOT / ".env"
    if not dotenv.exists():
        raise RuntimeError("Root .env file is missing. Copy .env.example to .env and set demo secrets.")
    allowed = set(required_names)
    for line in dotenv.read_text(encoding="utf-8").splitlines():
        parsed = _parse_dotenv_line(line)
        if not parsed:
            continue
        key, value = parsed
        if key in allowed and not os.getenv(key):
            os.environ[key] = value


def required_environment() -> dict[str, str]:
    names = (
        "DEMO_ADMIN_PASSWORD",
        "DEMO_SUPERVISOR_PASSWORD",
        "DEMO_ANALYST_PASSWORD",
        "DEMO_CUSTOMER_GSM",
        "DEMO_OTP_CODE",
        "INTERNAL_SERVICE_KEY",
    )
    load_root_dotenv(names)
    values = {name: os.getenv(name, "") for name in names}
    missing = [name for name, value in values.items() if not value.strip()]
    if missing:
        raise RuntimeError("Missing required environment variables:\n" + "\n".join(missing))
    return values


def compose_exec(service: str, module: str, environment: dict[str, str], *arguments: str) -> str:
    command = ["docker", "compose", "exec", "-T"]
    for key, value in environment.items():
        command.extend(("-e", f"{key}={value}"))
    command.extend((service, "python", "-m", module, *arguments))
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if completed.returncode:
        safe_output = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"{service}/{module} failed: {safe_output}")
    return completed.stdout


def marker_json(output: str, marker: str) -> dict:
    for line in output.splitlines():
        if line.startswith(marker):
            return json.loads(line[len(marker):])
    raise RuntimeError(f"Expected marker was not produced: {marker}")


def http_json(method: str, path: str, payload: dict | None = None, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json", "X-Request-ID": "fraudcell-demo-script"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(GATEWAY + path, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=10) as response:
            result = json.loads(response.read())
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} for {path}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Service request failed for {path}: {type(exc).__name__}") from exc
    if not result.get("success", False):
        code = (result.get("error") or {}).get("code", "UNKNOWN_ERROR")
        raise RuntimeError(f"{path} returned {code}")
    return result["data"]


def check_health() -> None:
    for name, path in HEALTH_PATHS.items():
        data = http_json("GET", path)
        if data.get("status") != "healthy":
            raise RuntimeError(f"{name} is not healthy")


def identity_environment(values: dict[str, str]) -> dict[str, str]:
    return {key: values[key] for key in (
        "DEMO_ADMIN_PASSWORD", "DEMO_SUPERVISOR_PASSWORD", "DEMO_ANALYST_PASSWORD",
        "DEMO_CUSTOMER_GSM", "DEMO_OTP_CODE",
    )}


def analyst_environment(users: dict[str, dict[str, str]]) -> dict[str, str]:
    return {
        "DEMO_CARD_ANALYST_ID": users[DEMO_EMAILS["card"]]["id"],
        "DEMO_ACCOUNT_ANALYST_ID": users[DEMO_EMAILS["account"]]["id"],
        "DEMO_AML_ANALYST_ID": users[DEMO_EMAILS["aml"]]["id"],
    }


def seed_or_check_users(values: dict[str, str], *, check: bool = False) -> dict:
    arguments = ("--check",) if check else ()
    output = compose_exec(
        "identity-service",
        "app.cli.seed_demo_users",
        identity_environment(values),
        *arguments,
    )
    return marker_json(output, "DEMO_USERS_JSON=")


def lookup_users(customer_gsm: str) -> dict:
    output = compose_exec(
        "identity-service",
        "app.cli.demo_user_info",
        {"DEMO_CUSTOMER_GSM": customer_gsm},
    )
    return marker_json(output, "DEMO_USERS_JSON=")


def customer_login(values: dict[str, str]) -> dict:
    gsm = values["DEMO_CUSTOMER_GSM"]
    http_json("POST", "/api/v1/auth/customers/login/otp/request", {"gsm": gsm})
    return http_json(
        "POST",
        "/api/v1/auth/customers/login",
        {"gsm": gsm, "otp_code": values["DEMO_OTP_CODE"]},
    )


def staff_login(email: str, password: str) -> dict:
    return http_json("POST", "/api/v1/auth/staff/login", {"email": email, "password": password})


def compose_services() -> set[str]:
    completed = subprocess.run(
        ["docker", "compose", "ps", "--status", "running", "--services"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if completed.returncode:
        raise RuntimeError("docker compose ps failed")
    return set(completed.stdout.split())


def rabbitmq_ping() -> None:
    completed = subprocess.run(
        ["docker", "compose", "exec", "-T", "rabbitmq", "rabbitmq-diagnostics", "-q", "ping"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if completed.returncode:
        raise RuntimeError("RabbitMQ is not reachable")
