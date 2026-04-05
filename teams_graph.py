import argparse
from datetime import datetime, timezone
import html
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable


GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = "https://graph.microsoft.com/ChannelMessage.Send offline_access"


class TeamsGraphError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


class TeamsGraphClient:
    def __init__(
        self,
        team_id: str,
        channel_id: str,
        *,
        access_token: str | None = None,
        tenant_id: str | None = None,
        client_id: str | None = None,
        timeout: float = 10.0,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
        use_requests: bool = False,
        log_handler: Callable[[str, dict[str, Any]], None] | None = None,
        prompt_handler: Callable[[str], None] | None = None,
    ) -> None:
        if not team_id:
            raise ValueError("team_id is required")
        if not channel_id:
            raise ValueError("channel_id is required")
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if backoff_seconds < 0:
            raise ValueError("backoff_seconds must be >= 0")
        if not access_token and not (tenant_id and client_id):
            raise ValueError("either access_token or tenant_id and client_id are required")

        self.team_id = team_id
        self.channel_id = channel_id
        self.access_token = access_token
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.use_requests = use_requests
        self.log_handler = log_handler
        self.prompt_handler = prompt_handler or _default_prompt_handler
        self._cached_access_token: str | None = access_token

    def send_text(
        self,
        text: str,
        *,
        title: str | None = None,
        importance: str = "normal",
    ) -> dict[str, Any]:
        return self.send_payload(_build_chat_message(text, title=title, importance=importance))

    def send_success(self, text: str, *, title: str = "Success") -> dict[str, Any]:
        return self.send_text(text, title=title, importance="normal")

    def send_warning(self, text: str, *, title: str = "Warning") -> dict[str, Any]:
        return self.send_text(text, title=title, importance="high")

    def send_error(self, text: str, *, title: str = "Error") -> dict[str, Any]:
        return self.send_text(text, title=title, importance="high")

    def send_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post_json(payload)

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        attempts = self.max_retries + 1
        last_error: TeamsGraphError | None = None

        for attempt in range(1, attempts + 1):
            self._log(
                "send_attempt",
                attempt=attempt,
                max_attempts=attempts,
                transport=self._transport_name,
            )
            try:
                if self.use_requests:
                    response_body = self._post_json_requests(payload)
                else:
                    response_body = self._post_json_urllib(payload)
                self._log(
                    "send_success",
                    attempt=attempt,
                    max_attempts=attempts,
                    transport=self._transport_name,
                    message_id=response_body.get("id"),
                )
                return response_body
            except TeamsGraphError as exc:
                last_error = exc
                self._log(
                    "send_failure",
                    attempt=attempt,
                    max_attempts=attempts,
                    transport=self._transport_name,
                    status_code=exc.status_code,
                    retryable=exc.retryable,
                    error=str(exc),
                )
                if attempt >= attempts or not exc.retryable:
                    raise
                delay_seconds = exc.retry_after_seconds
                if delay_seconds is None:
                    delay_seconds = self.backoff_seconds * (2 ** (attempt - 1))
                self._log(
                    "retry_scheduled",
                    attempt=attempt,
                    next_attempt=attempt + 1,
                    max_attempts=attempts,
                    delay_seconds=delay_seconds,
                )
                time.sleep(delay_seconds)

        if last_error is not None:
            raise last_error
        raise TeamsGraphError("Microsoft Graph request failed with an unknown error")

    def _post_json_urllib(self, payload: dict[str, Any]) -> dict[str, Any]:
        response_body, _, _ = _json_request_urllib(
            self._messages_url,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._resolve_access_token()}",
                "Content-Type": "application/json",
            },
            data=json.dumps(payload).encode("utf-8"),
            timeout=self.timeout,
        )
        return response_body

    def _post_json_requests(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            import requests
        except ImportError as exc:
            raise TeamsGraphError(
                "requests transport requested but the requests package is not installed",
                retryable=False,
            ) from exc

        try:
            response = requests.post(
                self._messages_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._resolve_access_token()}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise TeamsGraphError(
                f"Microsoft Graph connection failed: {exc}",
                retryable=True,
            ) from exc

        if response.status_code >= 400:
            raise TeamsGraphError(
                f"Microsoft Graph request failed: {response.status_code} {response.text}",
                status_code=response.status_code,
                retryable=_should_retry_status(response.status_code),
                retry_after_seconds=_parse_retry_after(response.headers.get("Retry-After")),
            )

        try:
            return response.json()
        except ValueError as exc:
            raise TeamsGraphError("Microsoft Graph returned invalid JSON") from exc

    def _resolve_access_token(self) -> str:
        if self._cached_access_token:
            return self._cached_access_token

        if not self.tenant_id or not self.client_id:
            raise TeamsGraphError("No access token is available and device code auth is not configured")

        self._cached_access_token = _acquire_device_code_token(
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            timeout=self.timeout,
            log_handler=self.log_handler,
            prompt_handler=self.prompt_handler,
        )
        return self._cached_access_token

    @property
    def _messages_url(self) -> str:
        team_id = urllib.parse.quote(self.team_id, safe="")
        channel_id = urllib.parse.quote(self.channel_id, safe="")
        return f"{GRAPH_BASE_URL}/teams/{team_id}/channels/{channel_id}/messages"

    @property
    def _transport_name(self) -> str:
        return "requests" if self.use_requests else "urllib"

    def _log(self, event: str, **fields: Any) -> None:
        if self.log_handler is None:
            return
        self.log_handler(event, fields)


def _default_prompt_handler(message: str) -> None:
    print(message, file=sys.stderr)


def _build_chat_message(text: str, *, title: str | None = None, importance: str = "normal") -> dict[str, Any]:
    if importance not in {"normal", "high", "urgent"}:
        raise ValueError("importance must be one of: normal, high, urgent")

    parts = []
    if title:
        parts.append(f"<div><strong>{html.escape(title)}</strong></div>")
    parts.append(f"<div>{html.escape(text).replace(chr(10), '<br>')}</div>")

    return {
        "body": {
            "contentType": "html",
            "content": "".join(parts),
        },
        "importance": importance,
    }


def _acquire_device_code_token(
    *,
    tenant_id: str,
    client_id: str,
    timeout: float,
    log_handler: Callable[[str, dict[str, Any]], None] | None,
    prompt_handler: Callable[[str], None],
) -> str:
    device_code_url = f"https://login.microsoftonline.com/{urllib.parse.quote(tenant_id, safe='')}/oauth2/v2.0/devicecode"
    token_url = f"https://login.microsoftonline.com/{urllib.parse.quote(tenant_id, safe='')}/oauth2/v2.0/token"

    device_payload, _, _ = _json_request_urllib(
        device_code_url,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=urllib.parse.urlencode({"client_id": client_id, "scope": GRAPH_SCOPE}).encode("utf-8"),
        timeout=timeout,
    )

    message = str(device_payload.get("message", "Complete sign-in in your browser."))
    if log_handler is not None:
        log_handler(
            "device_code_prompt",
            {
                "verification_uri": device_payload.get("verification_uri"),
                "user_code": device_payload.get("user_code"),
            },
        )
    prompt_handler(message)

    interval = int(device_payload.get("interval", 5))
    expires_at = time.time() + int(device_payload.get("expires_in", 900))
    device_code = str(device_payload["device_code"])

    while time.time() < expires_at:
        time.sleep(interval)
        token_payload, status_code, _ = _json_request_urllib(
            token_url,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=urllib.parse.urlencode(
                {
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "client_id": client_id,
                    "device_code": device_code,
                }
            ).encode("utf-8"),
            timeout=timeout,
            treat_http_error_as_response=True,
        )
        if status_code == 200 and "access_token" in token_payload:
            return str(token_payload["access_token"])

        error_code = token_payload.get("error")
        if error_code == "authorization_pending":
            continue
        if error_code == "slow_down":
            interval += 5
            continue
        if error_code == "authorization_declined":
            raise TeamsGraphError("User declined device code authorization")
        if error_code == "expired_token":
            raise TeamsGraphError("Device code expired before sign-in completed")
        if error_code == "bad_verification_code":
            raise TeamsGraphError("Device code was rejected by Microsoft Entra")
        raise TeamsGraphError(
            f"Device code authentication failed: {token_payload.get('error_description', token_payload)}"
        )

    raise TeamsGraphError("Device code expired before sign-in completed")


def _json_request_urllib(
    url: str,
    *,
    method: str,
    headers: dict[str, str],
    data: bytes | None,
    timeout: float,
    treat_http_error_as_response: bool = False,
) -> tuple[dict[str, Any], int, dict[str, str]]:
    request = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body_text = response.read().decode("utf-8", errors="replace")
            body = json.loads(body_text) if body_text else {}
            return body, response.status, dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(body_text) if body_text else {}
        except json.JSONDecodeError:
            body = {"raw": body_text}

        headers_map = dict(exc.headers.items())
        if treat_http_error_as_response:
            return body, exc.code, headers_map

        raise TeamsGraphError(
            f"Microsoft Graph request failed: {exc.code} {body_text}",
            status_code=exc.code,
            retryable=_should_retry_status(exc.code),
            retry_after_seconds=_parse_retry_after(headers_map.get("Retry-After")),
        ) from exc
    except urllib.error.URLError as exc:
        raise TeamsGraphError(
            f"Microsoft Graph connection failed: {exc}",
            retryable=True,
        ) from exc


def _should_retry_status(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code <= 599


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return max(seconds, 0.0)


def _load_json_payload(path: str) -> dict[str, Any]:
    if path == "-":
        raw = sys.stdin.read()
    else:
        with open(path, encoding="utf-8") as handle:
            raw = handle.read()

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TeamsGraphError(f"Invalid JSON input: {exc}") from exc

    if not isinstance(payload, dict):
        raise TeamsGraphError("JSON payload must be an object at the top level")
    return payload


def _make_cli_logger(log_format: str) -> Callable[[str, dict[str, Any]], None] | None:
    if log_format == "none":
        return None

    if log_format == "json":
        def log_json(event: str, fields: dict[str, Any]) -> None:
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": event,
            }
            record.update(fields)
            json.dump(record, sys.stderr)
            sys.stderr.write("\n")

        return log_json

    def log_text(event: str, fields: dict[str, Any]) -> None:
        pieces = [f"event={event}"]
        for key, value in fields.items():
            pieces.append(f"{key}={json.dumps(value)}")
        print(" ".join(pieces), file=sys.stderr)

    return log_text


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Post messages to a Microsoft Teams channel through Microsoft Graph.")
    parser.add_argument("message", nargs="?", help="Plain text message to send")
    parser.add_argument("--title", help="Optional title rendered above the message body")
    parser.add_argument("--style", choices=["normal", "success", "warning", "error"], default="normal")
    parser.add_argument("--importance", choices=["normal", "high", "urgent"], default="normal")
    parser.add_argument("--payload-file", help="Path to a raw Graph chatMessage JSON payload, or - for stdin")
    parser.add_argument("--team-id", default=os.environ.get("TEAMS_GRAPH_TEAM_ID"), help="Teams team ID")
    parser.add_argument("--channel-id", default=os.environ.get("TEAMS_GRAPH_CHANNEL_ID"), help="Teams channel ID")
    parser.add_argument("--tenant-id", default=os.environ.get("MS_TENANT_ID"), help="Microsoft Entra tenant ID or alias")
    parser.add_argument("--client-id", default=os.environ.get("MS_CLIENT_ID"), help="Public client application ID for device code auth")
    parser.add_argument("--access-token", default=os.environ.get("MS_GRAPH_ACCESS_TOKEN"), help="Microsoft Graph bearer token")
    parser.add_argument("--transport", choices=["urllib", "requests"], default="urllib")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--backoff-seconds", type=float, default=1.0)
    parser.add_argument("--log-format", choices=["text", "json", "none"], default="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.message and not args.payload_file:
        parser.error("either a message or --payload-file is required")

    logger = _make_cli_logger(args.log_format)
    client = TeamsGraphClient(
        team_id=args.team_id or "",
        channel_id=args.channel_id or "",
        access_token=args.access_token or None,
        tenant_id=args.tenant_id or None,
        client_id=args.client_id or None,
        timeout=args.timeout,
        max_retries=args.max_retries,
        backoff_seconds=args.backoff_seconds,
        use_requests=args.transport == "requests",
        log_handler=logger,
    )

    if args.payload_file:
        response = client.send_payload(_load_json_payload(args.payload_file))
    elif args.style == "success":
        response = client.send_success(args.message, title=args.title or "Success")
    elif args.style == "warning":
        response = client.send_warning(args.message, title=args.title or "Warning")
    elif args.style == "error":
        response = client.send_error(args.message, title=args.title or "Error")
    else:
        response = client.send_text(args.message, title=args.title, importance=args.importance)

    json.dump(response, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())