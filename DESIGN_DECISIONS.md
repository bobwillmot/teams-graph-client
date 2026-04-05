# Design Decisions

Date: 2026-04-05

## Summary

This file records the main implementation decisions for the Microsoft Graph based Teams client.

## Decision 1

The project targets Microsoft Graph channel messaging rather than Teams incoming webhooks.

Reason: the user asked for the Graph-based alternative to the existing webhook project.

Consequence: the project uses the `/teams/{team-id}/channels/{channel-id}/messages` API and returns the created message document rather than the minimal webhook response body.

## Decision 2

Authentication uses a supplied bearer token or interactive device code flow.

Reason: ordinary channel posting with Microsoft Graph requires delegated permission such as `ChannelMessage.Send`. Microsoft documents app-only application permission support only for migration scenarios, so client credentials would be a misleading default for this tool.

Consequence: the project is suitable for local scripts and interactive automation, but it is not aimed at unattended CI posting.

## Decision 3

The client retains the webhook project's transport and retry structure.

Reason: the existing project shape is simple, testable, and already fits the user's requested "similar to this" constraint.

Consequence: the Graph client supports both `urllib` and optional `requests`, retries `429` and `5xx` responses, and emits structured CLI logs.

## Decision 4

The CLI accepts raw Graph `chatMessage` JSON payloads from a file or stdin in addition to simple text input.

Reason: some callers want a high-level helper for plain text, while others already have a Graph payload they want to send directly.

Consequence: the project supports both scripting styles without requiring a separate utility.

## Decision 5

No sample GitHub Actions workflow is included.

Reason: delegated device code auth is not a good match for unattended CI, and a sample workflow would suggest a deployment pattern that is usually the wrong choice for this API.

Consequence: the README explicitly notes that the webhook-based project is usually the simpler CI option.