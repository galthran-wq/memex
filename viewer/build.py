#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.kb import parse_entry

try:
    import mistune
    _md = mistune.create_markdown(plugins=['math'])
except ImportError:
    _md = None


def build(repo_root: Path, output: Path) -> None:
    kb_dir = repo_root / "knowledge"
    if not kb_dir.exists():
        print("No knowledge/ directory found")
        return

    entries_data = []
    graph_nodes = []
    graph_edges = []
    backlinks: dict[str, list[dict]] = defaultdict(list)

    entries = []
    for md_path in sorted(kb_dir.glob("*.md")):
        entry = parse_entry(md_path, repo_root)
        if entry:
            entries.append(entry)

    for entry in entries:
        for edge in entry.edges:
            backlinks[edge.path].append({
                "path": entry.path,
                "title": entry.title,
                "label": edge.label,
                "description": edge.description,
            })

    for entry in entries:
        body_html = ""
        if _md:
            body = re.sub(r'(?<!\$)\$\$(.+?)\$\$(?!\$)', r'\n$$\n\1\n$$\n', entry.body)
            body_html = _md(body)

        entry_backlinks = backlinks.get(entry.path, [])

        entries_data.append({
            "path": entry.path,
            "slug": entry.slug,
            "title": entry.title,
            "type": entry.type,
            "summary": entry.summary,
            "tags": entry.tags,
            "created": entry.created,
            "updated": entry.updated,
            "edges": [
                {"path": e.path, "label": e.label, "description": e.description}
                for e in entry.edges
            ],
            "backlinks": entry_backlinks,
            "sources": [
                {"url": s.url, "title": s.title} for s in entry.sources
            ],
            "body_html": body_html,
        })

        graph_nodes.append({
            "id": entry.path,
            "title": entry.title,
            "type": entry.type,
        })

        for edge in entry.edges:
            graph_edges.append({
                "from": entry.path,
                "to": edge.path,
                "label": edge.label,
            })

    type_counts = defaultdict(int)
    all_tags = set()
    for e in entries_data:
        type_counts[e["type"]] += 1
        all_tags.update(e["tags"])

    data = {
        "entries": entries_data,
        "graph": {
            "nodes": graph_nodes,
            "edges": graph_edges,
        },
        "stats": {
            "total": len(entries_data),
            "by_type": dict(type_counts),
            "tags": sorted(all_tags),
            "total_edges": len(graph_edges),
        },
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2))
    print(f"Built data.json: {len(entries_data)} entries, {len(graph_edges)} edges")


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent.parent
    output = Path(__file__).resolve().parent / "data.json"
    build(repo_root, output)
