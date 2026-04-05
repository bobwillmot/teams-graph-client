import os

from teams_graph import TeamsGraphClient


def main() -> None:
    client = TeamsGraphClient(
        team_id=os.environ.get("TEAMS_GRAPH_TEAM_ID", ""),
        channel_id=os.environ.get("TEAMS_GRAPH_CHANNEL_ID", ""),
        access_token=os.environ.get("MS_GRAPH_ACCESS_TOKEN") or None,
        tenant_id=os.environ.get("MS_TENANT_ID") or None,
        client_id=os.environ.get("MS_CLIENT_ID") or None,
    )

    response = client.send_success(
        "Hello from Python via Microsoft Graph.",
        title="Example Message",
    )
    print(f"Posted message id: {response.get('id', 'unknown')}")


if __name__ == "__main__":
    main()