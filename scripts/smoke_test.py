#!/usr/bin/env python3
"""FraudCell Platform Automated Smoke Test.

Uses Python standard library only (no external dependencies).
"""

from __future__ import annotations

import json
import socket
import sys
import urllib.error
import urllib.request

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"


def check_url(url: str, expected_status: int = 200, timeout: float = 5.0) -> tuple[bool, str, int | None, dict | None]:
    """Fetch URL and return (success, message, status_code, json_body)."""
    req = urllib.request.Request(url, headers={"User-Agent": "FraudCell-SmokeTest/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.getcode()
            body_bytes = response.read()
            json_data = None
            if response.headers.get_content_type() == "application/json":
                try:
                    json_data = json.loads(body_bytes.decode("utf-8"))
                except json.JSONDecodeError:
                    pass
            if status == expected_status:
                return True, f"HTTP {status}", status, json_data
            return False, f"Expected HTTP {expected_status}, got HTTP {status}", status, json_data
    except urllib.error.HTTPError as exc:
        json_data = None
        try:
            json_data = json.loads(exc.read().decode("utf-8"))
        except Exception:
            pass
        if exc.code == expected_status:
            return True, f"HTTP {exc.code}", exc.code, json_data
        return False, f"Expected HTTP {expected_status}, got HTTP {exc.code}", exc.code, json_data
    except Exception as exc:
        return False, f"Connection failed: {exc}", None, None


def check_port_unreachable(host: str, port: int, timeout: float = 1.5) -> tuple[bool, str]:
    """Verify that a port is NOT directly accessible on host."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        result = sock.connect_ex((host, port))
        sock.close()
        if result != 0:
            return True, f"Port {port} is closed/unreachable (connect_ex returned {result})"
        return False, f"Port {port} is open! Security violation: backend exposed to host!"
    except Exception as exc:
        return True, f"Port {port} unreachable ({exc})"


def main() -> int:
    print("=" * 60)
    print("🚀 FraudCell Monorepo Smoke Test")
    print("=" * 60)

    all_passed = True

    tests = [
        ("Frontend Main Page", "http://localhost:3000/"),
        ("Frontend Platform Health API", "http://localhost:3000/api/platform-health"),
        ("Kong Gateway -> Identity Health", "http://localhost:8000/api/v1/auth/health"),
        ("Kong Gateway -> Transaction Health", "http://localhost:8000/api/v1/transactions/health"),
        ("Kong Gateway -> AI Health", "http://localhost:8000/api/v1/ai/health"),
        ("Kong Gateway -> Gamification Health", "http://localhost:8000/api/v1/game/health"),
        ("Kong Gateway -> Identity Ready", "http://localhost:8000/api/v1/auth/ready"),
        ("Kong Gateway -> Transaction Ready", "http://localhost:8000/api/v1/transactions/ready"),
        ("Kong Gateway -> AI Ready", "http://localhost:8000/api/v1/ai/ready"),
        ("Kong Gateway -> Gamification Ready", "http://localhost:8000/api/v1/game/ready"),
    ]

    print("\n🔍 1. HTTP Endpoint Checks")
    print("-" * 60)
    for name, url in tests:
        ok, msg, status, _ = check_url(url)
        if ok:
            print(f"[{GREEN}PASS{RESET}] {name:<40} -> {msg}")
        else:
            print(f"[{RED}FAIL{RESET}] {name:<40} -> {msg}")
            all_passed = False

    print("\n📊 2. Platform Health Payload Integrity Check")
    print("-" * 60)
    ok, msg, status, data = check_url("http://localhost:3000/api/platform-health")
    if ok and data and "services" in data:
        services = data.get("services", [])
        if len(services) == 4:
            unhealthy = [s["name"] for s in services if s.get("status") != "healthy"]
            if not unhealthy:
                print(f"[{GREEN}PASS{RESET}] All 4 services reported 'healthy' in platform-health")
            else:
                print(f"[{RED}FAIL{RESET}] Unhealthy services found in platform-health: {unhealthy}")
                all_passed = False
        else:
            print(f"[{RED}FAIL{RESET}] Expected 4 services in platform-health, got {len(services)}")
            all_passed = False
    else:
        print(f"[{RED}FAIL{RESET}] Failed to retrieve valid JSON from platform-health: {msg}")
        all_passed = False

    print("\n🔒 3. Direct Port Isolation Check (Ports 8001-8004 must NOT be published)")
    print("-" * 60)
    for port in (8001, 8002, 8003, 8004):
        ok, msg = check_port_unreachable("127.0.0.1", port)
        if ok:
            print(f"[{GREEN}PASS{RESET}] Direct port {port} isolation -> {msg}")
        else:
            print(f"[{RED}FAIL{RESET}] Direct port {port} isolation -> {msg}")
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print(f"🎉 {GREEN}ALL SMOKE TESTS PASSED SUCCESSFULLY!{RESET}")
        print("=" * 60)
        return 0
    print(f"❌ {RED}SOME SMOKE TESTS FAILED!{RESET}")
    print("=" * 60)
    return 1


if __name__ == "__main__":
    sys.exit(main())
