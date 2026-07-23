#!/usr/bin/env python3
"""FraudCell Fault Isolation Automated Test.

Tests fault tolerance by stopping ai-service and verifying:
- Kong AI route returns 502 or 503
- Other microservices remain healthy (200)
- Frontend platform health remains 200 with only ai-service reported as 'unavailable'
- ai-service is safely restarted in a finally block
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"


def fetch_url(url: str, timeout: float = 10.0) -> tuple[int | None, dict | None]:
    """Fetch URL and return (status_code, json_body)."""
    req = urllib.request.Request(url, headers={"User-Agent": "FraudCell-FaultTest/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.getcode()
            body_bytes = response.read()
            json_data = None
            try:
                json_data = json.loads(body_bytes.decode("utf-8"))
            except Exception:
                pass
            return status, json_data
    except urllib.error.HTTPError as exc:
        code = exc.code
        json_data = None
        try:
            body_bytes = exc.read()
            json_data = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            pass
        return code, json_data
    except Exception:
        return 502, None


def run_cmd(cmd: list[str]) -> bool:
    """Run shell command using subprocess."""
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res.returncode == 0


def main() -> int:
    print("=" * 60)
    print("⚡ FraudCell Fault Isolation Test (AI Service Shutdown)")
    print("=" * 60)

    test_passed = True

    try:
        # Step 1: Stop ai-service
        print("\n1. Stopping ai-service via 'docker compose stop ai-service'...")
        if not run_cmd(["docker", "compose", "stop", "ai-service"]):
            print(f"[{RED}FAIL{RESET}] Failed to execute docker compose stop ai-service")
            return 1
        print("   ai-service container stopped.")

        # Step 2: Verify Kong AI route returns 502 or 503 (with short retry loop for TCP tear-down)
        print("\n2. Checking Kong Gateway AI route (expecting 502 or 503)...")
        status = None
        for attempt in range(1, 6):
            status, _ = fetch_url("http://localhost:8000/api/v1/ai/health")
            if status in (502, 503):
                break
            time.sleep(1)

        if status in (502, 503):
            print(f"[{GREEN}PASS{RESET}] Kong Gateway AI route returned HTTP {status}")
        else:
            print(f"[{RED}FAIL{RESET}] Expected HTTP 502 or 503 for AI route, got HTTP {status}")
            test_passed = False

        # Step 3: Verify other routes remain 200
        print("\n3. Checking remaining microservice routes (expecting HTTP 200)...")
        other_routes = [
            ("Identity", "http://localhost:8000/api/v1/auth/health"),
            ("Transaction", "http://localhost:8000/api/v1/transactions/health"),
            ("Gamification", "http://localhost:8000/api/v1/game/health"),
        ]
        for name, url in other_routes:
            res_status = None
            for _ in range(3):
                res_status, _ = fetch_url(url)
                if res_status == 200:
                    break
                time.sleep(1)

            if res_status == 200:
                print(f"[{GREEN}PASS{RESET}] {name:<15} route returned HTTP 200")
            else:
                print(f"[{RED}FAIL{RESET}] {name:<15} route expected 200, got HTTP {res_status}")
                test_passed = False

        # Step 4: Verify Frontend /api/platform-health
        print("\n4. Checking Frontend /api/platform-health (expecting 200 with AI 'unavailable')...")
        status, data = fetch_url("http://localhost:3000/api/platform-health")
        if status == 200 and data and "services" in data:
            services = {s["name"]: s.get("status") for s in data["services"]}
            print(f"   Platform health statuses: {services}")
            if (
                services.get("ai-service") == "unavailable"
                and services.get("identity-service") == "healthy"
                and services.get("transaction-service") == "healthy"
                and services.get("gamification-service") == "healthy"
            ):
                print(f"[{GREEN}PASS{RESET}] Frontend platform-health correctly isolated AI failure")
            else:
                print(f"[{RED}FAIL{RESET}] Unexpected platform-health status dictionary: {services}")
                test_passed = False
        else:
            print(f"[{RED}FAIL{RESET}] Frontend /api/platform-health check failed with HTTP {status}")
            test_passed = False

    finally:
        # ALWAYS restart ai-service regardless of test errors
        print("\n🔄 5. RECOVERY: Restarting ai-service via 'docker compose start ai-service'...")
        run_cmd(["docker", "compose", "start", "ai-service"])

        # Wait for recovery
        recovered = False
        print("   Waiting for AI route to recover to HTTP 200 (max 30s)...")
        for i in range(1, 11):
            time.sleep(3)
            status, _ = fetch_url("http://localhost:8000/api/v1/ai/health")
            if status == 200:
                recovered = True
                print(f"[{GREEN}PASS{RESET}] AI service recovered on attempt {i} -> HTTP 200")
                break
            print(f"   Attempt {i}: HTTP {status}...")

        if not recovered:
            print(f"[{RED}FAIL{RESET}] AI service failed to recover within 30 seconds!")
            test_passed = False

    print("\n" + "=" * 60)
    if test_passed:
        print(f"🎉 {GREEN}FAULT ISOLATION TEST PASSED SUCCESSFULLY!{RESET}")
        print("=" * 60)
        return 0
    print(f"❌ {RED}FAULT ISOLATION TEST FAILED!{RESET}")
    print("=" * 60)
    return 1


if __name__ == "__main__":
    sys.exit(main())
