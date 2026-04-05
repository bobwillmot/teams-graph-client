PYTHON := .venv/bin/python
PIP := $(PYTHON) -m pip
TEAMS_GRAPH_POST := .venv/bin/teams-graph-post
PAYLOAD_FILE ?= payload.json

ifneq ($(wildcard .env),)
include .env
endif

export MS_TENANT_ID
export MS_CLIENT_ID
export MS_GRAPH_ACCESS_TOKEN
export TEAMS_GRAPH_TEAM_ID
export TEAMS_GRAPH_CHANNEL_ID

.PHONY: help venv install install-requests example post post-json doctor test freeze clean

help:
	@echo "Available targets:"
	@echo "  make venv              Create .venv using the project-selected Python"
	@echo "  make install           Install the project in editable mode into .venv"
	@echo "  make install-requests  Install the project with optional requests support"
	@echo "  make example           Run example.py using .venv"
	@echo "  make post MESSAGE=...  Send a text message to a Teams channel"
	@echo "  make post-json         Send a raw Graph chatMessage payload file"
	@echo "  make doctor            Verify local environment and Graph configuration"
	@echo "  make test              Run smoke tests"
	@echo "  make freeze            Show installed package versions in .venv"
	@echo "  make clean             Remove build artifacts"
	@echo ""
	@echo "Optional .env support: set MS_TENANT_ID, MS_CLIENT_ID, TEAMS_GRAPH_TEAM_ID,"
	@echo "TEAMS_GRAPH_CHANNEL_ID, and optionally MS_GRAPH_ACCESS_TOKEN in .env or your shell"

venv:
	python3 -m venv .venv

install: venv
	$(PIP) install -e .

install-requests: venv
	$(PIP) install -e '.[requests]'

example:
	$(PYTHON) example.py

post:
	@if [ -z "$(MESSAGE)" ]; then echo "Usage: make post MESSAGE='Hello from make'"; exit 1; fi
	@if [ -z "$(TEAMS_GRAPH_TEAM_ID)" ] || [ -z "$(TEAMS_GRAPH_CHANNEL_ID)" ]; then echo "TEAMS_GRAPH_TEAM_ID and TEAMS_GRAPH_CHANNEL_ID must be set."; exit 1; fi
	@if [ -z "$(MS_GRAPH_ACCESS_TOKEN)" ] && ( [ -z "$(MS_TENANT_ID)" ] || [ -z "$(MS_CLIENT_ID)" ] ); then echo "Set MS_GRAPH_ACCESS_TOKEN or both MS_TENANT_ID and MS_CLIENT_ID."; exit 1; fi
	$(TEAMS_GRAPH_POST) "$(MESSAGE)"

post-json:
	@if [ -z "$(TEAMS_GRAPH_TEAM_ID)" ] || [ -z "$(TEAMS_GRAPH_CHANNEL_ID)" ]; then echo "TEAMS_GRAPH_TEAM_ID and TEAMS_GRAPH_CHANNEL_ID must be set."; exit 1; fi
	@if [ -z "$(MS_GRAPH_ACCESS_TOKEN)" ] && ( [ -z "$(MS_TENANT_ID)" ] || [ -z "$(MS_CLIENT_ID)" ] ); then echo "Set MS_GRAPH_ACCESS_TOKEN or both MS_TENANT_ID and MS_CLIENT_ID."; exit 1; fi
	$(TEAMS_GRAPH_POST) --payload-file "$(FILE)$(if $(FILE),,$(PAYLOAD_FILE))"

doctor:
	@if [ ! -x "$(PYTHON)" ]; then echo "Missing virtual environment Python at $(PYTHON). Run 'make install' first."; exit 1; fi
	@if [ ! -x "$(TEAMS_GRAPH_POST)" ]; then echo "Missing teams-graph-post at $(TEAMS_GRAPH_POST). Run 'make install' first."; exit 1; fi
	@if [ ! -f "$(PAYLOAD_FILE)" ]; then echo "Missing sample payload file: $(PAYLOAD_FILE)"; exit 1; fi
	@if [ -z "$(TEAMS_GRAPH_TEAM_ID)" ]; then echo "TEAMS_GRAPH_TEAM_ID is not set."; exit 1; fi
	@if [ -z "$(TEAMS_GRAPH_CHANNEL_ID)" ]; then echo "TEAMS_GRAPH_CHANNEL_ID is not set."; exit 1; fi
	@if [ -z "$(MS_GRAPH_ACCESS_TOKEN)" ] && [ -z "$(MS_TENANT_ID)" ]; then echo "MS_TENANT_ID is not set."; exit 1; fi
	@if [ -z "$(MS_GRAPH_ACCESS_TOKEN)" ] && [ -z "$(MS_CLIENT_ID)" ]; then echo "MS_CLIENT_ID is not set."; exit 1; fi
	@echo "Python: $$($(PYTHON) --version)"
	@echo "teams-graph-post: $$($(TEAMS_GRAPH_POST) --help >/dev/null 2>&1 && echo ok || echo failed)"
	@echo "payload.json: ok"
	@echo "TEAMS_GRAPH_TEAM_ID: configured"
	@echo "TEAMS_GRAPH_CHANNEL_ID: configured"
	@if [ -n "$(MS_GRAPH_ACCESS_TOKEN)" ]; then echo "Auth: access token configured"; else echo "Auth: device code configured"; fi

test:
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py' -v

freeze:
	$(PIP) freeze

clean:
	rm -rf build dist *.egg-info .pytest_cache .coverage