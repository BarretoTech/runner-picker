"""Exercise the reference policy without external network calls."""
import importlib.util
import io
import json
import os
import sys
sys.dont_write_bytecode = True
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("service", "examples/capacity-service/server.py")
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


class PolicyTest(unittest.TestCase):
    def test_paginated_case_insensitive_match(self):
        pages = [dict(total_count=101, runners=[dict(status="offline", busy=False, labels=[])] * 100),
                 dict(total_count=101, runners=[dict(status="online", busy=False, labels=[dict(name="LINUX")])])]
        with patch.dict(os.environ, RUNNER_OWNER="example-org", RUNNER_TOKEN="test"), patch.object(
            service, "urlopen", side_effect=[io.BytesIO(json.dumps(p).encode()) for p in pages]
        ) as request:
            self.assertEqual(service.decide(["linux"], 1, "", "example-org")["choice"], "self-hosted")
            self.assertEqual(request.call_count, 2)

    def test_busy_overflow_and_hosted(self):
        for overflow, expected in [("example-overflow", "overflow"), ("", "hosted")]:
            with patch.dict(os.environ, RUNNER_OWNER="example-org", RUNNER_TOKEN="test"), patch.object(
                service, "urlopen", return_value=io.BytesIO(b'{"total_count":1,"runners":[{"status":"online","busy":true,"labels":[]}]}')
            ):
                self.assertEqual(service.decide(["linux"], 1, overflow, "")["choice"], expected)

    def test_owner_restriction(self):
        with patch.dict(os.environ, RUNNER_OWNER="example-org"):
            with self.assertRaises(ValueError):
                service.decide(["linux"], 1, "", "other-org")


if __name__ == "__main__":
    unittest.main()
