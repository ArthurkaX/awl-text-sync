from __future__ import annotations

import json
from collections import defaultdict, deque
from dataclasses import dataclass
from html import escape
from pathlib import Path

from .config import WorkspacePaths
from .models import ParsedBlockFile
from .stl_validation import (
    CALL_HEADER_PATTERN,
    build_block_declaration_index,
    collect_call_statements,
    resolve_call_target,
)


@dataclass(frozen=True)
class CallGraphEdge:
    caller: tuple[str, int]
    callee: tuple[str, int] | None
    callee_label: str
    line_number: int
    statement: str
    source: str


@dataclass(frozen=True)
class CallGraph:
    nodes: dict[tuple[str, int], ParsedBlockFile]
    adjacency: dict[tuple[str, int], tuple[CallGraphEdge, ...]]
    reverse_adjacency: dict[tuple[str, int], tuple[CallGraphEdge, ...]]
    roots: tuple[tuple[str, int], ...]
    reachable: frozenset[tuple[str, int]]
    unreachable: tuple[tuple[str, int], ...]
    external_calls: tuple[CallGraphEdge, ...]
    unresolved_calls: tuple[tuple[tuple[str, int], int, str], ...]


def default_call_graph_report_path(paths: WorkspacePaths) -> Path:
    return paths.build_dir / "Reports" / "call_graph.html"


def _iter_block_body_lines(source: str) -> list[tuple[int, str]]:
    in_body = False
    body_lines: list[tuple[int, str]] = []
    for line_number, raw_line in enumerate(source.splitlines(), 1):
        if not in_body:
            if raw_line.strip() == "BEGIN":
                in_body = True
            continue
        code_part = raw_line.split("//", 1)[0].strip()
        if code_part:
            body_lines.append((line_number, code_part))
    return body_lines


def _build_named_block_index(parsed: list[ParsedBlockFile]) -> dict[str, tuple[str, int]]:
    named_blocks: dict[str, tuple[str, int]] = {}
    conflicts: set[str] = set()
    for item in parsed:
        block = item.block
        for name in (block.symbol_name, block.internal_name):
            if not name or name in conflicts:
                continue
            key = (block.block_type, block.number)
            existing = named_blocks.get(name)
            if existing is None:
                named_blocks[name] = key
            elif existing != key:
                conflicts.add(name)
                named_blocks.pop(name, None)
    return named_blocks


def _block_display_name(item: ParsedBlockFile) -> str:
    block = item.block
    preferred_name = block.symbol_name or block.internal_name
    if preferred_name:
        return f"{block.block_type} {block.number} {preferred_name}"
    return f"{block.block_type} {block.number}"


def _block_summary(item: ParsedBlockFile) -> str:
    block = item.block
    name = block.symbol_name or block.internal_name
    if name:
        return f"{block.block_type} {block.number} - {name}"
    return f"{block.block_type} {block.number}"


def _format_target_label(target: str, resolved: tuple[str, int] | None) -> str:
    if resolved is not None:
        return f"{resolved[0]} {resolved[1]}"
    return target


