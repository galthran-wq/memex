from __future__ import annotations

from pathlib import Path, PurePosixPath

import httpx
from mcp.server.fastmcp import FastMCP

from server.config import Config
from server.cursor_client import CursorClient, CursorClientError
from server.github_client import GitHubClient, GitHubClientError, IMAGE_EXTENSIONS
from server.kb import KnowledgeBase
from server.prompt import build_prompt


def register_tools(mcp: FastMCP, kb: KnowledgeBase, config: Config) -> None:

    @mcp.tool(
        description=(
            "Search the knowledge base. Returns matching entries with "
            "title, path, type, tags, summary, and backlink count. "
            "Entries are atomic knowledge units linked via typed edges."
        )
    )
    def kb_search(query: str) -> str:
        results = kb.search(query, limit=20)
        if not results:
            return "No results found."
        lines = []
        for r in results:
            lines.append(
                f"[{r.type}] {r.title}\n"
                f"  path: {r.path}\n"
                f"  tags: {', '.join(r.tags)}\n"
                f"  summary: {r.summary}\n"
                f"  backlinks: {r.backlink_count}"
            )
        return "\n\n".join(lines)

    @mcp.tool(
        description=(
            "List knowledge base entries. Filter by type "
            "(concept, reference, insight, question, note) and/or tag. "
            "Returns title, type, summary, tags, and connection density "
            "for each entry."
        )
    )
    def kb_list(type: str | None = None, tag: str | None = None) -> str:
        entries = kb.list_entries(type_filter=type, tag_filter=tag)
        if not entries:
            return "No entries found."
        lines = []
        for e in entries:
            bl = kb.get_backlink_count(e.path)
            lines.append(
                f"[{e.type}] {e.title}\n"
                f"  path: {e.path}\n"
                f"  tags: {', '.join(e.tags)}\n"
                f"  summary: {e.summary}\n"
                f"  edges: {len(e.edges)}  backlinks: {bl}"
            )
        return "\n\n".join(lines)

    @mcp.tool(
        description=(
            "Read a knowledge base entry by path "
            "(e.g. /knowledge/rlhf.md). Returns frontmatter "
            "(title, summary, tags, edges, sources) and markdown body "
            "with cross-reference links. Also returns computed backlinks."
        )
    )
    def kb_read(path: str) -> str:
        entry = kb.read_entry(path)
        if not entry:
            return f"Entry not found: {path}"
        backlinks = kb.get_backlinks(path)
        parts = [
            f"# {entry.title}",
            f"type: {entry.type}",
            f"summary: {entry.summary}",
            f"tags: {', '.join(entry.tags)}",
            f"created: {entry.created}",
        ]
        if entry.updated:
            parts.append(f"updated: {entry.updated}")
        if entry.edges:
            parts.append("\nedges:")
            for edge in entry.edges:
                desc = f" — {edge.description}" if edge.description else ""
                parts.append(f"  [{edge.label}] {edge.path}{desc}")
        if entry.sources:
            parts.append("\nsources:")
            for s in entry.sources:
                title = f" ({s.title})" if s.title else ""
                parts.append(f"  {s.url}{title}")
        if backlinks:
            parts.append("\nbacklinks:")
            for bl in backlinks:
                desc = f" — {bl.description}" if bl.description else ""
                parts.append(f"  [{bl.label}] {bl.path} ({bl.title}){desc}")
        parts.append(f"\n---\n{entry.body}")
        return "\n".join(parts)

    @mcp.tool(
        description=(
            "Upload an image to the knowledge base assets on GitHub. "
            "Accepts a local file path or a URL as the source. "
            "Local file paths require the MCP server to run on the same "
            "machine (local/stdio transport). URLs work regardless of "
            "server location. "
            "Optionally specify a branch — if omitted, pushes to the "
            "default branch. Returns the repo-relative path for use in "
            "markdown entries: ![alt](/knowledge/assets/filename.png)"
        )
    )
    def kb_upload(source: str, branch: str | None = None) -> str:
        if not config.memex_git_token:
            return "Error: MEMEX_GIT_TOKEN not configured"
        if not config.github.owner or not config.github.repo:
            return "Error: GitHub repository not configured in config.yaml"

        is_url = source.startswith("http://") or source.startswith("https://")

        if is_url:
            filename = PurePosixPath(source.split("?")[0]).name
        else:
            filename = Path(source).name

        ext = PurePosixPath(filename).suffix.lower()
        if ext not in IMAGE_EXTENSIONS:
            return f"Error: Unsupported image type '{ext}'. Supported: {', '.join(sorted(IMAGE_EXTENSIONS))}"

        if is_url:
            try:
                resp = httpx.get(source, timeout=30, follow_redirects=True)
                resp.raise_for_status()
                content = resp.content
            except httpx.HTTPError as e:
                return f"Error: Failed to fetch URL: {e}"
        else:
            p = Path(source).expanduser().resolve()
            if not p.exists():
                return f"Error: File not found: {source}"
            content = p.read_bytes()

        target_branch = branch or config.github.default_branch
        repo_path = f"{config.knowledge.assets_dir}/{filename}"

        gh = GitHubClient(config.memex_git_token, config.github.owner, config.github.repo)
        try:
            if branch:
                gh.ensure_branch(branch, config.github.default_branch)
            result = gh.upload_file(repo_path, content, target_branch)
        except GitHubClientError as e:
            return f"Error: {e}"
        finally:
            gh.close()

        return (
            f"Uploaded: /{result.path}\n"
            f"Branch: {result.branch}\n"
            f"Use in entries: ![alt](/{result.path})"
        )

    @mcp.tool(
        description=(
            "Add knowledge to the base. Pass a natural language summary — "
            "concepts, insights, references, questions. A cloud agent will "
            "decompose it into atomic entries, create cross-references, "
            "and open a PR. Returns agent ID for status tracking. "
            "Optionally specify a branch to base the agent on (e.g. one "
            "where images were uploaded via kb_upload)."
        )
    )
    def kb_add(summary: str, branch: str | None = None) -> str:
        if not summary or not summary.strip():
            return "Error: Summary cannot be empty"
        if not config.cursor_api_key:
            return "Error: CURSOR_API_KEY not configured"
        if not config.github.owner or not config.github.repo:
            return "Error: GitHub repository not configured in config.yaml"

        target_branch = branch or config.github.default_branch

        images: list[str] = []
        if target_branch and config.memex_git_token:
            gh = GitHubClient(
                config.memex_git_token, config.github.owner, config.github.repo
            )
            try:
                images = gh.list_directory(config.knowledge.assets_dir, target_branch)
            except GitHubClientError:
                pass
            finally:
                gh.close()

        prompt_text = build_prompt(summary.strip(), kb, images=images)
        repo_url = f"https://github.com/{config.github.owner}/{config.github.repo}"

        client = CursorClient(config.cursor_api_key)
        try:
            result = client.launch_agent(
                prompt=prompt_text,
                repository=repo_url,
                ref=target_branch,
            )
        except CursorClientError as e:
            return f"Error: {e}"
        finally:
            client.close()

        return (
            f"Cloud agent launched.\n"
            f"Agent ID: {result.agent_id}\n"
            f"Dashboard: {result.agent_url}\n"
            f"Use kb_status with this agent_id to check progress."
        )

    @mcp.tool(
        description=(
            "Check status of a knowledge base update. "
            "Returns state (running/completed/failed) and PR URL when ready."
        )
    )
    def kb_status(agent_id: str) -> str:
        if not config.cursor_api_key:
            return "Error: CURSOR_API_KEY not configured"

        client = CursorClient(config.cursor_api_key)
        try:
            status = client.get_status(agent_id)
        except CursorClientError as e:
            return f"Error: {e}"
        finally:
            client.close()

        parts = [
            f"Status: {status.status}",
            f"Dashboard: {status.agent_url}",
        ]
        if status.pr_url:
            parts.append(f"PR: {status.pr_url}")
        return "\n".join(parts)
