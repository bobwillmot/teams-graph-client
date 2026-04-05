import io
import json
import sys
import tempfile
import unittest
from unittest import mock

from teams_graph import TeamsGraphClient, TeamsGraphError, _load_json_payload, _make_cli_logger


class RecordingClient(TeamsGraphClient):
    def __init__(self) -> None:
        super().__init__(team_id="team-id", channel_id="channel-id", access_token="token")
        self.last_payload = None

    def _post_json(self, payload: dict[str, object]) -> dict[str, object]:
        self.last_payload = payload
        return {"id": "message-id", "body": payload.get("body")}


class RetryingClient(TeamsGraphClient):
    def __init__(self, responses, **kwargs) -> None:
        super().__init__(team_id="team-id", channel_id="channel-id", access_token="token", **kwargs)
        self._responses = list(responses)

    def _post_json_urllib(self, payload: dict[str, object]) -> dict[str, object]:
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class DeviceCodeClient(TeamsGraphClient):
    def __init__(self) -> None:
        super().__init__(team_id="team-id", channel_id="channel-id", tenant_id="organizations", client_id="client-id")
        self.acquire_calls = 0

    def _post_json_urllib(self, payload: dict[str, object]) -> dict[str, object]:
        return {"id": "message-id"}

    def _resolve_access_token(self) -> str:
        self.acquire_calls += 1
        return "device-token"


class TeamsGraphTests(unittest.TestCase):
    def test_send_text_builds_html_payload(self) -> None:
        client = RecordingClient()

        response = client.send_text("Hello from test", title="Greeting")

        self.assertEqual(response["id"], "message-id")
        self.assertIsNotNone(client.last_payload)
        body = client.last_payload["body"]
        self.assertEqual(body["contentType"], "html")
        self.assertIn("Greeting", body["content"])
        self.assertIn("Hello from test", body["content"])

    def test_send_payload_passes_through_unchanged(self) -> None:
        client = RecordingClient()
        payload = {"body": {"contentType": "text", "content": "hello"}}

        client.send_payload(payload)

        self.assertEqual(client.last_payload, payload)

    def test_load_json_payload_reads_file(self) -> None:
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8") as handle:
            json.dump({"body": {"content": "hello"}}, handle)
            handle.flush()

            payload = _load_json_payload(handle.name)

        self.assertEqual(payload, {"body": {"content": "hello"}})

    def test_load_json_payload_reads_stdin(self) -> None:
        with mock.patch.object(sys, "stdin", io.StringIO('{"body": {"content": "hello"}}')):
            payload = _load_json_payload("-")

        self.assertEqual(payload, {"body": {"content": "hello"}})

    def test_load_json_payload_rejects_non_object_json(self) -> None:
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8") as handle:
            json.dump([1, 2, 3], handle)
            handle.flush()

            with self.assertRaisesRegex(RuntimeError, "top level"):
                _load_json_payload(handle.name)

    def test_retryable_failure_retries_and_logs_events(self) -> None:
        events = []
        client = RetryingClient(
            [
                TeamsGraphError("retry me", status_code=429, retryable=True, retry_after_seconds=2.0),
                {"id": "message-id"},
            ],
            max_retries=2,
            backoff_seconds=0.5,
            log_handler=lambda event, fields: events.append((event, fields)),
        )

        with mock.patch("teams_graph.time.sleep") as sleep_mock:
            result = client.send_payload({"body": {"contentType": "text", "content": "hello"}})

        self.assertEqual(result["id"], "message-id")
        sleep_mock.assert_called_once_with(2.0)
        self.assertEqual([event for event, _ in events], [
            "send_attempt",
            "send_failure",
            "retry_scheduled",
            "send_attempt",
            "send_success",
        ])

    def test_non_retryable_failure_does_not_retry(self) -> None:
        client = RetryingClient(
            [TeamsGraphError("bad request", status_code=400, retryable=False)],
            max_retries=2,
            backoff_seconds=0.5,
        )

        with mock.patch("teams_graph.time.sleep") as sleep_mock:
            with self.assertRaisesRegex(RuntimeError, "bad request"):
                client.send_payload({"body": {"contentType": "text", "content": "hello"}})

        sleep_mock.assert_not_called()

    def test_make_cli_logger_json_emits_json_record(self) -> None:
        logger = _make_cli_logger("json")
        stderr = io.StringIO()

        with mock.patch.object(sys, "stderr", stderr):
            logger("send_success", {"attempt": 1, "transport": "urllib"})

        record = json.loads(stderr.getvalue())
        self.assertEqual(record["event"], "send_success")
        self.assertEqual(record["attempt"], 1)
        self.assertEqual(record["transport"], "urllib")

    def test_make_cli_logger_none_returns_none(self) -> None:
        self.assertIsNone(_make_cli_logger("none"))


if __name__ == "__main__":
    unittest.main()