def build_call_graph(parsed: list[ParsedBlockFile]) -> CallGraph:
    nodes = {(item.block.block_type, item.block.number): item for item in parsed}
    declaration_indexes = {
        key: build_block_declaration_index(item.block.source)
        for key, item in nodes.items()
        if item.block.block_type in {"FB", "FC", "OB"}
    }
    named_block_index = _build_named_block_index(parsed)

    adjacency_buckets: dict[tuple[str, int], list[CallGraphEdge]] = defaultdict(list)
    reverse_buckets: dict[tuple[str, int], list[CallGraphEdge]] = defaultdict(list)
    external_calls: list[CallGraphEdge] = []
    unresolved_calls: list[tuple[tuple[str, int], int, str]] = []

    for caller_key, declaration_index in declaration_indexes.items():
        caller_block = nodes[caller_key]
        for call_statement in collect_call_statements(_iter_block_body_lines(caller_block.block.source)):
            match = CALL_HEADER_PATTERN.match(call_statement.statement)
            if not match:
                unresolved_calls.append((caller_key, call_statement.line_number, call_statement.statement))
                continue
            target_text = match.group("target")
            resolved_target = resolve_call_target(target_text, declaration_index, named_block_index)
            if resolved_target is None:
                unresolved_calls.append((caller_key, call_statement.line_number, call_statement.statement))
                continue

            callee_key: tuple[str, int] | None = None
            if resolved_target.kind in {"FB", "FC", "OB", "DB"} and resolved_target.number is not None:
                candidate_key = (resolved_target.kind, resolved_target.number)
                if candidate_key in nodes:
                    callee_key = candidate_key

            edge = CallGraphEdge(
                caller=caller_key,
                callee=callee_key,
                callee_label=_format_target_label(target_text, callee_key),
                line_number=call_statement.line_number,
                statement=call_statement.statement,
                source=resolved_target.source,
            )

            if callee_key is None:
                external_calls.append(edge)
                continue

            adjacency_buckets[caller_key].append(edge)
            reverse_buckets[callee_key].append(edge)

    roots = tuple(
        sorted(
            key for key, item in nodes.items() if item.block.block_type == "OB"
        )
    )
    if not roots:
        roots = tuple(sorted(key for key in nodes if key not in reverse_buckets))
    if not roots:
        roots = tuple(sorted(nodes))

    reachable: set[tuple[str, int]] = set()
    queue: deque[tuple[str, int]] = deque(roots)
    while queue:
        key = queue.popleft()
        if key in reachable:
            continue
        reachable.add(key)
        for edge in adjacency_buckets.get(key, []):
            if edge.callee is not None and edge.callee not in reachable:
                queue.append(edge.callee)

    unreachable = tuple(sorted(key for key in nodes if key not in reachable))

    adjacency = {key: tuple(edges) for key, edges in sorted(adjacency_buckets.items())}
    reverse_adjacency = {key: tuple(edges) for key, edges in sorted(reverse_buckets.items())}
    return CallGraph(
        nodes=nodes,
        adjacency=adjacency,
        reverse_adjacency=reverse_adjacency,
        roots=roots,
        reachable=frozenset(reachable),
        unreachable=unreachable,
        external_calls=tuple(external_calls),
        unresolved_calls=tuple(unresolved_calls),
    )


def _graph_payload(graph: CallGraph, workspace_root: Path) -> str:
    nodes = []
    edges = []
    for key, item in sorted(graph.nodes.items()):
        block = item.block
        nodes.append(
            {
                "key": f"{key[0]} {key[1]}",
                "kind": block.block_type,
                "number": block.number,
                "name": block.symbol_name or block.internal_name or "",
                "filename": item.path.name,
                "path": str(item.path),
                "reachable": key in graph.reachable,
                "incoming": len(graph.reverse_adjacency.get(key, ())),
                "outgoing": len(graph.adjacency.get(key, ())),
                "is_root": key in graph.roots,
            }
        )

    for edge in graph.external_calls:
        edges.append(
            {
                "caller": f"{edge.caller[0]} {edge.caller[1]}",
                "callee": None if edge.callee is None else f"{edge.callee[0]} {edge.callee[1]}",
                "callee_label": edge.callee_label,
                "line": edge.line_number,
                "statement": edge.statement,
                "source": edge.source,
                "external": True,
            }
        )

    for caller, edges_list in graph.adjacency.items():
        for edge in edges_list:
            edges.append(
                {
                    "caller": f"{caller[0]} {caller[1]}",
                    "callee": None if edge.callee is None else f"{edge.callee[0]} {edge.callee[1]}",
                    "callee_label": edge.callee_label,
                    "line": edge.line_number,
                    "statement": edge.statement,
                    "source": edge.source,
                    "external": False,
                }
            )

    unresolved = [
        {
            "caller": f"{caller[0]} {caller[1]}",
            "line": line_number,
            "statement": statement,
        }
        for caller, line_number, statement in graph.unresolved_calls
    ]

    return json.dumps(
        {
            "workspace": str(workspace_root),
            "nodes": nodes,
            "edges": edges,
            "roots": [f"{key[0]} {key[1]}" for key in graph.roots],
            "reachable": [f"{key[0]} {key[1]}" for key in sorted(graph.reachable)],
            "unreachable": [f"{key[0]} {key[1]}" for key in graph.unreachable],
            "external_calls": len(graph.external_calls),
            "unresolved_calls": unresolved,
            "stats": {
                "total": len(graph.nodes),
                "reachable": len(graph.reachable),
                "unreachable": len(graph.unreachable),
                "external": len(graph.external_calls),
                "unresolved": len(graph.unresolved_calls),
            },
        },
        ensure_ascii=False,
    )


