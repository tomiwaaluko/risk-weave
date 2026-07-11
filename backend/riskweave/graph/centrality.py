"""Structural systemic-importance score (`RW-FR-019`).

This is a **structural** property of the graph — who is central in the web of
exposures regardless of any scenario — and MUST be stored and displayed
separately from scenario impact so the UI can distinguish "systemically
important" from "hit hard by this shock".

We use weighted PageRank on the exposure graph (edge weight = absolute derived
weight, i.e. exposure strength). PageRank answers "how much does risk flowing
through the network concentrate on this node", which is the systemic-importance
question; it is deterministic (power iteration to a fixed tolerance), needs no
external library, and is stable on the curated graph size.

Rejected alternatives: raw degree (ignores who you are connected to);
betweenness (O(VE), and less aligned with contagion flow than PageRank).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

DAMPING = 0.85
MAX_ITERATIONS = 200
TOLERANCE = 1e-12


def transmission_centrality(
    node_ids: Sequence[str],
    arcs: Sequence[tuple[str, str, float]],
    damping: float = DAMPING,
) -> Mapping[str, float]:
    """Weighted PageRank over the exposure graph.

    ``arcs`` are ``(source, target, weight)`` with non-negative weights.
    Returns a score per node summing to 1.0. Deterministic: fixed init, fixed
    iteration order, fixed tolerance.
    """
    nodes = list(node_ids)
    n = len(nodes)
    if n == 0:
        return {}

    index = {node: i for i, node in enumerate(nodes)}
    out_weight = [0.0] * n
    out_arcs: list[list[tuple[int, float]]] = [[] for _ in range(n)]
    for source, target, weight in arcs:
        if source not in index or target not in index:
            continue
        w = abs(float(weight))
        if w == 0.0:
            continue
        s = index[source]
        out_arcs[s].append((index[target], w))
        out_weight[s] += w

    rank = [1.0 / n] * n
    teleport = (1.0 - damping) / n
    for _ in range(MAX_ITERATIONS):
        dangling = damping * sum(rank[i] for i in range(n) if out_weight[i] == 0.0) / n
        nxt = [teleport + dangling] * n
        for i in range(n):
            if out_weight[i] == 0.0:
                continue
            share = damping * rank[i] / out_weight[i]
            for j, w in out_arcs[i]:
                nxt[j] += share * w
        delta = sum(abs(nxt[i] - rank[i]) for i in range(n))
        rank = nxt
        if delta < TOLERANCE:
            break

    total = sum(rank)
    if total > 0:
        rank = [r / total for r in rank]
    return {nodes[i]: rank[i] for i in range(n)}
