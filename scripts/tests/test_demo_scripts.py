import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import demo_prepare
import demo_reset


class DemoScriptTests(unittest.TestCase):
    def test_reset_requires_exact_confirmation_without_side_effects(self):
        with patch.object(demo_reset, "lookup_users") as lookup:
            self.assertEqual(demo_reset.main([]), 1)
            lookup.assert_not_called()

    def test_reset_is_safe_before_demo_users_exist(self):
        with (
            patch.object(demo_reset, "lookup_users", return_value={}),
            patch.object(demo_reset, "compose_exec") as execute,
        ):
            self.assertEqual(demo_reset.main(["--confirm", "RESET_DEMO"]), 0)
            execute.assert_not_called()

    def test_prepare_can_run_twice_without_exposing_tokens(self):
        values = {
            "DEMO_ADMIN_PASSWORD": "hidden-admin",
            "DEMO_SUPERVISOR_PASSWORD": "hidden-supervisor",
            "DEMO_ANALYST_PASSWORD": "hidden-analyst",
            "DEMO_CUSTOMER_GSM": "05550000001",
            "DEMO_OTP_CODE": "1234",
            "INTERNAL_SERVICE_KEY": "hidden-key",
        }
        users = {
            "demo.admin@fraudcell.com": {"id": "1", "role": "ADMIN"},
            "demo.supervisor@fraudcell.com": {"id": "2", "role": "SUPERVISOR"},
            "demo.analyst.card@fraudcell.com": {"id": "3", "role": "ANALYST"},
            "demo.analyst.account@fraudcell.com": {"id": "4", "role": "ANALYST"},
            "demo.analyst.aml@fraudcell.com": {"id": "5", "role": "ANALYST"},
            "customer": {"id": "6", "role": "CUSTOMER", "gsm": "+905550000001"},
        }
        token_response = {"access_token": "never-print", "refresh_token": "never-print"}
        with (
            patch.object(demo_prepare, "required_environment", return_value=values),
            patch.object(demo_prepare, "check_health"),
            patch.object(demo_prepare, "seed_or_check_users", return_value=users),
            patch.object(demo_prepare, "compose_exec"),
            patch.object(demo_prepare, "customer_login", return_value=token_response),
            patch.object(demo_prepare, "staff_login", return_value=token_response),
            patch("builtins.print") as output,
        ):
            self.assertEqual(demo_prepare.main(), 0)
            self.assertEqual(demo_prepare.main(), 0)
            rendered = " ".join(" ".join(map(str, call.args)) for call in output.call_args_list)
            self.assertNotIn("never-print", rendered)
            self.assertIn("DEMO READY", rendered)


if __name__ == "__main__":
    unittest.main()