def render_call_graph_report(graph: CallGraph, workspace_root: Path) -> str:
    payload = _graph_payload(graph, workspace_root).replace("</", "<\\/")
    template = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>awl-text-sync Call Graph</title>
<style>
  :root {{
    --bg: #f4efe7;
    --panel: #fffdfa;
    --panel-alt: #f9f6f1;
    --text: #1f1b16;
    --muted: #6b6258;
    --accent: #2f6f77;
    --accent-2: #7c4f23;
    --border: #ddd3c6;
    --shadow: rgba(0, 0, 0, 0.08);
    --selected: #e7f1ef;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: Segoe UI, Arial, sans-serif;
    color: var(--text);
    background: linear-gradient(180deg, #efe6d8 0%, var(--bg) 260px);
  }}
  header {{
    padding: 24px 28px 14px;
    border-bottom: 1px solid rgba(0,0,0,0.06);
  }}
  h1 {{
    margin: 0 0 10px;
    font-size: 28px;
    letter-spacing: -0.02em;
  }}
  .summary {{
    color: var(--muted);
    line-height: 1.45;
  }}
  .toolbar {{
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin-top: 14px;
  }}
  button {{
    border: 0;
    border-radius: 999px;
    padding: 9px 14px;
    font: inherit;
    background: var(--accent);
    color: white;
    cursor: pointer;
  }}
  button.secondary {{
    background: #5e645f;
  }}
  main {{
    display: grid;
    grid-template-columns: 330px minmax(0, 1fr) 320px;
    gap: 16px;
    padding: 16px 16px 20px;
    min-height: calc(100vh - 120px);
  }}
  .panel {{
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 16px;
    box-shadow: 0 10px 28px var(--shadow);
    overflow: hidden;
  }}
  .panel-header {{
    padding: 14px 16px;
    background: linear-gradient(180deg, var(--panel-alt), var(--panel));
    border-bottom: 1px solid var(--border);
    font-weight: 700;
  }}
  .panel-body {{
    padding: 14px 16px 16px;
  }}
  .stack {{
    display: grid;
    gap: 12px;
  }}
  .search {{
    width: 100%;
    padding: 11px 12px;
    border: 1px solid var(--border);
    border-radius: 12px;
    font: inherit;
    background: #fff;
  }}
  .stats {{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }}
  .stat {{
    background: #f7f4ef;
    border: 1px solid #e7ddd0;
    border-radius: 12px;
    padding: 10px 12px;
  }}
  .stat .label {{
    color: var(--muted);
    font-size: 12px;
  }}
  .stat .value {{
    font-size: 18px;
    font-weight: 700;
    margin-top: 2px;
  }}
  .list {{
    max-height: calc(100vh - 320px);
    overflow: auto;
    border-top: 1px solid var(--border);
  }}
  .node-row {{
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 10px 14px;
    border-bottom: 1px solid #eee7dc;
    cursor: pointer;
  }}
  .node-row:hover {{
    background: #f6f1e8;
  }}
  .node-row.selected {{
    background: var(--selected);
  }}
  .node-main {{
    min-width: 0;
    flex: 1;
  }}
  .node-key {{
    font-weight: 700;
  }}
  .node-sub {{
    color: var(--muted);
    font-size: 12px;
    margin-top: 2px;
    word-break: break-word;
  }}
  .badge {{
    display: inline-block;
    padding: 3px 8px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
    border: 1px solid transparent;
    white-space: nowrap;
  }}
  .badge.root {{
    color: var(--accent);
    background: #e8f3f4;
    border-color: #c7dde0;
  }}
  .badge.reachable {{
    color: #24603a;
    background: #e6f3ea;
    border-color: #bfdcc8;
  }}
  .badge.unreachable {{
    color: #8e4f12;
    background: #f8eadc;
    border-color: #e7c59f;
  }}
  .badge.external {{
    color: #8b5d0d;
    background: #f8eedc;
    border-color: #e8d0a7;
  }}
  .detail-title {{
    font-size: 22px;
    font-weight: 800;
    margin-bottom: 6px;
  }}
  .detail-meta {{
    color: var(--muted);
    font-size: 13px;
    line-height: 1.5;
  }}
  .detail-grid {{
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 8px;
    margin: 16px 0;
  }}
  .detail-card {{
    background: #f7f4ef;
    border: 1px solid #e5dbce;
    border-radius: 12px;
    padding: 10px 12px;
  }}
  .detail-card .label {{
    color: var(--muted);
    font-size: 12px;
  }}
  .detail-card .value {{
    font-size: 16px;
    font-weight: 700;
    margin-top: 2px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin-top: 12px;
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
  }}
  th, td {{
    text-align: left;
    padding: 10px 12px;
    border-bottom: 1px solid #eee7dc;
    vertical-align: top;
    font-size: 13px;
  }}
  th {{
    background: #f7f4ef;
    color: var(--muted);
    font-weight: 700;
  }}
  tr.clickable {{
    cursor: pointer;
  }}
  tr.clickable:hover {{
    background: #f6f1e8;
  }}
  .callstmt {{
    font-family: Consolas, monospace;
    white-space: pre-wrap;
    word-break: break-word;
  }}
  .section {{
    margin-top: 16px;
  }}
  .section h3 {{
    margin: 0 0 8px;
    font-size: 16px;
  }}
  .empty {{
    color: var(--muted);
    font-size: 13px;
    padding: 8px 0;
  }}
  .pill-row {{
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 8px;
  }}
  .pill {{
    padding: 5px 8px;
    border-radius: 999px;
    background: #f1ece4;
    color: #5c5247;
    font-size: 12px;
  }}
  .external-item {{
    padding: 10px 0;
    border-bottom: 1px solid #eee7dc;
  }}
  .call-tree {{
    margin-top: 12px;
    border: 1px solid var(--border);
    border-radius: 14px;
    background: #fbf8f2;
    overflow: hidden;
  }}
  .tree-node {{
    border-top: 1px solid #eee7dc;
  }}
  .tree-node:first-child {{
    border-top: 0;
  }}
  .tree-node > summary {{
    list-style: none;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 12px;
    font-weight: 700;
  }}
  .tree-node > summary::-webkit-details-marker {{
    display: none;
  }}
  .tree-children {{
    padding: 0 0 8px 16px;
    border-left: 2px solid #e7dccf;
    margin-left: 12px;
  }}
  .tree-edge {{
    margin-top: 8px;
    padding: 10px 12px;
    border: 1px solid #efe3d2;
    border-radius: 12px;
    background: #fffdfa;
  }}
  .tree-edge-line {{
    color: var(--muted);
    font-size: 12px;
    margin-bottom: 6px;
  }}
  .tree-leaf {{
    color: var(--muted);
    font-size: 12px;
    padding: 10px 12px;
  }}
  .sidebar-note {{
    margin-top: 10px;
    color: var(--muted);
    font-size: 12px;
    line-height: 1.4;
  }}
  @media (max-width: 1100px) {{
    main {{
      grid-template-columns: 1fr;
    }}
    .list {{
      max-height: 320px;
    }}
  }}
</style>
<script>
const GRAPH = __PAYLOAD__;

const state = {{
  query: '',
  selected: GRAPH.roots[0] || (GRAPH.nodes[0] ? GRAPH.nodes[0].key : ''),
  focusPath: GRAPH.roots[0] || (GRAPH.nodes[0] ? GRAPH.nodes[0].key : '') ? [GRAPH.roots[0] || GRAPH.nodes[0].key] : [],
  showUnreachableOnly: false
}};

const byKey = new Map(GRAPH.nodes.map((node) => [node.key, node]));
const outgoing = new Map();
const incoming = new Map();
GRAPH.edges.forEach((edge) => {{
  if (edge.caller) {{
    if (!outgoing.has(edge.caller)) outgoing.set(edge.caller, []);
    outgoing.get(edge.caller).push(edge);
  }}
  if (edge.callee) {{
    if (!incoming.has(edge.callee)) incoming.set(edge.callee, []);
    incoming.get(edge.callee).push(edge);
  }}
}});

function blockLabel(node) {{
  return node.name ? `${{node.kind}} ${{node.number}} - ${{node.name}}` : `${{node.kind}} ${{node.number}}`;
}}

function shortStatement(statement) {{
  const trimmed = statement.replace(/\\s+/g, ' ').trim();
  return trimmed.length > 180 ? trimmed.slice(0, 180) + '…' : trimmed;
}}

function normalizeSearchText(value) {{
  return String(value).toLowerCase().replace(/[^a-z0-9]+/g, '');
}}

function nodeSearchKey(node) {{
  return normalizeSearchText(`${{node.kind}} ${{node.number}}`);
}}

function nodeSearchText(node) {{
  return normalizeSearchText(`${{node.key}} ${{node.kind}} ${{node.number}} ${{node.name}} ${{node.filename}} ${{node.path}}`);
}}

function searchScore(node) {{
  const query = normalizeSearchText(state.query);
  if (!query) return 0;
  const key = nodeSearchKey(node);
  const text = nodeSearchText(node);
  if (query === key) return 0;
  if (text.startsWith(query)) return 1;
  if (text.includes(query)) return 2;
  return 99;
}}

function badge(node) {{
  if (node.is_root) return '<span class="badge root">root</span>';
  if (!node.reachable) return '<span class="badge unreachable">unreachable</span>';
  return '<span class="badge reachable">reachable</span>';
}}

function nodeRowHtml(node, badgeHtml, selected = false) {{
  return `
    <div class="node-row ${{selected ? 'selected' : ''}}" data-key="${{escapeHtml(node.key)}}">
      <div class="node-main">
        <div class="node-key">${{escapeHtml(blockLabel(node))}}</div>
        <div class="node-sub">${{escapeHtml(node.filename)}}</div>
      </div>
      <div>${{badgeHtml}}</div>
    </div>
  `;
}}

function textItemHtml(titleHtml, bodyHtml) {{
  return `
    <div class="external-item">
      <div>${{titleHtml}}</div>
      <div class="node-sub">${{bodyHtml}}</div>
    </div>
  `;
}}

function tableHtml(headers, rowsHtml) {{
  return `
    <table>
      <thead><tr>${{headers.map((header) => `<th>${{escapeHtml(header)}}</th>`).join('')}}</tr></thead>
      <tbody>${{rowsHtml}}</tbody>
    </table>
  `;
}}

function escapeHtml(value) {{
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}}

function matches(node) {{
  if (state.showUnreachableOnly && node.reachable) return false;
  return searchScore(node) < 99;
}}

function exactSearchMatch(nodes) {{
  const query = normalizeSearchText(state.query);
  if (!query) return null;
  return nodes.find((node) => nodeSearchKey(node) === query) || null;
}}

function renderSearchStatus(filtered, exactMatch) {{
  const status = document.getElementById('search-status');
  if (!state.query) {{
    status.textContent = `${{GRAPH.nodes.length}} blocks`;
    return;
  }}
  const exact = exactMatch ? ` · exact: ${{blockLabel(exactMatch)}}` : '';
  status.textContent = `${{filtered.length}} match${{filtered.length === 1 ? '' : 'es'}} for "${{state.query}}"${{exact}}`;
}}

const DEBUG_CALL_GRAPH = true;

function debugLog(message, payload = null) {{
  if (!DEBUG_CALL_GRAPH || typeof console === 'undefined' || typeof console.debug !== 'function') return;
  if (payload === null) {{
    console.debug(`[call-graph] ${{message}}`);
    return;
  }}
  console.debug(`[call-graph] ${{message}}`, payload);
}}

function setSelected(key, mode = 'replace') {{
  if (!key) {{
    console.warn('[call-graph] Ignored empty selection target');
    return;
  }}
  if (!byKey.has(key)) {{
    console.warn(`[call-graph] Unknown selection target: ${{key}}`);
    return;
  }}
  const currentPath = Array.isArray(state.focusPath) ? state.focusPath : [];
  let nextPath = [key];
  if (mode === 'push' && currentPath.length) {{
    const existingIndex = currentPath.indexOf(key);
    nextPath = existingIndex >= 0 ? currentPath.slice(0, existingIndex + 1) : [...currentPath, key];
  }}
  debugLog('setSelected', {{ from: state.selected, to: key, mode, path: nextPath }});
  state.selected = key;
  state.focusPath = nextPath;
  render();
}}

function renderList() {{
  const list = document.getElementById('block-list');
  const filtered = GRAPH.nodes
    .filter(matches)
    .sort((left, right) => {{
      const scoreDelta = searchScore(left) - searchScore(right);
      if (scoreDelta) return scoreDelta;
      return blockLabel(left).localeCompare(blockLabel(right), undefined, {{ numeric: true, sensitivity: 'base' }});
    }});
  let selectionChangedByFilter = false;
  const exactMatch = exactSearchMatch(filtered);
  if (exactMatch) {{
    selectionChangedByFilter = state.selected !== exactMatch.key;
    state.selected = exactMatch.key;
  }} else if (filtered.length && !filtered.some((node) => node.key === state.selected)) {{
    selectionChangedByFilter = true;
    state.selected = filtered[0].key;
  }}
  if (selectionChangedByFilter) {{
    state.focusPath = state.selected ? [state.selected] : [];
  }}
  list.innerHTML = filtered.map((node) => nodeRowHtml(node, badge(node), node.key === state.selected)).join('') || '<div class="empty">No blocks match the current filter.</div>';
  list.querySelectorAll('.node-row').forEach((row) => {{
    row.addEventListener('click', () => {{
      debugLog('list click', {{ target: row.dataset.key }});
      setSelected(row.dataset.key, 'replace');
    }});
  }});
  renderSearchStatus(filtered, exactMatch);
  if (state.query && state.selected && typeof CSS !== 'undefined' && CSS.escape) {{
    const selectedRow = list.querySelector(`.node-row[data-key="${{CSS.escape(state.selected)}}"]`);
    if (selectedRow) {{
      requestAnimationFrame(() => selectedRow.scrollIntoView({{ block: 'nearest' }}));
    }}
  }}
}

function edgeRow(edge) {{
  const target = edge.callee ? edge.callee : edge.callee_label;
  return `
    <tr class="clickable" data-target="${{escapeHtml(edge.callee || '')}}">
      <td>${{escapeHtml(edge.line)}}</td>
      <td>${{escapeHtml(target)}}</td>
      <td class="callstmt">${{escapeHtml(shortStatement(edge.statement))}}</td>
    </tr>
  `;
}}

const TREE_PREVIEW_DEPTH = 1;

function treeFocusButton(target) {{
  return `<button type="button" class="tree-focus" data-target="${{escapeHtml(target)}}">Focus block</button>`;
}}

function renderCallTree(key, path = [], depth = 0) {{
  const node = byKey.get(key);
  if (!node) return '';
  const edges = outgoing.get(key) || [];
  const isRoot = path.length === 0;
  const open = isRoot || depth < 1;
  let html = `<details class="tree-node"${{open ? ' open' : ''}}>`;
  html += `<summary><span>${{escapeHtml(blockLabel(node))}}</span><span class="meta">${{edges.length}} calls</span></summary>`;
  html += '<div class="tree-children">';
  if (!edges.length) {{
    html += '<div class="tree-leaf">No workspace calls.</div>';
  }} else if (depth >= TREE_PREVIEW_DEPTH) {{
    html += `<div class="tree-leaf">Downstream calls: ${{edges.length}}. ${{treeFocusButton(node.key)}}</div>`;
  }} else {{
    for (const edge of edges) {{
      const callLine = `line ${{edge.line}} · ${{shortStatement(edge.statement)}}`;
      if (!edge.callee || !byKey.has(edge.callee)) {{
        html += `<div class="tree-edge"><div class="tree-edge-line">${{escapeHtml(callLine)}}</div><div class="tree-leaf">${{escapeHtml(edge.callee ? edge.callee_label : 'external call')}}</div></div>`;
        continue;
      }}
      if (path.includes(edge.callee)) {{
        html += `<div class="tree-edge"><div class="tree-edge-line">${{escapeHtml(callLine)}}</div><div class="tree-leaf">Cycle to ${{escapeHtml(edge.callee_label)}}.</div></div>`;
        continue;
      }}
      html += `<div class="tree-edge"><div class="tree-edge-line">${{escapeHtml(callLine)}}</div>${{renderCallTree(edge.callee, [...path, key], depth + 1)}}</div>`;
    }}
  }}
  html += '</div></details>';
  return html;
}}

function renderSelected() {{
  const node = byKey.get(state.selected) || GRAPH.nodes[0];
  const focusPath = Array.isArray(state.focusPath) && state.focusPath.length ? state.focusPath : [node.key];
  debugLog('renderSelected', {{ selected: state.selected, resolved: node.key, path: focusPath }});
  const outgoingEdges = outgoing.get(node.key) || [];
  const incomingEdges = incoming.get(node.key) || [];
  const outgoingRows = outgoingEdges.map(edgeRow).join('');
  const incomingRows = incomingEdges.map((edge) => `
    <tr class="clickable" data-target="${{escapeHtml(edge.caller)}}">
      <td>${{escapeHtml(edge.line)}}</td>
      <td>${{escapeHtml(edge.caller)}}</td>
      <td class="callstmt">${{escapeHtml(shortStatement(edge.statement))}}</td>
    </tr>
  `).join('');
  const breadcrumbHtml = focusPath.map((key, index) => {{
    const crumbNode = byKey.get(key);
    const label = crumbNode ? blockLabel(crumbNode) : key;
    if (index === focusPath.length - 1) {{
      return `<span class="pill">${{escapeHtml(label)}}</span>`;
    }}
    return `<button type="button" class="crumb" data-target="${{escapeHtml(key)}}">${{escapeHtml(label)}}</button>`;
  }}).join('<span class="detail-meta"> / </span>');
  const details = document.getElementById('selected-block');
  details.innerHTML = `
    <div class="detail-title">${{escapeHtml(blockLabel(node))}}</div>
    <div class="detail-meta">
      ${{escapeHtml(node.path)}}<br>
      File: ${{escapeHtml(node.filename)}}
    </div>
    <div class="pill-row">
      ${{breadcrumbHtml}}
    </div>
    <div class="pill-row">
      ${{badge(node)}}
      ${{node.is_root ? '<span class="pill">OB root</span>' : ''}}
      <span class="pill">incoming ${{incomingEdges.length}}</span>
      <span class="pill">outgoing ${{outgoingEdges.length}}</span>
    </div>
    <div class="detail-grid">
      <div class="detail-card"><div class="label">Kind</div><div class="value">${{escapeHtml(node.kind)}}</div></div>
      <div class="detail-card"><div class="label">Number</div><div class="value">${{escapeHtml(node.number)}}</div></div>
      <div class="detail-card"><div class="label">Reachability</div><div class="value">${{node.reachable ? 'reachable' : 'unreachable'}}</div></div>
      <div class="detail-card"><div class="label">Calls</div><div class="value">${{outgoingEdges.length}}</div></div>
    </div>
    <div class="section">
      <h3>Call tree from selected block</h3>
      <div class="call-tree">
        ${{renderCallTree(node.key)}}
      </div>
    </div>
    <div class="section">
      <h3>Outgoing calls</h3>
      ${{outgoingEdges.length ? tableHtml(['Line', 'Target', 'Call'], outgoingRows) : '<div class="empty">No outgoing workspace calls.</div>'}}
    </div>
    <div class="section">
      <h3>Incoming calls</h3>
      ${{incomingEdges.length ? tableHtml(['Line', 'Caller', 'Call'], incomingRows) : '<div class="empty">No incoming workspace calls.</div>'}}
    </div>
  `;
  details.querySelectorAll('.crumb').forEach((button) => {{
    button.addEventListener('click', () => {{
      debugLog('breadcrumb click', {{ target: button.dataset.target }});
      setSelected(button.dataset.target, 'push');
    }});
  }});
  details.querySelectorAll('tr.clickable').forEach((row) => {{
    row.addEventListener('click', () => {{
      debugLog('table click', {{ target: row.dataset.target }});
      setSelected(row.dataset.target, 'push');
    }});
  }});
  details.querySelectorAll('.tree-focus').forEach((button) => {{
    button.addEventListener('click', (event) => {{
      event.preventDefault();
      event.stopPropagation();
      debugLog('tree focus click', {{ target: button.dataset.target }});
      setSelected(button.dataset.target, 'push');
    }});
  }});
}

function setTextById(id, value) {{
  const element = document.getElementById(id);
  if (!element) {{
    console.warn(`Call graph report is missing expected element #${{id}}`);
    return;
  }}
  element.textContent = value;
}}

function renderSidebar() {{
  setTextById('workspace-name', GRAPH.workspace);
  setTextById('summary-blocks', GRAPH.stats.total);
  setTextById('summary-reachable', GRAPH.stats.reachable);
  setTextById('summary-unreachable', GRAPH.stats.unreachable);
  setTextById('summary-external', GRAPH.stats.external);
  setTextById('summary-unresolved', GRAPH.stats.unresolved);
}}

function renderStaticLists() {{
  const unreachable = document.getElementById('unreachable-list');
  unreachable.innerHTML = GRAPH.unreachable.length ? GRAPH.unreachable.map((key) => nodeRowHtml(byKey.get(key), '<span class="badge unreachable">unreachable</span>')).join('') : '<div class="empty">None</div>';
  unreachable.querySelectorAll('.node-row').forEach((row) => row.addEventListener('click', () => setSelected(row.dataset.key, 'replace')));

  const external = document.getElementById('external-list');
  const externalEdges = GRAPH.edges.filter((edge) => edge.external);
  external.innerHTML = externalEdges.length ? externalEdges.map((edge) => textItemHtml(`<strong>${{escapeHtml(edge.caller)}}</strong> → ${{escapeHtml(edge.callee_label)}}`, `line ${{escapeHtml(edge.line)}} · ${{escapeHtml(shortStatement(edge.statement))}}`)).join('') : '<div class="empty">None</div>';

  const unresolved = document.getElementById('unresolved-list');
  unresolved.innerHTML = GRAPH.unresolved_calls.length ? GRAPH.unresolved_calls.map((item) => textItemHtml(`<strong>${{escapeHtml(item.caller)}}</strong>`, `line ${{escapeHtml(item.line)}} · ${{escapeHtml(shortStatement(item.statement))}}`)).join('') : '<div class="empty">None</div>';
}

function render() {{
  renderList();
  renderSelected();
}}

document.addEventListener('DOMContentLoaded', () => {{
  renderSidebar();
  renderStaticLists();
  const search = document.getElementById('search');
  search.addEventListener('input', () => {{
    state.query = search.value;
    render();
  }});
  document.getElementById('unreachable-only').addEventListener('change', (event) => {{
    state.showUnreachableOnly = event.target.checked;
    render();
  }});
  document.getElementById('expand-all').addEventListener('click', () => {{
    state.showUnreachableOnly = false;
    search.value = '';
    state.query = '';
    document.getElementById('unreachable-only').checked = false;
    render();
  }});
  document.getElementById('focus-unreachable').addEventListener('click', () => {{
    state.showUnreachableOnly = true;
    document.getElementById('unreachable-only').checked = true;
    if (GRAPH.unreachable.length) {{
      state.selected = GRAPH.unreachable[0];
      state.focusPath = [GRAPH.unreachable[0]];
    }}
    render();
  }});
  render();
}});
</script>
</head>
<body>
  <header>
    <h1>Call Graph</h1>
    <div class="summary">
      Workspace: <span id="workspace-name"></span><br>
      This view shows each block once, with callers and callees separated so repeated subtrees do not flood the page.
    </div>
    <div class="toolbar">
      <button type="button" id="expand-all">Show all</button>
      <button type="button" class="secondary" id="focus-unreachable">Focus unreachable</button>
    </div>
  </header>
  <main>
    <aside class="panel">
      <div class="panel-header">Blocks</div>
      <div class="panel-body stack">
        <input id="search" class="search" type="search" placeholder="Search by name, number, file, or kind">
        <div id="search-status" class="detail-meta"></div>
        <label class="detail-meta"><input id="unreachable-only" type="checkbox"> Show unreachable only</label>
        <div class="stats">
          <div class="stat"><div class="label">Blocks</div><div class="value" id="summary-blocks"></div></div>
          <div class="stat"><div class="label">Reachable</div><div class="value" id="summary-reachable"></div></div>
          <div class="stat"><div class="label">Unreachable</div><div class="value" id="summary-unreachable"></div></div>
          <div class="stat"><div class="label">External</div><div class="value" id="summary-external"></div></div>
          <div class="stat"><div class="label">Unresolved</div><div class="value" id="summary-unresolved"></div></div>
        </div>
      </div>
      <div id="block-list" class="list"></div>
    </aside>

    <section class="panel">
      <div class="panel-header">Selected Block</div>
      <div class="panel-body">
        <div id="selected-block"></div>
      </div>
    </section>

    <aside class="stack">
      <section class="panel">
        <div class="panel-header">Unreachable Blocks</div>
        <div class="panel-body">
          <div id="unreachable-list"></div>
        </div>
      </section>
      <section class="panel">
        <div class="panel-header">External Calls</div>
        <div class="panel-body">
          <div id="external-list"></div>
        </div>
      </section>
      <section class="panel">
        <div class="panel-header">Unresolved Calls</div>
        <div class="panel-body">
          <div id="unresolved-list"></div>
        </div>
      </section>
    </aside>
  </main>
</body>
</html>
"""
    return template.replace("{{", "{").replace("}}", "}").replace("__PAYLOAD__", payload)


def write_call_graph_report(graph: CallGraph, workspace_root: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_call_graph_report(graph, workspace_root), encoding="utf-8", newline="")
    return output_path
