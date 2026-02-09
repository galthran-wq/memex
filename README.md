# Memex

![Memex Architecture](docs/memex-architecture.png)

Personal knowledge base as a GitHub template. An MCP server gives AI agents tools to search, read, and add knowledge. Writes go through [Cursor Cloud Agents](https://cursor.com/docs/cloud-agent) — a cloud agent reads your `.cursor/rules/`, creates properly formatted entries with cross-references, and opens a PR for you to review.

## How It Works

```
You: "add what we discussed about transformers to my knowledge base"
  ↓
Your AI agent summarizes the discussion
  ↓
Calls kb_add(summary) via MCP
  ↓
Cursor Cloud Agent spawns, reads .cursor/rules/,
creates atomic entries with typed edges, opens a PR
  ↓
You review and merge
```

**Read path**: MCP server reads from local disk — fast, no API calls.
**Write path**: Cloud agent handles formatting, cross-references, and PRs.

## Quick Start

1. Click **Use this template** on GitHub
2. Clone your new repo locally
3. Configure:

```bash
cp .env.example .env
# Edit .env — set CURSOR_API_KEY
# Edit config.yaml — set github.owner and github.repo
```

4. Run the server:

```bash
uv run memex
```

5. Add to Cursor MCP config (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "memex": {
      "url": "http://localhost:8787/mcp"
    }
  }
}
```

Done. Your AI agent now has access to `kb_search`, `kb_list`, `kb_read`, `kb_add`, and `kb_status` tools.

## Knowledge Model

Flat knowledge graph: every entry is `knowledge/{slug}.md`.

```yaml
---
title: "RLHF"
type: concept                    # concept | reference | insight | question | note
summary: "Fine-tuning LLMs using human preference feedback"
tags: [ml, alignment]
created: "2026-02-09"
edges:
  - path: /knowledge/reward-model.md
    label: uses
    description: "Reward model scores outputs for training signal"
sources:
  - url: "https://arxiv.org/abs/2203.02155"
---
```

- **Typed edges** in frontmatter — the graph's source of truth
- **Markdown links** in body — for readability, clickable on GitHub
- **Backlinks** computed dynamically by the server
- **Body templates** per type (concept → Definition/How It Works/Connections, etc.)

## MCP Tools

| Tool | Description |
|------|-------------|
| `kb_search(query)` | Fulltext search across entries |
| `kb_list(type?, tag?)` | List entries with optional filters |
| `kb_read(path)` | Read entry with edges and backlinks |
| `kb_add(summary)` | Launch cloud agent to add knowledge via PR |
| `kb_status(agent_id)` | Check cloud agent status and PR URL |

## Viewer (GitHub Pages)

A static site with entry list, filters, and interactive graph visualization.

Deploy automatically when a PR is merged into `master` that changes `knowledge/**` (also redeploys on `viewer/**` changes).

Manual deploy: go to Actions → **Deploy Knowledge Base Viewer** → Run workflow.

The viewer reads `knowledge/*.md`, builds a `data.json`, and deploys a single-page app with vis.js graph.

## Running with Docker

```bash
docker compose up
```

## Remote Deployment

Deploy the Docker image to any host. Set these env vars:

| Variable | Purpose |
|----------|---------|
| `MEMEX_GIT_URL` | Repo URL for cloning |
| `MEMEX_GIT_TOKEN` | GitHub PAT for private repos |
| `MEMEX_AUTH_TOKEN` | Bearer token for MCP endpoint auth |
| `CURSOR_API_KEY` | For kb_add (Cloud Agents API) |
| `OPENAI_API_KEY` | For semantic search (optional) |

Cursor MCP config for remote:

```json
{
  "mcpServers": {
    "memex": {
      "url": "https://your-host.example.com/mcp",
      "headers": {
        "Authorization": "Bearer your-token-here"
      }
    }
  }
}
```

## Search Backends

Configured in `config.yaml` under `search.backend`:

- **`bm25`** (default) — term-frequency relevance ranking via rank-bm25
- **`substring`** — zero-dependency fallback, case-insensitive match
- **`semantic`** — OpenAI embeddings with cosine similarity (requires `OPENAI_API_KEY`)

## CLI

The cloud agent uses CLI tools to query the KB during PR creation:

```bash
uv run python -m server.cli search "reinforcement learning"
uv run python -m server.cli list --type concept --tag ml
uv run python -m server.cli read /knowledge/rlhf.md
uv run python -m server.cli stats
```
