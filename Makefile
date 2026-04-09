.PHONY: dev build build-ui clean typecheck lint run run-http bump

# Development — starts MCP server + Vite with HMR preview
dev:
	cd ui && npm run dev

# Build — UI + server deps
build: build-ui

build-ui:
	cd ui && npm install && npm run build

# Run server in stdio mode
run:
	uv run python -m synapse_crm.server

# Run server in HTTP mode
run-http:
	uv run uvicorn synapse_crm.server:app --port 8001

# Verify
typecheck:
	uv run ty check src/

lint:
	uv run ruff check src/

clean:
	rm -rf ui/dist ui/node_modules deps/*.egg-info

# Version bump — updates manifest.json, server.json, pyproject.toml, __init__.py
bump:
ifndef VERSION
	$(error VERSION is required. Usage: make bump VERSION=0.2.0)
endif
	@echo "Bumping to $(VERSION)"
	@jq --arg v "$(VERSION)" '.version = $$v' manifest.json > manifest.tmp.json && mv manifest.tmp.json manifest.json
	@jq --arg v "$(VERSION)" '.version = $$v' server.json > server.tmp.json && mv server.tmp.json server.json
	@sed -i '' 's/^version = .*/version = "$(VERSION)"/' pyproject.toml
	@sed -i '' 's/^__version__ = .*/__version__ = "$(VERSION)"/' src/synapse_crm/__init__.py
	@echo "Done. Don't forget to commit and tag."
