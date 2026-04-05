# Teams Graph Client

Small Python client for posting messages to a Microsoft Teams channel through Microsoft Graph.

Features:

- Reusable Python class.
- Command-line interface.
- Optional `requests` transport.
- Retry with exponential backoff for `429` and `5xx` responses.
- Installable `teams-graph-post` console command.
- Rich JSON payload input from a file or stdin.
- Structured text or JSON logs for CI and automation.
- Delegated authentication through a supplied access token or interactive device code sign-in.

## Important Difference From Webhooks

This project uses Microsoft Graph, not Teams incoming webhooks.

- Normal channel message creation through Graph requires delegated permission such as `ChannelMessage.Send`.
- App-only client credentials are not supported for ordinary channel posting; Microsoft documents application permission support only for migration scenarios.
- This means the easiest supported auth path for a local script is delegated device code sign-in, or supplying a short-lived access token obtained elsewhere.
- If you need unattended CI posting, the webhook-based project is usually the simpler fit.

## Files

- `.env.example`: example Graph environment file.
- `.env`: local Graph environment file created with placeholder values.
- `.gitignore`: local environment and build artifact ignore rules.
- `Makefile`: common setup and run targets.
- `payload.json`: sample Graph `chatMessage` payload.
- `tests/test_teams_graph.py`: smoke tests for payload generation and JSON loading.
- `teams_graph.py`: reusable client class and CLI.
- `example.py`: simple example usage.
- `pyproject.toml`: packaging metadata and `teams-graph-post` entry point.
- `chat-transcript.md`: saved project conversation summary.
- `design-decisions.md`: saved implementation decisions and tradeoffs.

## Make Targets

Common commands:

```bash
make install
make install-requests
make example
make doctor
make test
make post MESSAGE="Hello from make"
make post-json
```

The `post` and `post-json` targets load these variables from `.env` if present, otherwise they use the current shell environment:

- `TEAMS_GRAPH_TEAM_ID`
- `TEAMS_GRAPH_CHANNEL_ID`
- `MS_TENANT_ID`
- `MS_CLIENT_ID`
- `MS_GRAPH_ACCESS_TOKEN`

Run `make doctor` to verify that `.venv`, `teams-graph-post`, `payload.json`, team/channel IDs, and authentication settings are all available before posting.

Create a local `.env` from the example:

```bash
cp .env.example .env
```

This folder already includes a local `.env` placeholder. Replace the placeholder values with your real tenant, app, team, and channel settings before posting.

## Setup

Register a Microsoft Entra application for delegated device code auth:

1. Create an app registration.
2. Enable public client flows for the app.
3. Add Microsoft Graph delegated permission `ChannelMessage.Send`.
4. Grant or consent to the permission in your tenant as required.
5. Copy the app's client ID into `MS_CLIENT_ID`.

You also need the target Teams team ID and channel ID.

## Usage

Set the channel and auth settings, then run the example:

```bash
export TEAMS_GRAPH_TEAM_ID="your-team-id"
export TEAMS_GRAPH_CHANNEL_ID="your-channel-id"
export MS_TENANT_ID="organizations"
export MS_CLIENT_ID="your-public-client-id"
python example.py
```

If `MS_GRAPH_ACCESS_TOKEN` is not set, the client starts a device code flow and asks you to sign in in a browser.

Use the built-in CLI:

```bash
teams-graph-post "Hello from CLI"
teams-graph-post "Deploy finished" --style success --title "Production Deploy"
teams-graph-post "Heads up" --style warning
```

Install the package locally and use the console command:

```bash
python -m pip install -e .
teams-graph-post "Hello from installed CLI"
```

Use the optional `requests` transport:

```bash
python -m pip install requests
teams-graph-post "Hello from CLI" --transport requests
```

Or install the optional dependency through the package metadata:

```bash
python -m pip install -e '.[requests]'
teams-graph-post "Hello from requests transport" --transport requests
```

Send a full Graph chatMessage payload from a JSON file:

```bash
teams-graph-post --payload-file payload.json
make post-json
```

Send JSON from stdin:

```bash
cat payload.json | teams-graph-post --payload-file -
```

Emit JSON logs for automation:

```bash
teams-graph-post "Deploy finished" --log-format json
```

Import the client in your own code:

```python
from teams_graph import TeamsGraphClient

client = TeamsGraphClient(
    team_id="your-team-id",
    channel_id="your-channel-id",
    tenant_id="organizations",
    client_id="your-public-client-id",
)

client.send_text("Hello from Python")
```

Provide your own bearer token when you already have one:

```python
from teams_graph import TeamsGraphClient

client = TeamsGraphClient(
    team_id="your-team-id",
    channel_id="your-channel-id",
    access_token="your-access-token",
)

client.send_success("Deploy succeeded", title="Production Deploy")
```

Retry behavior:

- Retries happen for `429` and `5xx` responses.
- Delay uses `Retry-After` when Graph provides it.
- Otherwise delay uses exponential backoff: `backoff_seconds * 2^(attempt - 1)`.
- Transport errors are retried as transient failures.

Structured logging:

- CLI logs are written to stderr.
- `--log-format text` prints readable key/value lines.
- `--log-format json` prints one JSON object per event for automation parsing.
- `--log-format none` suppresses CLI logs.

Smoke tests:

- Run `make test` to verify the client builds payloads and loads JSON input correctly.

Note: unlike the webhook variant, this project does not include a sample GitHub Actions workflow because normal Graph channel posting depends on delegated user auth, which is a poor fit for unattended CI.