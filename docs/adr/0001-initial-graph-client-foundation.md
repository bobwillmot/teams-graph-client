# ADR 0001: Initial Graph Client Foundation

Status: Accepted

## Context

This project was created as a Microsoft Graph based alternative to an existing Teams webhook client. The goal was to keep the project small and script-friendly while staying aligned with the actual permission and authentication model for normal Teams channel posting.

## Decision

The project will:

- Target Microsoft Graph channel messaging rather than Teams incoming webhooks.
- Use a supplied bearer token or delegated device code authentication instead of app-only client credentials.
- Preserve the webhook project's simple transport and retry structure.
- Accept either plain text helpers or a full Graph `chatMessage` JSON payload from a file or stdin.
- Omit a sample GitHub Actions workflow because delegated interactive auth is a poor fit for unattended CI.

## Consequences

- The client posts through the `/teams/{team-id}/channels/{channel-id}/messages` API and returns the created message document.
- The recommended authentication path is interactive delegated auth such as device code sign-in, or a short-lived access token obtained elsewhere.
- The tool is aimed at local scripts and interactive automation rather than unattended CI posting.
- The client supports both `urllib` and optional `requests`, retries `429` and `5xx` responses, and emits structured CLI logs.
- Callers can choose between a high-level text interface and direct submission of an existing Graph payload.
- The README explicitly points users toward the webhook-based approach when they need a simpler unattended CI integration.