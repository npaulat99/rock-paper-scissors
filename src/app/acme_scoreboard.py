"""Public HTTPS scoreboard served with Let's Encrypt (WebPKI) certificates.

This runs a **separate** HTTPS server alongside the mTLS game server.
- The game server on port 9002 uses SPIFFE mTLS (client certificates required).
- This scoreboard server on port 443 uses a Let's Encrypt cert (server-only TLS,
  no client auth) so anyone with a browser can view the scores.

This demonstrates the difference between WebPKI (ACME) and SPIFFE trust models.
"""

from __future__ import annotations

import json
import ssl
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scoreboard import ScoreBoard


def start_acme_scoreboard(
    *,
    host: str,
    port: int,
    scoreboard: ScoreBoard,
    server_spiffe_id: str,
    cert_path: str,
    key_path: str,
) -> threading.Thread:
    """Start the public HTTPS scoreboard in a daemon thread.

    Args:
        host: Bind address (e.g. "0.0.0.0")
        port: Bind port (e.g. 443)
        scoreboard: Shared ScoreBoard instance (same one used by the game)
        server_spiffe_id: This server's SPIFFE ID (shown in response)
        cert_path: Path to Let's Encrypt fullchain.pem
        key_path: Path to Let's Encrypt privkey.pem

    Returns:
        The daemon thread running the server.
    """

    class AcmeHandler(BaseHTTPRequestHandler):
        server_version = "rps-scoreboard/0.1"

        def do_GET(self) -> None:  # noqa: N802
            if self.path in ("/", "/v1/rps/scores"):
                self._serve_scores()
            elif self.path == "/healthz":
                self._json_ok({"status": "ok"})
            else:
                self._json_error(HTTPStatus.NOT_FOUND, "not_found", "unknown path")

        def _serve_scores(self) -> None:
            scores_data = {
                "server_spiffe_id": server_spiffe_id,
                "transport": "WebPKI (Let's Encrypt / ACME)",
                "opponents": [],
            }
            for peer_id in sorted(scoreboard._scores.keys()):
                score = scoreboard._scores[peer_id]
                scores_data["opponents"].append({
                    "spiffe_id": peer_id,
                    "wins": score.wins,
                    "losses": score.losses,
                })
            self._json_ok(scores_data)

        def _json_ok(self, payload: dict) -> None:
            data = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)

        def _json_error(self, status: HTTPStatus, code: str, msg: str) -> None:
            data = json.dumps({"error": code, "message": msg}).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt: str, *args) -> None:
            pass  # suppress request logs for the public scoreboard

    # Standard WebPKI TLS context — server-only, no client auth
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_path, key_path)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2

    httpd = ThreadingHTTPServer((host, port), AcmeHandler)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)

    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    print(f"  ACME scoreboard: https://{host}:{port}/v1/rps/scores  (WebPKI)")
    return t
