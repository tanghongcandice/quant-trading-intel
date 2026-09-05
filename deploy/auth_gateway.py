#!/usr/bin/env python3
"""Small authenticated reverse proxy for the private Hong dashboard."""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import http.client
import json
import os
import secrets
import subprocess
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


DEFAULT_CREDENTIALS = Path("/Users/mac/.config/hong-dashboard/auth.json")
HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}
FAIL_WINDOW_SECONDS = 5 * 60
BLOCK_SECONDS = 10 * 60
MAX_FAILURES = 8


def password_digest(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), 310_000
    ).hex()


def initialize_credentials(path: Path, username: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise SystemExit(f"Credentials already exist: {path}")

    password = secrets.token_urlsafe(24)
    salt = secrets.token_hex(16)
    payload = {
        "username": username,
        "salt": salt,
        "password_hash": password_digest(password, salt),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    subprocess.run(["/usr/bin/pbcopy"], input=password, text=True, check=True)
    print(f"Created credentials for {username}; password copied to the macOS clipboard.")


def set_credentials(path: Path, username: str) -> None:
    password = getpass.getpass("新密码（至少 12 个字符）: ")
    confirmation = getpass.getpass("再次输入新密码: ")
    if password != confirmation:
        raise SystemExit("两次输入的密码不一致，未修改。")
    if len(password) < 12:
        raise SystemExit("密码至少需要 12 个字符，未修改。")

    salt = secrets.token_hex(16)
    payload = {
        "username": username,
        "salt": salt,
        "password_hash": password_digest(password, salt),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.chmod(0o600)
    temporary.replace(path)
    print(f"已更新账号 {username} 的密码。")


class AuthState:
    def __init__(self, credential_path: Path) -> None:
        data = json.loads(credential_path.read_text(encoding="utf-8"))
        self.username = str(data["username"])
        self.salt = str(data["salt"])
        self.password_hash = str(data["password_hash"])
        self.failures: dict[str, deque[float]] = defaultdict(deque)
        self.blocked_until: dict[str, float] = {}
        self.lock = threading.Lock()

    def is_blocked(self, ip: str) -> bool:
        now = time.monotonic()
        with self.lock:
            until = self.blocked_until.get(ip, 0)
            if until <= now:
                self.blocked_until.pop(ip, None)
                return False
            return True

    def record_failure(self, ip: str) -> None:
        now = time.monotonic()
        with self.lock:
            attempts = self.failures[ip]
            while attempts and attempts[0] < now - FAIL_WINDOW_SECONDS:
                attempts.popleft()
            attempts.append(now)
            if len(attempts) >= MAX_FAILURES:
                self.blocked_until[ip] = now + BLOCK_SECONDS
                attempts.clear()

    def verify(self, authorization: str | None) -> bool:
        if not authorization or not authorization.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(authorization[6:], validate=True).decode("utf-8")
            username, password = decoded.split(":", 1)
        except (ValueError, UnicodeDecodeError):
            return False
        supplied_hash = password_digest(password, self.salt)
        return hmac.compare_digest(username, self.username) and hmac.compare_digest(
            supplied_hash, self.password_hash
        )


class GatewayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    auth_state: AuthState

    def client_ip(self) -> str:
        return self.headers.get("CF-Connecting-IP", self.client_address[0]).strip()

    def authenticate(self) -> bool:
        ip = self.client_ip()
        if self.auth_state.is_blocked(ip):
            body = b"Too many failed login attempts. Try again later.\n"
            self.send_response(429)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Retry-After", str(BLOCK_SECONDS))
            self.end_headers()
            self.wfile.write(body)
            return False

        if self.auth_state.verify(self.headers.get("Authorization")):
            return True

        self.auth_state.record_failure(ip)
        body = b"Authentication required.\n"
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Hong dashboard", charset="UTF-8"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        return False

    def proxy(self) -> None:
        if not self.authenticate():
            return

        target_port = 8000 if self.path.startswith(("/api", "/media")) else 8001
        request_headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP and key.lower() != "authorization"
        }
        request_headers["Host"] = f"127.0.0.1:{target_port}"

        connection = http.client.HTTPConnection("127.0.0.1", target_port, timeout=60)
        try:
            connection.request(self.command, self.path, headers=request_headers)
            response = connection.getresponse()
            body = response.read()
            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                if key.lower() not in HOP_BY_HOP and key.lower() != "content-length":
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "private, no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        except (OSError, http.client.HTTPException):
            body = b"Dashboard upstream is unavailable.\n"
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        finally:
            connection.close()

    do_GET = proxy
    do_HEAD = proxy
    do_OPTIONS = proxy

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials", type=Path, default=DEFAULT_CREDENTIALS)
    parser.add_argument("--init-credentials", action="store_true")
    parser.add_argument("--set-password", action="store_true")
    parser.add_argument("--username", default="hong")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8002)
    args = parser.parse_args()

    if args.init_credentials:
        initialize_credentials(args.credentials, args.username)
        return
    if args.set_password:
        set_credentials(args.credentials, args.username)
        return

    GatewayHandler.auth_state = AuthState(args.credentials)
    server = ThreadingHTTPServer((args.host, args.port), GatewayHandler)
    server.daemon_threads = True
    print(f"Hong dashboard auth gateway listening on {args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
