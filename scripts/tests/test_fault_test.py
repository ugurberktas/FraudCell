from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import URLError


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import fault_test


class FaultScriptTests(unittest.TestCase):
    def test_gateway_timeout_and_server_errors_count_as_unavailable(self):
        self.assertTrue(fault_test.endpoint_is_unavailable(None))
        self.assertTrue(fault_test.endpoint_is_unavailable(502))
        self.assertTrue(fault_test.endpoint_is_unavailable(504))
        self.assertFalse(fault_test.endpoint_is_unavailable(200))

    def test_safety_recovery_attempts_every_stopped_service(self):
        runner = object.__new__(fault_test.FaultRecoveryTest)
        runner.stopped_services = {"rabbitmq", "gamification-worker", "ai-service"}
        calls: list[tuple[str, ...]] = []

        def fake_compose(*arguments, **_kwargs):
            calls.append(arguments)
            if arguments == ("start", "gamification-worker"):
                raise fault_test.FaultTestError("safe failure")
            return ""

        with (
            patch.object(fault_test, "compose", side_effect=fake_compose),
            patch("builtins.print"),
        ):
            self.assertFalse(runner.recover_stopped_services())

        self.assertEqual(
            calls,
            [
                ("start", "rabbitmq"),
                ("start", "gamification-worker"),
                ("start", "ai-service"),
            ],
        )
        self.assertEqual(runner.stopped_services, {"gamification-worker"})

    def test_request_failure_does_not_expose_token_password_or_otp(self):
        secrets = ("secret-token", "secret-password", "1234")
        with patch.object(
            fault_test,
            "urlopen",
            side_effect=URLError("secret-token secret-password 1234"),
        ):
            with self.assertRaises(fault_test.FaultTestError) as caught:
                fault_test.request_json(
                    "POST",
                    "/safe-path",
                    payload={"password": secrets[1], "otp_code": secrets[2]},
                    token=secrets[0],
                )

        rendered = str(caught.exception)
        for secret in secrets:
            self.assertNotIn(secret, rendered)

    def test_duplicate_delivery_proof_only_resets_one_validated_event(self):
        event_id = "76f950ea-5269-45c6-a4f0-e07b3727df0f"
        with patch.object(fault_test, "db_scalar", return_value="1") as execute:
            fault_test.reset_outbox_for_republish(event_id)

        service, statement = execute.call_args.args
        self.assertEqual(service, "transaction-db")
        self.assertIn(event_id, statement)
        self.assertIn("SET published_at = NULL", statement)


if __name__ == "__main__":
    unittest.main()
