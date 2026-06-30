"""
graph.py — Citation graph builder and traversal for Temporal Graph-RAG.

Builds an in-memory adjacency structure from the citation_edges table,
then provides BFS expansion and bridge-paper detection without any
external graph library (pure Python dicts/sets).
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Optional

logger = logging.getLogger(__name__)


# ── In-memory graph ───────────────────────────────────────────────────────────

class CitationGraph:
    """
    Directed graph: edge  source → target  means 'source cites target'.
    Stores forward edges (cites) and reverse edges (cited-by) for fast lookup.
    """

    def __init__(self):
        # source_id → {target_id, ...}
        self._forward: dict[str, set[str]] = defaultdict(set)
        # target_id → {source_id, ...}
        self._reverse: dict[str, set[str]] = defaultdict(set)
        # corpus_id → publication year (int or None)
        self._year: dict[str, Optional[int]] = {}

    def add_edge(self, source: str, target: str, source_year: Optional[int] = None):
        self._forward[source].add(target)
        self._reverse[target].add(source)
        if source_year is not None and source not in self._year:
            self._year[source] = source_year

    def register_paper(self, corpus_id: str, year: Optional[int]):
        if corpus_id not in self._year:
            self._year[corpus_id] = year

    def neighbors(self, node: str) -> set[str]:
        """Papers that `node` cites."""
        return self._forward.get(node, set())

    def cited_by(self, node: str) -> set[str]:
        """Papers that cite `node`."""
        return self._reverse.get(node, set())

    def year_of(self, node: str) -> Optional[int]:
        return self._year.get(node)

    def all_nodes(self) -> set[str]:
        nodes: set[str] = set(self._year.keys())
        nodes.update(self._forward.keys())
        nodes.update(self._reverse.keys())
        return nodes

    def edge_count(self) -> int:
        return sum(len(v) for v in self._forward.values())

    def node_count(self) -> int:
        return len(self.all_nodes())


# ── Loader ────────────────────────────────────────────────────────────────────

def load_graph(session) -> CitationGraph:
    """
    Build a CitationGraph from the database.
    Loads all citation_edges and all paper years.
    """
    from database import CitationEdge, Paper  # local import to avoid circular refs

    g = CitationGraph()

    # Register all known papers with their years
    for p in session.query(Paper.corpus_id, Paper.year).all():
        g.register_paper(p.corpus_id, p.year)

    # Load citation edges
    for edge in session.query(CitationEdge).all():
        g.add_edge(edge.source_corpus_id, edge.target_corpus_id, edge.source_year)

    logger.info(f"Loaded citation graph: {g.node_count()} nodes, {g.edge_count()} edges")
    return g


# ── BFS subgraph expansion ────────────────────────────────────────────────────

def expand_subgraph(
    graph: CitationGraph,
    seeds: list[str],
    max_hops: int = 3,
    max_nodes: int = 150,
) -> set[str]:
    """
    BFS from seed papers outward (following citation edges in both directions).
    Returns the set of corpus_ids in the subgraph.
    """
    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque()

    for s in seeds:
        if s not in visited:
            visited.add(s)
            queue.append((s, 0))

    while queue and len(visited) < max_nodes:
        node, depth = queue.popleft()
        if depth >= max_hops:
            continue
        # Expand in both directions (cites + cited-by)
        neighbours = graph.neighbors(node) | graph.cited_by(node)
        for nb in neighbours:
            if nb not in visited:
                visited.add(nb)
                queue.append((nb, depth + 1))
                if len(visited) >= max_nodes:
                    break

    return visited


# ── Bridge paper detection ────────────────────────────────────────────────────

def find_bridge_papers(
    graph: CitationGraph,
    subgraph_nodes: set[str],
    seeds: set[str],
    top_k: int = 15,
) -> list[str]:
    """
    A "bridge" paper is one that is cited by many papers in the subgraph
    AND cites many papers in the subgraph — i.e., high in-degree + out-degree
    within the subgraph.  Acts as a conceptual hub connecting ideas.

    Returns corpus_ids sorted by bridge score descending.
    """
    scores: dict[str, float] = {}

    for node in subgraph_nodes:
        # In-degree within subgraph (papers in subgraph that cite this node)
        in_deg = len(graph.cited_by(node) & subgraph_nodes)
        # Out-degree within subgraph (papers in subgraph that this node cites)
        out_deg = len(graph.neighbors(node) & subgraph_nodes)
        # Hub score: harmonic mean of in/out, biased toward high in-degree
        if in_deg + out_deg > 0:
            scores[node] = (1.5 * in_deg + out_deg) / (in_deg + out_deg + 1)
        else:
            scores[node] = 0.0

    # Prioritize non-seed papers so we surface the connective tissue,
    # but keep seeds if nothing else ranks higher
    sorted_nodes = sorted(scores, key=lambda n: (n not in seeds, -scores[n]))

    return sorted_nodes[:top_k]


# ── Temporal ordering ─────────────────────────────────────────────────────────

def sort_by_year(
    graph: CitationGraph,
    corpus_ids: list[str],
    known_years: Optional[dict[str, int]] = None,
) -> list[str]:
    """
    Sort corpus_ids chronologically (ascending year).
    Papers with unknown year are placed at the end.
    `known_years` can supply additional year data from the Paper table.
    """
    def year_key(cid: str) -> int:
        y = (known_years or {}).get(cid) or graph.year_of(cid)
        return y if y else 9999

    return sorted(corpus_ids, key=year_key)
