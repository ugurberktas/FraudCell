#!/usr/bin/env python3
"""Run FraudCell's live AI, worker, and RabbitMQ recovery checks.

The demo must already be reset and prepared. Credentials and tokens are kept in
memory and are never rendered to stdout/stderr.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import subprocess
import sys
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid

from demo_common import (
    DEMO_EMAILS,
    GATEWAY,
    ROOT,
    required_environment,
    seed_or_check_users,
)


GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"


class FaultTestError(RuntimeError):
    """A secret-safe fault-test failure."""


class ApiResult:
    def __init__(self, status: int, body: dict[str, Any]) -> None:
        self.status = status
        self.body = body

    @property
    def data(self) -> Any:
        return self.body.get("data")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FaultTestError(message)


def request_json(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    token: str | None = None,
    expected_status: int = 200,
    timeout: float = 10.0,
) -> ApiResult:
    request_id = f"fault-test-{uuid.uuid4()}"
    headers = {"Content-Type": "application/json", "X-Request-ID": request_id}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        GATEWAY + path,
        data=(json.dumps(payload).encode("utf-8") if payload is not None else None),
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            status = response.status
            response_headers = response.headers
            raw = response.read()
    except HTTPError as exc:
        status = exc.code
        response_headers = exc.headers
        raw = exc.read()
    except (URLError, TimeoutError, OSError) as exc:
        raise FaultTestError(f"{path} is unreachable ({type(exc).__name__})") from exc
    try:
        body = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FaultTestError(f"{path} did not return JSON") from exc
    require(
        status == expected_status,
        f"{path} returned HTTP {status}, expected {expected_status}",
    )
    require(isinstance(body, dict), f"{path} response is not an object")
    require({"success", "data", "error"}.issubset(body), f"{path} response envelope is invalid")
    require(
        response_headers.get("X-Request-ID") == request_id,
        f"{path} did not preserve X-Request-ID",
    )
    require(
        body.get("success") is (expected_status < 400),
        f"{path} success flag does not match HTTP status",
    )
    return ApiResult(status, body)


def fetch_json(url: str, timeout: float = 10.0) -> tuple[int | None, dict[str, Any] | None]:
    request = Request(url, headers={"User-Agent": "FraudCell-FaultTest/2.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read())
    except HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read())
        except (UnicodeDecodeError, json.JSONDecodeError):
            return exc.code, None
    except (URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None, None


def endpoint_is_unavailable(status: int | None) -> bool:
    """Treat a gateway timeout and any upstream 5xx as unavailable."""
    return status is None or status >= 500


def compose(*arguments: str, timeout: float = 90.0) -> str:
    try:
        completed = subprocess.run(
            ["docker", "compose", *arguments],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FaultTestError(f"docker compose failed ({type(exc).__name__})") from exc
    if completed.returncode:
        operation = arguments[0] if arguments else "command"
        raise FaultTestError(f"docker compose {operation} failed")
    return completed.stdout.strip()


def db_scalar(service: str, statement: str) -> str:
    return compose(
        "exec",
        "-T",
        "-e",
        f"FRAUDCELL_SQL={statement}",
        service,
        "sh",
        "-lc",
        'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "$FRAUDCELL_SQL"',
    )


def poll(
    check: Callable[[], Any],
    message: str,
    *,
    timeout: float = 45.0,
    interval: float = 1.0,
) -> Any:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except Exception as exc:  # polling deliberately hides transient details
            last_error = exc
        time.sleep(interval)
    if isinstance(last_error, FaultTestError):
        raise FaultTestError(message) from last_error
    raise FaultTestError(message)


def validated_uuid(value: str, label: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise FaultTestError(f"{label} is not a UUID") from exc


def outbox_state(event_id: str) -> str:
    safe_id = validated_uuid(event_id, "event_id")
    return db_scalar(
        "transaction-db",
        "SELECT CASE WHEN published_at IS NULL THEN 'PENDING' ELSE 'PUBLISHED' END "
        f"FROM outbox_events WHERE event_id = '{safe_id}'::uuid",
    )


def processed_count(event_id: str) -> int:
    safe_id = validated_uuid(event_id, "event_id")
    return int(
        db_scalar(
            "gamification-db",
            f"SELECT count(*) FROM processed_events WHERE event_id = '{safe_id}'::uuid",
        )
    )


def ledger_stats(event_id: str) -> tuple[int, int]:
    safe_id = validated_uuid(event_id, "event_id")
    raw = db_scalar(
        "gamification-db",
        "SELECT count(*)::text || ':' || COALESCE(sum(points), 0)::text "
        f"FROM score_ledger WHERE event_id = '{safe_id}'::uuid",
    )
    try:
        count, points = raw.split(":", 1)
        return int(count), int(points)
    except (ValueError, AttributeError) as exc:
        raise FaultTestError("ScoreLedger query returned an invalid result") from exc


def reset_outbox_for_republish(event_id: str) -> None:
    safe_id = validated_uuid(event_id, "event_id")
    changed = db_scalar(
        "transaction-db",
        "WITH reset_event AS ("
        "UPDATE outbox_events SET published_at = NULL "
        f"WHERE event_id = '{safe_id}'::uuid RETURNING 1"
        ") SELECT count(*) FROM reset_event",
    )
    require(changed == "1", "outbox event could not be prepared for duplicate delivery")


def rabbitmq_queue_counts() -> tuple[int, int] | None:
    queue_name = os.getenv("CASE_DECISION_QUEUE", "gamification.case-decisions.v1")
    output = compose(
        "exec",
        "-T",
        "rabbitmq",
        "rabbitmqctl",
        "-q",
        "list_queues",
        "name",
        "messages_ready",
        "messages_unacknowledged",
    )
    for line in output.splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[0] == queue_name:
            try:
                return int(fields[1]), int(fields[2])
            except ValueError as exc:
                raise FaultTestError("RabbitMQ queue counters are invalid") from exc
    return None


def rabbitmq_event_is_queued() -> bool:
    counts = rabbitmq_queue_counts()
    return counts is not None and counts[0] >= 1


def rabbitmq_queue_drained() -> bool:
    return rabbitmq_queue_counts() == (0, 0)


class FaultRecoveryTest:
    def __init__(self) -> None:
        self.values = required_environment()
        self.users = seed_or_check_users(self.values, check=True)
        self.stopped_services: set[str] = set()
        self.customer = self._customer_login()
        self._validate_prepared_demo()

    @staticmethod
    def _pass(label: str) -> None:
        print(f"[{GREEN}PASS{RESET}] {label}")

    def _validate_prepared_demo(self) -> None:
        expected = set(DEMO_EMAILS.values()) | {"customer"}
        require(set(self.users) == expected, "prepared demo accounts are incomplete")
        for account in self.users.values():
            validated_uuid(account.get("id", ""), "demo user id")

    def _customer_login(self) -> dict[str, Any]:
        request_json(
            "POST",
            "/api/v1/auth/customers/login/otp/request",
            payload={"gsm": self.values["DEMO_CUSTOMER_GSM"]},
        )
        result = request_json(
            "POST",
            "/api/v1/auth/customers/login",
            payload={
                "gsm": self.values["DEMO_CUSTOMER_GSM"],
                "otp_code": self.values["DEMO_OTP_CODE"],
            },
        ).data
        require(result.get("user", {}).get("role") == "CUSTOMER", "customer login role is wrong")
        require(bool(result.get("access_token")), "customer access token is missing")
        return result

    def _analyst_login(self, analyst_id: str) -> dict[str, Any]:
        safe_id = validated_uuid(analyst_id, "assigned analyst id")
        email = next(
            (
                address
                for address in (
                    DEMO_EMAILS["card"],
                    DEMO_EMAILS["account"],
                    DEMO_EMAILS["aml"],
                )
                if self.users[address]["id"] == safe_id
            ),
            None,
        )
        require(email is not None, "AI assigned a non-demo analyst")
        result = request_json(
            "POST",
            "/api/v1/auth/staff/login",
            payload={"email": email, "password": self.values["DEMO_ANALYST_PASSWORD"]},
        ).data
        require(result.get("user", {}).get("role") == "ANALYST", "analyst login role is wrong")
        require(bool(result.get("access_token")), "analyst access token is missing")
        return result

    @staticmethod
    def _transaction_payload(*, high_risk: bool, label: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        occurred_at = now.replace(
            hour=(2 if high_risk else 12), minute=15, second=0, microsecond=0
        ).isoformat().replace("+00:00", "Z")
        if high_risk:
            return {
                "amount": "48500.00",
                "transaction_type": "TRANSFER",
                "recipient": f"Demo Alıcı {label}",
                "source_device": "Yeni iPhone",
                "city": "Berlin",
                "occurred_at": occurred_at,
                "transaction_frequency_24h": 1,
                "is_new_device": True,
                "home_city": "Istanbul",
            }
        return {
            "amount": "250.00",
            "transaction_type": "FATURA",
            "recipient": f"Elektrik Faturası {label}",
            "source_device": "iPhone 15 Pro",
            "city": "Istanbul",
            "occurred_at": occurred_at,
            "transaction_frequency_24h": 2,
            "is_new_device": False,
            "home_city": "Istanbul",
        }

    def _create_transaction(self, *, high_risk: bool, label: str) -> dict[str, Any]:
        result = request_json(
            "POST",
            "/api/v1/transactions/transactions",
            payload=self._transaction_payload(high_risk=high_risk, label=label),
            token=self.customer["access_token"],
            expected_status=201,
        )
        require(result.status == 201, "transaction create did not return HTTP 201")
        return result.data

    def _prepare_high_risk_case(self, label: str) -> dict[str, Any]:
        created = self._create_transaction(high_risk=True, label=label)
        transaction = created.get("transaction") or {}
        risk_case = created.get("case") or {}
        require(created.get("ai_fallback") is False, "high-risk case unexpectedly used AI fallback")
        require(transaction.get("risk_level") in {"YUKSEK", "KRITIK"}, "demo risk is below YUKSEK")
        require(risk_case.get("status") == "ATANDI", "high-risk case is not assigned")
        analyst = self._analyst_login(risk_case.get("assigned_analyst_id", ""))
        case_id = validated_uuid(risk_case.get("id", ""), "case id")
        started = request_json(
            "POST",
            f"/api/v1/transactions/cases/{case_id}/start",
            token=analyst["access_token"],
        ).data
        require(started.get("status") == "INCELENIYOR", "case did not start")
        requested = request_json(
            "POST",
            f"/api/v1/transactions/cases/{case_id}/request-verification",
            token=analyst["access_token"],
        ).data
        require(
            requested.get("status") == "MUSTERI_DOGRULAMA",
            "verification was not requested",
        )
        customer_response = request_json(
            "POST",
            f"/api/v1/transactions/cases/{case_id}/customer-response",
            payload={"response": "BEN_YAPMADIM"},
            token=self.customer["access_token"],
        ).data
        require(
            customer_response.get("status") == "INCELENIYOR",
            "customer response did not return case to review",
        )
        return {
            "case_id": case_id,
            "analyst_token": analyst["access_token"],
            "risk_level": transaction["risk_level"],
        }

    @staticmethod
    def _decide_case(prepared: dict[str, Any]) -> dict[str, Any]:
        decided = request_json(
            "POST",
            f"/api/v1/transactions/cases/{prepared['case_id']}/decision",
            payload={
                "decision": "BLOKLANDI",
                "note": "Fault recovery test: customer denied the transaction.",
            },
            token=prepared["analyst_token"],
        ).data
        require(decided.get("status") == "BLOKLANDI", "case decision was not committed")
        require(decided.get("event_delivery") == "PENDING", "decision did not return PENDING")
        validated_uuid(decided.get("event_id", ""), "decision event id")
        return decided

    def _stop(self, service: str) -> None:
        compose("stop", service)
        self.stopped_services.add(service)

    def _start(self, service: str) -> None:
        compose("start", service)
        self.stopped_services.discard(service)

    @staticmethod
    def _service_running(service: str) -> bool:
        running = set(compose("ps", "--status", "running", "--services").splitlines())
        return service in running

    @staticmethod
    def _expected_points(risk_level: str) -> int:
        return 45 if risk_level == "KRITIK" else 30

    def ai_recovery(self) -> None:
        self._stop("ai-service")
        poll(
            lambda: not self._service_running("ai-service"),
            "AI container did not stop",
            timeout=20,
        )
        poll(
            lambda: endpoint_is_unavailable(
                fetch_json(GATEWAY + "/api/v1/ai/health", timeout=2.0)[0]
            ),
            "AI route did not become unavailable",
            timeout=20,
        )
        for path, service in (
            ("/api/v1/auth/health", "identity-service"),
            ("/api/v1/transactions/health", "transaction-service"),
            ("/api/v1/game/health", "gamification-service"),
        ):
            data = request_json("GET", path).data
            require(data.get("service") == service, f"{service} did not remain healthy")
        fallback = self._create_transaction(high_risk=False, label="AI-FALLBACK")
        transaction = fallback.get("transaction") or {}
        risk_case = fallback.get("case") or {}
        require(fallback.get("ai_fallback") is True, "AI outage did not activate fallback")
        require(transaction.get("ai_status") == "UNAVAILABLE", "fallback ai_status is wrong")
        require(transaction.get("risk_level") == "BELIRSIZ", "fallback risk_level is wrong")
        require(transaction.get("decision") == "INCELEME", "fallback decision is wrong")
        require(risk_case.get("status") == "YENI", "fallback manual case was not created")
        frontend_status, frontend = fetch_json("http://localhost:3000/api/platform-health")
        require(frontend_status == 200 and isinstance(frontend, dict), "frontend health failed")
        statuses = {item.get("name"): item.get("status") for item in frontend.get("services", [])}
        require(statuses.get("ai-service") == "unavailable", "frontend did not isolate AI failure")
        self._pass("AI stopped: HTTP 201 fallback transaction and manual case")

        self._start("ai-service")
        poll(
            lambda: request_json("GET", "/api/v1/ai/health").data.get("status") == "healthy",
            "AI service did not recover",
            timeout=45,
        )
        recovered = self._create_transaction(high_risk=False, label="AI-RECOVERY")
        require(recovered.get("ai_fallback") is False, "AI remained in fallback after recovery")
        require(
            recovered.get("transaction", {}).get("ai_status") == "SCORED",
            "recovery transaction was not scored",
        )
        require(
            bool(recovered.get("ai_result", {}).get("model_version")),
            "recovery model_version is missing",
        )
        self._pass("AI restarted: real scoring recovered")

    def gamification_worker_recovery(self) -> None:
        self._stop("gamification-worker")
        prepared = self._prepare_high_risk_case("WORKER-RECOVERY")
        decided = self._decide_case(prepared)
        event_id = decided["event_id"]
        poll(
            lambda: outbox_state(event_id) == "PUBLISHED",
            "outbox was not published while gamification worker was stopped",
        )
        require(processed_count(event_id) == 0, "event was processed while worker was stopped")
        require(ledger_stats(event_id) == (0, 0), "score was written while worker was stopped")
        poll(
            rabbitmq_event_is_queued,
            "published event was not retained in the durable gamification queue",
            timeout=30,
        )
        self._pass("Gamification worker stopped: decision committed and event queued")

        self._start("gamification-worker")
        poll(
            lambda: self._service_running("gamification-worker"),
            "gamification worker did not restart",
            timeout=30,
        )
        poll(
            lambda: processed_count(event_id) == 1,
            "gamification worker did not consume the queued event",
            timeout=60,
        )
        before = ledger_stats(event_id)
        require(before[0] in {3, 4}, "ScoreLedger reason count is wrong")
        require(
            before[1] == self._expected_points(prepared["risk_level"]),
            "ScoreLedger point total is wrong",
        )
        self._pass("Gamification worker restarted: event consumed exactly once")

        reset_outbox_for_republish(event_id)
        poll(
            lambda: outbox_state(event_id) == "PUBLISHED",
            "duplicate outbox delivery was not published",
        )
        poll(
            rabbitmq_queue_drained,
            "gamification queue did not drain after duplicate delivery",
            timeout=45,
        )
        require(processed_count(event_id) == 1, "duplicate event created a second ProcessedEvent")
        require(ledger_stats(event_id) == before, "duplicate event changed ScoreLedger")
        self._pass("Duplicate delivery: ProcessedEvent and ScoreLedger stayed idempotent")

    def rabbitmq_recovery(self) -> None:
        prepared = self._prepare_high_risk_case("RABBIT-RECOVERY")
        self._stop("rabbitmq")
        decided = self._decide_case(prepared)
        event_id = decided["event_id"]
        require(outbox_state(event_id) == "PENDING", "outbox did not stay PENDING")
        case_status = db_scalar(
            "transaction-db",
            f"SELECT status::text FROM risk_cases WHERE id = '{prepared['case_id']}'::uuid",
        )
        require(case_status == "BLOKLANDI", "case decision was not durable with RabbitMQ down")
        require(processed_count(event_id) == 0, "RabbitMQ-down event was already processed")
        self._pass("RabbitMQ stopped: decision committed and outbox stayed PENDING")

        compose("start", "rabbitmq")
        poll(
            lambda: self._rabbitmq_healthy(),
            "RabbitMQ did not recover",
            timeout=60,
        )
        self.stopped_services.discard("rabbitmq")
        poll(
            lambda: outbox_state(event_id) == "PUBLISHED",
            "pending outbox event was not published after RabbitMQ recovery",
            timeout=75,
        )
        poll(
            lambda: processed_count(event_id) == 1,
            "recovered RabbitMQ event was not consumed",
            timeout=75,
        )
        stats = ledger_stats(event_id)
        require(stats[0] in {3, 4}, "recovered event ScoreLedger reason count is wrong")
        require(
            stats[1] == self._expected_points(prepared["risk_level"]),
            "recovered event ScoreLedger point total is wrong",
        )
        self._pass("RabbitMQ restarted: pending event published and consumed once")

    @staticmethod
    def _rabbitmq_healthy() -> bool:
        try:
            compose("exec", "-T", "rabbitmq", "rabbitmq-diagnostics", "-q", "ping")
            return True
        except FaultTestError:
            return False

    def recover_stopped_services(self) -> bool:
        success = True
        for service in ("rabbitmq", "gamification-worker", "ai-service"):
            if service not in self.stopped_services:
                continue
            try:
                compose("start", service)
                self.stopped_services.discard(service)
            except Exception:
                success = False
                print(f"[{RED}FAIL{RESET}] Safety recovery could not restart {service}")
        return success

    def run(self) -> int:
        print("=" * 68)
        print("FraudCell live fault recovery test")
        print("=" * 68)
        self.ai_recovery()
        self.gamification_worker_recovery()
        self.rabbitmq_recovery()
        print(f"[{GREEN}PASS{RESET}] ALL FAULT RECOVERY TESTS PASSED")
        return 0


def main() -> int:
    test: FaultRecoveryTest | None = None
    result = 1
    try:
        test = FaultRecoveryTest()
        result = test.run()
    except Exception as exc:
        message = str(exc) if isinstance(exc, FaultTestError) else type(exc).__name__
        print(f"[{RED}FAIL{RESET}] Fault recovery test: {message}")
        result = 1
    finally:
        if test is not None and not test.recover_stopped_services():
            result = 1
    return result


if __name__ == "__main__":
    sys.exit(main())
