"""Real Apprise delivery to a loopback receiver; no external notifications."""

import json
import threading
import unittest
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from monopolygo_rewards.config import Settings
from monopolygo_rewards.models import RunResult
from monopolygo_rewards.notifications import build_notification, send_bounded


class AppriseDeliveryTests(unittest.TestCase):
    def test_real_json_delivery_and_rejected_delivery(self):
        received = []
        status = [200]

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(status[0])
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            s = Settings(
                "WonderfulFinch83",
                apprise_url=f"json://127.0.0.1:{server.server_port}/notice",
                apprise_timeout=timedelta(seconds=10),
            )
            message = build_notification(
                s, RunResult((), "blocked", datetime(2026, 11, 10, tzinfo=UTC), "Session rejected")
            )
            self.assertTrue(send_bounded(s, message))
            self.assertEqual(received[0]["type"], "failure")
            self.assertIn("Session rejected", received[0]["message"])
            status[0] = 500
            self.assertFalse(send_bounded(s, message))
            self.assertEqual(len(received), 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
