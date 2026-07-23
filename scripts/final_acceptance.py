#!/usr/bin/env python3
"""Run the live FraudCell golden-path acceptance without exposing credentials."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import subprocess
import sys
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import uuid

from demo_common import DEMO_EMAILS, GATEWAY, ROOT, required_environment, seed_or_check_users


class AcceptanceError(RuntimeError):
    """A secret-safe acceptance assertion failure."""


class ApiResult:
    def __init__(self, status: int, body: dict[str, Any], headers: Any) -> None:
        self.status = status
        self.body = body
        self.headers = headers

    @property
    def data(self) -> Any:
        return self.body.get("data")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceError(message)


def request_json(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    token: str | None = None,
    expected_status: int = 200,
    timeout: float = 10.0,
) -> ApiResult:
    request_id = f"final-acceptance-{uuid.uuid4()}"
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
        raise AcceptanceError(f"{path} is unreachable ({type(exc).__name__})") from exc
    try:
        body = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceError(f"{path} did not return JSON") from exc
    require(status == expected_status, f"{path} returned HTTP {status}, expected {expected_status}")
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
    return ApiResult(status, body, response_headers)


def compose(*arguments: str, timeout: float = 60.0) -> str:
    try:
        completed = subprocess.run(
            ["docker", "compose", *arguments],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AcceptanceError(f"docker compose failed ({type(exc).__name__})") from exc
    if completed.returncode:
        raise AcceptanceError(f"docker compose {' '.join(arguments[:2])} failed")
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


def poll(check: Callable[[], Any], message: str, *, timeout: float = 30.0) -> Any:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except Exception as exc:  # retries are intentionally secret-safe
            last_error = exc
        time.sleep(1)
    if isinstance(last_error, AcceptanceError):
        raise AcceptanceError(message) from last_error
    raise AcceptanceError(message)


class Acceptance:
    def __init__(self) -> None:
        self.values = required_environment()
        self.results: dict[str, Any] = {}
        self.failures: list[str] = []
        self.ai_stopped = False

    def step(self, key: str, label: str, action: Callable[[], Any]) -> Any:
        try:
            value = action()
            self.results[key] = value
            print(f"[PASS] {label}")
            return value
        except Exception as exc:
            message = str(exc) if isinstance(exc, AcceptanceError) else type(exc).__name__
            self.failures.append(label)
            self.results[key] = None
            print(f"[FAIL] {label}: {message}")
            return None

    def need(self, key: str) -> Any:
        value = self.results.get(key)
        if value is None:
            raise AcceptanceError(f"prerequisite failed: {key}")
        return value

    def check_api_health(self) -> dict[str, Any]:
        paths = {
            "identity-service": "/api/v1/auth/health",
            "transaction-service": "/api/v1/transactions/health",
            "ai-service": "/api/v1/ai/health",
            "gamification-service": "/api/v1/game/health",
        }
        result = {}
        for expected_service, path in paths.items():
            data = request_json("GET", path).data
            require(data.get("status") == "healthy", f"{expected_service} is not healthy")
            require(data.get("service") == expected_service, f"Kong route mismatch for {expected_service}")
            result[expected_service] = data
        return result

    @staticmethod
    def check_openapi() -> bool:
        catalogs = {
            "/api/v1/auth/openapi.json": {
                ("post", "/customers/otp/request"),
                ("post", "/customers/register"),
                ("post", "/customers/login/otp/request"),
                ("post", "/customers/login"),
                ("post", "/staff/login"),
                ("post", "/tokens/refresh"),
                ("post", "/tokens/logout"),
                ("get", "/me"),
                ("post", "/staff/accounts"),
                ("get", "/audit-logs"),
            },
            "/api/v1/transactions/openapi.json": {
                ("post", "/transactions"),
                ("get", "/transactions/me"),
                ("get", "/transactions/{transaction_id}"),
                ("get", "/cases/assigned-to-me"),
                ("post", "/cases/{case_id}/start"),
                ("post", "/cases/{case_id}/request-verification"),
                ("post", "/cases/{case_id}/customer-response"),
                ("post", "/cases/{case_id}/decision"),
                ("post", "/cases/{case_id}/assign"),
                ("post", "/cases/{case_id}/feedback"),
            },
            "/api/v1/ai/openapi.json": {
                ("post", "/score-and-assign"),
                ("post", "/internal/analysts/sync"),
                ("get", "/health"),
                ("get", "/ready"),
            },
            "/api/v1/game/openapi.json": {
                ("get", "/leaderboard"),
                ("get", "/profiles/me"),
                ("get", "/profiles/{analyst_id}"),
                ("get", "/health"),
                ("get", "/ready"),
            },
        }
        for gateway_path, required in catalogs.items():
            request_id = f"final-openapi-{uuid.uuid4()}"
            request = Request(
                GATEWAY + gateway_path,
                headers={"X-Request-ID": request_id},
                method="GET",
            )
            try:
                with urlopen(request, timeout=10) as response:
                    require(response.status == 200, f"{gateway_path} returned HTTP {response.status}")
                    require(
                        response.headers.get("X-Request-ID") == request_id,
                        f"{gateway_path} did not preserve X-Request-ID",
                    )
                    document = json.loads(response.read())
            except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                raise AcceptanceError(f"{gateway_path} OpenAPI is unavailable") from exc
            available = {
                (method.lower(), path)
                for path, operations in document.get("paths", {}).items()
                for method in operations
                if method.lower() in {"get", "post", "put", "patch", "delete"}
            }
            missing = required - available
            require(not missing, f"{gateway_path} is missing {len(missing)} required operation(s)")
        return True

    @staticmethod
    def check_postgres() -> bool:
        for service in ("identity-db", "transaction-db", "ai-db", "gamification-db"):
            compose(
                "exec",
                "-T",
                service,
                "sh",
                "-lc",
                'pg_isready -q -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
            )
        return True

    @staticmethod
    def check_rabbitmq() -> bool:
        compose("exec", "-T", "rabbitmq", "rabbitmq-diagnostics", "-q", "ping")
        return True

    @staticmethod
    def check_kong() -> bool:
        rows = [json.loads(line) for line in compose("ps", "--format", "json", "kong").splitlines()]
        require(len(rows) == 1, "Kong container is missing")
        require(rows[0].get("State") == "running", "Kong is not running")
        require(rows[0].get("Health") == "healthy", "Kong is not healthy")
        return True

    @staticmethod
    def check_worker(service: str) -> bool:
        running = set(compose("ps", "--status", "running", "--services").splitlines())
        require(service in running, f"{service} is not running")
        return True

    def check_demo_accounts(self) -> dict[str, Any]:
        users = seed_or_check_users(self.values, check=True)
        expected = set(DEMO_EMAILS.values()) | {"customer"}
        require(set(users) == expected, "demo account set is incomplete")
        for account in users.values():
            uuid.UUID(account["id"])
        return users

    def customer_login(self) -> dict[str, Any]:
        request_json(
            "POST",
            "/api/v1/auth/customers/login/otp/request",
            payload={"gsm": self.values["DEMO_CUSTOMER_GSM"]},
        )
        login = request_json(
            "POST",
            "/api/v1/auth/customers/login",
            payload={
                "gsm": self.values["DEMO_CUSTOMER_GSM"],
                "otp_code": self.values["DEMO_OTP_CODE"],
            },
        ).data
        require(login.get("user", {}).get("role") == "CUSTOMER", "customer role is invalid")
        require(bool(login.get("access_token")), "customer access token is missing")
        return login

    def staff_login(self, email: str, password: str, role: str) -> dict[str, Any]:
        login = request_json(
            "POST",
            "/api/v1/auth/staff/login",
            payload={"email": email, "password": password},
        ).data
        require(login.get("user", {}).get("role") == role, f"{role} login returned wrong role")
        require(bool(login.get("access_token")), f"{role} access token is missing")
        return login

    @staticmethod
    def transaction_payload(*, high_risk: bool) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        occurred_at = now.replace(
            hour=(1 if high_risk else 12),
            minute=(30 if high_risk else 0),
            second=0,
            microsecond=0,
        ).isoformat().replace("+00:00", "Z")
        if high_risk:
            return {
                "amount": "48500.00",
                "transaction_type": "TRANSFER",
                "recipient": "Demo Alıcı",
                "source_device": "Yeni iPhone",
                "city": "Berlin",
                "occurred_at": occurred_at,
                "transaction_frequency_24h": 20,
                "is_new_device": True,
                "home_city": "Istanbul",
            }
        return {
            "amount": "250.00",
            "transaction_type": "FATURA",
            "recipient": "Elektrik Faturası",
            "source_device": "Bilinen iPhone",
            "city": "Istanbul",
            "occurred_at": occurred_at,
            "transaction_frequency_24h": 1,
            "is_new_device": False,
            "home_city": "Istanbul",
        }

    def create_transaction(self, *, high_risk: bool) -> dict[str, Any]:
        customer = self.need("customer_login")
        return request_json(
            "POST",
            "/api/v1/transactions/transactions",
            payload=self.transaction_payload(high_risk=high_risk),
            token=customer["access_token"],
            expected_status=201,
        ).data

    def check_high_risk(self) -> dict[str, Any]:
        created = self.need("high_transaction")
        transaction = created.get("transaction") or {}
        case = created.get("case") or {}
        require(created.get("ai_fallback") is False, "high-risk transaction used AI fallback")
        require(transaction.get("ai_status") == "SCORED", "AI status is not SCORED")
        require(transaction.get("risk_level") in {"YUKSEK", "KRITIK"}, "risk is below YUKSEK")
        require(transaction.get("decision") in {"INCELEME", "BLOK"}, "AI decision is not review/block")
        require(case.get("status") == "ATANDI", "risk case is not assigned")
        require(bool(case.get("assigned_analyst_id")), "assigned analyst is missing")
        return created

    def check_ai_result(self) -> dict[str, Any]:
        created = self.need("high_risk")
        result = created.get("ai_result") or {}
        score = float(result.get("risk_score"))
        require(0.0 <= score <= 1.0, "risk_score is outside 0..1")
        require(score >= 0.70, "golden transaction risk_score is below YUKSEK")
        require(result.get("fraud_type") in {
            "CALINTI_KART", "HESAP_ELE_GECIRME", "PARA_AKLAMA", "SUPHELI_DAVRANIS", "TEMIZ"
        }, "fraud_type is outside the catalog")
        require(
            result.get("fraud_type") == "HESAP_ELE_GECIRME",
            "golden transaction fraud_type is not HESAP_ELE_GECIRME",
        )
        require(
            set(result.get("risk_reasons") or [])
            == {
                "Yüksek işlem tutarı",
                "Gece saatinde işlem",
                "Alışılmadık şehir",
                "Yeni cihaz",
                "Yüksek işlem sıklığı",
            },
            "risk_reasons do not match the golden input signals",
        )
        require(bool(result.get("model_version")), "model_version is empty")
        expected_decision = "ONAY" if score < 0.40 else ("INCELEME" if score <= 0.90 else "BLOK")
        expected_level = (
            "DUSUK"
            if score < 0.40
            else ("ORTA" if score < 0.70 else ("YUKSEK" if score <= 0.90 else "KRITIK"))
        )
        require(result.get("decision") == expected_decision, "AI decision threshold mismatch")
        require(result.get("risk_level") == expected_level, "AI risk-level threshold mismatch")
        return result

    def assigned_analyst_login(self) -> dict[str, Any]:
        users = self.need("demo_accounts")
        case = self.need("high_risk")["case"]
        assigned_id = case["assigned_analyst_id"]
        email = DEMO_EMAILS["account"]
        require(
            users[email]["id"] == assigned_id,
            "golden transaction was not assigned to the account-specialist Analyst",
        )
        login = self.staff_login(email, self.values["DEMO_ANALYST_PASSWORD"], "ANALYST")
        login["assigned_analyst_id"] = assigned_id
        return login

    def check_initial_profile(self) -> dict[str, Any]:
        analyst = self.need("analyst_login")
        profile = request_json(
            "GET", "/api/v1/game/profiles/me", token=analyst["access_token"]
        ).data
        require(profile.get("total_points") == 0, "demo analyst points are not reset")
        require(profile.get("resolved_cases") == 0, "demo analyst cases are not reset")
        require(profile.get("badges") == [], "demo analyst badges are not reset")
        return profile

    def transition_case(self) -> dict[str, Any]:
        case_id = self.need("high_risk")["case"]["id"]
        token = self.need("analyst_login")["access_token"]
        started = request_json(
            "POST", f"/api/v1/transactions/cases/{case_id}/start", token=token
        ).data
        require(started.get("status") == "INCELENIYOR", "case did not enter INCELENIYOR")
        require(
            bool(started.get("transaction", {}).get("risk_reasons")),
            "persisted risk_reasons are missing from the Analyst case response",
        )
        invalid = request_json(
            "POST",
            f"/api/v1/transactions/cases/{case_id}/start",
            token=token,
            expected_status=422,
        )
        require(invalid.body.get("error", {}).get("code") == "INVALID_CASE_TRANSITION", "illegal transition error is wrong")
        requested = request_json(
            "POST",
            f"/api/v1/transactions/cases/{case_id}/request-verification",
            token=token,
        ).data
        require(requested.get("status") == "MUSTERI_DOGRULAMA", "verification state is wrong")
        return requested

    def customer_verification(self) -> dict[str, Any]:
        case_id = self.need("high_risk")["case"]["id"]
        token = self.need("customer_login")["access_token"]
        response = request_json(
            "POST",
            f"/api/v1/transactions/cases/{case_id}/customer-response",
            token=token,
            payload={"response": "BEN_YAPMADIM"},
        ).data
        require(response.get("status") == "INCELENIYOR", "case did not return to INCELENIYOR")
        require(response.get("customer_response") == "BEN_YAPMADIM", "customer response was not stored")
        return response

    def block_case(self) -> dict[str, Any]:
        case_id = self.need("high_risk")["case"]["id"]
        token = self.need("analyst_login")["access_token"]
        missing_note = request_json(
            "POST",
            f"/api/v1/transactions/cases/{case_id}/decision",
            token=token,
            payload={"decision": "BLOKLANDI"},
            expected_status=422,
        )
        require(missing_note.body.get("error", {}).get("code") == "DECISION_NOTE_REQUIRED", "missing-note validation is wrong")
        decided = request_json(
            "POST",
            f"/api/v1/transactions/cases/{case_id}/decision",
            token=token,
            payload={
                "decision": "BLOKLANDI",
                "note": "Müşteri işlemi reddetti; hesap güvenliği için işlem bloklandı.",
            },
        ).data
        require(decided.get("status") == "BLOKLANDI", "case was not blocked")
        require(decided.get("event_delivery") == "PENDING", "outbox delivery marker is wrong")
        uuid.UUID(decided["event_id"])
        history = [item.get("to_status") for item in decided.get("history", [])]
        require(
            history == ["YENI", "ATANDI", "INCELENIYOR", "MUSTERI_DOGRULAMA", "INCELENIYOR", "BLOKLANDI"],
            "case history does not match the golden state machine",
        )
        return decided

    def check_outbox(self) -> str:
        event_id = self.need("blocked")["event_id"]

        def published() -> str | None:
            value = db_scalar(
                "transaction-db",
                f"SELECT CASE WHEN published_at IS NULL THEN 'PENDING' ELSE 'PUBLISHED' END FROM outbox_events WHERE event_id = '{event_id}'::uuid",
            )
            return value if value == "PUBLISHED" else None

        return poll(published, "outbox event was not published")

    def check_processed_event(self) -> bool:
        event_id = self.need("blocked")["event_id"]
        return bool(
            poll(
                lambda: db_scalar(
                    "gamification-db",
                    f"SELECT count(*) FROM processed_events WHERE event_id = '{event_id}'::uuid",
                ) == "1",
                "gamification worker did not process the event",
            )
        )

    def check_score_ledger(self) -> dict[str, Any]:
        event_id = self.need("blocked")["event_id"]
        risk_level = self.need("high_risk")["transaction"]["risk_level"]
        expected_points = 45 if risk_level == "KRITIK" else 30
        points = int(db_scalar(
            "gamification-db",
            f"SELECT COALESCE(sum(points), 0) FROM score_ledger WHERE event_id = '{event_id}'::uuid",
        ))
        require(points == expected_points, f"ScoreLedger points are {points}, expected {expected_points}")
        reasons = set(filter(None, db_scalar(
            "gamification-db",
            f"SELECT COALESCE(string_agg(reason, ',' ORDER BY reason), '') FROM score_ledger WHERE event_id = '{event_id}'::uuid",
        ).split(",")))
        expected_reasons = {"CASE_RESOLVED", "FAST_DECISION", "CONFIRMED_FRAUD"}
        if risk_level == "KRITIK":
            expected_reasons.add("CRITICAL_WITHIN_SLA")
        require(reasons == expected_reasons, "ScoreLedger reasons are incorrect")
        return {"points": points, "reasons": sorted(reasons)}

    def check_profile_badge(self) -> dict[str, Any]:
        analyst = self.need("analyst_login")
        expected_points = self.need("score_ledger")["points"]
        profile = poll(
            lambda: request_json(
                "GET", "/api/v1/game/profiles/me", token=analyst["access_token"]
            ).data,
            "analyst profile was not available",
        )
        require(profile.get("total_points") == expected_points, "analyst total_points is incorrect")
        require(profile.get("resolved_cases") == 1, "analyst resolved_cases is incorrect")
        require(profile.get("level") == "BRONZ", "analyst level is incorrect")
        require(profile.get("badges") == ["ILK_YAKALAMA"], "ILK_YAKALAMA badge is missing or duplicated")
        return profile

    def check_leaderboard(self) -> dict[str, Any]:
        supervisor = self.need("supervisor_login")
        analyst_id = self.need("analyst_login")["assigned_analyst_id"]
        expected_points = self.need("score_ledger")["points"]
        data = request_json(
            "GET",
            "/api/v1/game/leaderboard?" + urlencode({"period": "daily", "limit": 10}),
            token=supervisor["access_token"],
        ).data
        row = next((item for item in data.get("items", []) if item.get("analyst_id") == analyst_id), None)
        require(row is not None, "assigned analyst is absent from daily leaderboard")
        require(row.get("period_points") == expected_points, "daily leaderboard points are incorrect")
        require(row.get("badges") == ["ILK_YAKALAMA"], "leaderboard badge is incorrect")
        return data

    def check_supervisor_data(self) -> dict[str, Any]:
        supervisor = self.need("supervisor_login")
        case_id = self.need("high_risk")["case"]["id"]
        data = request_json(
            "GET", "/api/v1/transactions/cases", token=supervisor["access_token"]
        ).data
        item = next((case for case in data.get("items", []) if case.get("id") == case_id), None)
        require(item is not None, "golden case is absent from supervisor data")
        require(item.get("status") == "BLOKLANDI", "supervisor case status is stale")
        require(item.get("transaction", {}).get("risk_level") in {"YUKSEK", "KRITIK"}, "supervisor risk data is wrong")
        require(bool(item.get("transaction", {}).get("risk_reasons")), "supervisor risk_reasons are missing")
        return data

    def check_ai_fallback(self) -> dict[str, Any]:
        compose("stop", "ai-service", timeout=90)
        self.ai_stopped = True
        poll(
            lambda: request_json("GET", "/api/v1/auth/health").data.get("service") == "identity-service",
            "Identity did not remain healthy with AI stopped",
            timeout=15,
        )
        poll(
            lambda: request_json("GET", "/api/v1/transactions/health").data.get("service") == "transaction-service",
            "Transaction did not remain healthy with AI stopped",
            timeout=15,
        )
        poll(
            lambda: request_json("GET", "/api/v1/game/health").data.get("service") == "gamification-service",
            "Gamification did not remain healthy with AI stopped",
            timeout=15,
        )
        created = self.create_transaction(high_risk=False)
        transaction = created.get("transaction") or {}
        case = created.get("case") or {}
        require(created.get("ai_fallback") is True, "AI outage did not activate fallback")
        require(transaction.get("ai_status") == "UNAVAILABLE", "fallback ai_status is wrong")
        require(transaction.get("risk_level") == "BELIRSIZ", "fallback risk_level is wrong")
        require(transaction.get("decision") == "INCELEME", "fallback decision is wrong")
        require(case.get("status") == "YENI", "manual review case was not created")
        return created

    def check_ai_recovery(self) -> dict[str, Any]:
        compose("start", "ai-service", timeout=90)
        poll(
            lambda: request_json("GET", "/api/v1/ai/health").data.get("service") == "ai-service",
            "AI service did not recover",
            timeout=45,
        )
        self.ai_stopped = False
        created = self.create_transaction(high_risk=False)
        require(created.get("ai_fallback") is False, "AI remained in fallback after recovery")
        require(created.get("transaction", {}).get("ai_status") == "SCORED", "recovery transaction was not scored")
        require(bool(created.get("ai_result", {}).get("model_version")), "recovery model_version is missing")
        return created

    def run(self) -> int:
        self.step("api_health", "Four API services healthy", self.check_api_health)
        self.step("openapi", "Required OpenAPI operations available", self.check_openapi)
        self.step("postgres", "Four PostgreSQL databases healthy", self.check_postgres)
        self.step("rabbitmq", "RabbitMQ healthy", self.check_rabbitmq)
        self.step("kong", "Kong healthy and routes isolated", self.check_kong)
        self.step("outbox_worker", "Transaction outbox worker running", lambda: self.check_worker("transaction-outbox-worker"))
        self.step("game_worker", "Gamification worker running", lambda: self.check_worker("gamification-worker"))
        self.step("demo_accounts", "Demo accounts exist with real UUIDs", self.check_demo_accounts)
        self.step("customer_login", "Customer login", self.customer_login)
        self.step(
            "supervisor_login",
            "Supervisor login",
            lambda: self.staff_login(
                DEMO_EMAILS["supervisor"], self.values["DEMO_SUPERVISOR_PASSWORD"], "SUPERVISOR"
            ),
        )
        self.step("high_transaction", "High-risk transaction returns HTTP 201", lambda: self.create_transaction(high_risk=True))
        self.step("high_risk", "RiskCase created at YUKSEK or KRITIK risk", self.check_high_risk)
        self.step("ai_result", "AI score, type, decision, reasons and model version", self.check_ai_result)
        self.step("analyst_login", "Appropriate assigned Analyst login", self.assigned_analyst_login)
        self.step("initial_profile", "Gamification profile starts at zero", self.check_initial_profile)
        self.step("case_transitions", "Case state transitions and illegal transition guard", self.transition_case)
        self.step("verification", "Customer verification BEN_YAPMADIM", self.customer_verification)
        self.step("blocked", "BLOKLANDI decision with required note and outbox event", self.block_case)
        self.step("outbox", "Outbox event published through RabbitMQ", self.check_outbox)
        self.step("processed", "Gamification ProcessedEvent created", self.check_processed_event)
        self.step("score_ledger", "ScoreLedger points and reasons correct", self.check_score_ledger)
        self.step("profile_badge", "Analyst points, level, resolved case and ILK_YAKALAMA", self.check_profile_badge)
        self.step("leaderboard", "Daily leaderboard updated from real ledger data", self.check_leaderboard)
        self.step("supervisor_data", "Supervisor endpoints show the real golden case", self.check_supervisor_data)
        self.step("ai_fallback", "AI outage fallback creates a manual review case with HTTP 201", self.check_ai_fallback)
        self.step("ai_recovery", "AI service recovers and scores a new transaction", self.check_ai_recovery)
        if self.failures:
            return 1
        print("FRAUDCELL FINAL ACCEPTANCE PASSED")
        return 0


def main() -> int:
    acceptance: Acceptance | None = None
    try:
        acceptance = Acceptance()
        return acceptance.run()
    except Exception as exc:
        message = str(exc) if isinstance(exc, AcceptanceError) else type(exc).__name__
        print(f"[FAIL] Final acceptance setup: {message}")
        return 1
    finally:
        if acceptance is not None and acceptance.ai_stopped:
            try:
                compose("start", "ai-service", timeout=90)
            except Exception:
                print("[FAIL] AI safety recovery: ai-service could not be restarted")


if __name__ == "__main__":
    sys.exit(main())
