from __future__ import annotations

import argparse
import sys
from pathlib import Path, PurePosixPath

import httpx

from server.config import load_config
from server.github_client import GitHubClient, GitHubClientError, IMAGE_EXTENSIONS
from server.kb import KnowledgeBase


def _make_kb() -> KnowledgeBase:
    config = load_config()
    config.sync.auto_pull = False
    return KnowledgeBase(config)


def cmd_search(args: argparse.Namespace) -> None:
    kb = _make_kb()
    results = kb.search(args.query, limit=args.limit)
    if not results:
        print("No results found.")
        return
    for r in results:
        print(f"[{r.type}] {r.title}")
        print(f"  path: {r.path}")
        print(f"  tags: {', '.join(r.tags)}")
        print(f"  summary: {r.summary}")
        print(f"  score: {r.score}  backlinks: {r.backlink_count}")
        print()


def cmd_list(args: argparse.Namespace) -> None:
    kb = _make_kb()
    entries = kb.list_entries(
        type_filter=args.type,
        tag_filter=args.tag,
    )
    if not entries:
        print("No entries found.")
        return
    for e in entries:
        bl = kb.get_backlink_count(e.path)
        print(f"[{e.type}] {e.title}")
        print(f"  path: {e.path}")
        print(f"  tags: {', '.join(e.tags)}")
        print(f"  summary: {e.summary}")
        print(f"  edges: {len(e.edges)}  backlinks: {bl}")
        print()


def cmd_read(args: argparse.Namespace) -> None:
    kb = _make_kb()
    entry = kb.read_entry(args.path)
    if not entry:
        print(f"Entry not found: {args.path}", file=sys.stderr)
        sys.exit(1)
    backlinks = kb.get_backlinks(args.path)

    print(f"# {entry.title}")
    print(f"type: {entry.type}")
    print(f"summary: {entry.summary}")
    print(f"tags: {', '.join(entry.tags)}")
    print(f"created: {entry.created}")
    if entry.updated:
        print(f"updated: {entry.updated}")
    if entry.edges:
        print(f"\nedges:")
        for edge in entry.edges:
            desc = f" — {edge.description}" if edge.description else ""
            print(f"  [{edge.label}] {edge.path}{desc}")
    if entry.sources:
        print(f"\nsources:")
        for s in entry.sources:
            title = f" ({s.title})" if s.title else ""
            print(f"  {s.url}{title}")
    if backlinks:
        print(f"\nbacklinks:")
        for bl in backlinks:
            desc = f" — {bl.description}" if bl.description else ""
            print(f"  [{bl.label}] {bl.path} ({bl.title}){desc}")
    print(f"\n---\n{entry.body}")


def cmd_stats(args: argparse.Namespace) -> None:
    kb = _make_kb()
    tc = kb.type_counts()
    tg = kb.tag_counts()
    total = kb.entry_count()
    total_edges = sum(len(e.edges) for e in kb.all_entries())
    print(f"Entries: {total}")
    print(f"Edges: {total_edges}")
    print(f"\nBy type:")
    for t, c in sorted(tc.items(), key=lambda x: x[1], reverse=True):
        print(f"  {t}: {c}")
    print(f"\nBy tag:")
    for t, c in sorted(tg.items(), key=lambda x: x[1], reverse=True):
        print(f"  {t}: {c}")


def cmd_upload(args: argparse.Namespace) -> None:
    config = load_config()
    if not config.memex_git_token:
        print("Error: MEMEX_GIT_TOKEN not configured", file=sys.stderr)
        sys.exit(1)
    if not config.github.owner or not config.github.repo:
        print("Error: GitHub repository not configured in config.yaml", file=sys.stderr)
        sys.exit(1)

    branch = args.branch or config.github.default_branch

    gh = GitHubClient(config.memex_git_token, config.github.owner, config.github.repo)
    try:
        if args.branch:
            gh.ensure_branch(branch, config.github.default_branch)

        for source in args.sources:
            is_url = source.startswith("http://") or source.startswith("https://")

            if is_url:
                filename = PurePosixPath(source.split("?")[0]).name
            else:
                filename = Path(source).name

            ext = PurePosixPath(filename).suffix.lower()
            if ext not in IMAGE_EXTENSIONS:
                print(
                    f"Skipping {filename}: unsupported type '{ext}'",
                    file=sys.stderr,
                )
                continue

            if is_url:
                try:
                    resp = httpx.get(source, timeout=30, follow_redirects=True)
                    resp.raise_for_status()
                    content = resp.content
                except httpx.HTTPError as e:
                    print(f"Error fetching {source}: {e}", file=sys.stderr)
                    continue
            else:
                p = Path(source).expanduser().resolve()
                if not p.exists():
                    print(f"File not found: {source}", file=sys.stderr)
                    continue
                content = p.read_bytes()

            repo_path = f"{config.knowledge.assets_dir}/{filename}"
            result = gh.upload_file(repo_path, content, branch)
            print(f"Uploaded: /{result.path}  (branch: {result.branch})")
    except GitHubClientError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        gh.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="memex-cli")
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=20)
    p_search.set_defaults(func=cmd_search)

    p_list = sub.add_parser("list")
    p_list.add_argument("--type", default=None)
    p_list.add_argument("--tag", default=None)
    p_list.set_defaults(func=cmd_list)

    p_read = sub.add_parser("read")
    p_read.add_argument("path")
    p_read.set_defaults(func=cmd_read)

    p_stats = sub.add_parser("stats")
    p_stats.set_defaults(func=cmd_stats)

    p_upload = sub.add_parser("upload")
    p_upload.add_argument("sources", nargs="+")
    p_upload.add_argument("--branch", default=None)
    p_upload.set_defaults(func=cmd_upload)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
