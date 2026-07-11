"""Property-based tests for the propagation engine (RIS-13).

Random graphs via hypothesis: scores stay bounded, decomposition always holds,
scores are monotone in shock magnitude for non-negative weights, and the engine
is a pure function (identical inputs → identical outputs).
"""

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from riskweave.propagation import (
    GraphEdge,
    GraphNode,
    GraphSnapshot,
    Scenario,
    ShockFactor,
    propagate,
)


@st.composite
def graphs(draw):
    """A random directed graph (no self-loops, no duplicate arcs) with weights."""
    n_nodes = draw(st.integers(min_value=2, max_value=10))
    node_ids = [f"n{i}" for i in range(n_nodes)]
    arcs = draw(
        st.sets(
            st.tuples(st.integers(0, n_nodes - 1), st.integers(0, n_nodes - 1)).filter(
                lambda ab: ab[0] != ab[1]
            ),
            min_size=1,
            max_size=min(30, n_nodes * (n_nodes - 1)),
        )
    )
    weights = draw(
        st.lists(
            st.floats(min_value=0.0, max_value=1.5, allow_nan=False),
            min_size=len(arcs),
            max_size=len(arcs),
        )
    )
    nodes = tuple(GraphNode(node_id=i, node_type="company", name=i) for i in node_ids)
    edges = tuple(
        GraphEdge(
            edge_id=f"e{k}",
            source_id=node_ids[a],
            target_id=node_ids[b],
            weight=w,
            method_id="DER-CREDIT",
            provenance_ref=f"prov:e{k}",
        )
        for k, ((a, b), w) in enumerate(zip(sorted(arcs), weights, strict=True))
    )
    return GraphSnapshot(snapshot_id="snap-prop", graph_version="1.0.0", nodes=nodes, edges=edges)


def shock(snapshot: GraphSnapshot, magnitude: float) -> Scenario:
    origin = snapshot.nodes[0].node_id
    return Scenario(
        scenario_id="scn-prop",
        factors=(ShockFactor(factor_id="f1", node_id=origin, magnitude=magnitude),),
    )


@settings(max_examples=200, deadline=None)
@given(graphs(), st.floats(min_value=0.0, max_value=10.0, allow_nan=False))
def test_scores_bounded(snap, magnitude):
    result = propagate(snap, shock(snap, magnitude))
    for impact in result.impacts.values():
        assert 0.0 <= impact.risk_score < 100.0
        assert math.isfinite(impact.raw_impact)


@settings(max_examples=200, deadline=None)
@given(graphs(), st.floats(min_value=0.0, max_value=10.0, allow_nan=False))
def test_decomposition_always_exact(snap, magnitude):
    result = propagate(snap, shock(snap, magnitude))
    for impact in result.impacts.values():
        total = math.fsum(sorted((c.contribution for c in impact.contributions), key=abs))
        assert math.isclose(impact.raw_impact, total, rel_tol=1e-12, abs_tol=1e-15)


@settings(max_examples=200, deadline=None)
@given(
    graphs(),
    st.floats(min_value=0.001, max_value=5.0, allow_nan=False),
    st.floats(min_value=1.0, max_value=4.0, allow_nan=False),
)
def test_scores_monotone_in_magnitude(snap, magnitude, multiplier):
    """With non-negative weights, a bigger shock never lowers any node's score."""
    smaller = propagate(snap, shock(snap, magnitude))
    larger = propagate(snap, shock(snap, magnitude * multiplier))
    for node_id, impact in smaller.impacts.items():
        assert node_id in larger.impacts
        assert larger.impacts[node_id].risk_score >= impact.risk_score - 1e-12


@settings(max_examples=100, deadline=None)
@given(graphs(), st.floats(min_value=0.0, max_value=10.0, allow_nan=False))
def test_pure_function(snap, magnitude):
    assert propagate(snap, shock(snap, magnitude)) == propagate(snap, shock(snap, magnitude))


@settings(max_examples=100, deadline=None)
@given(graphs(), st.floats(min_value=0.0, max_value=10.0, allow_nan=False))
def test_no_path_exceeds_three_hops_or_revisits(snap, magnitude):
    result = propagate(snap, shock(snap, magnitude))
    for impact in result.impacts.values():
        for contribution in impact.contributions:
            assert 1 <= contribution.hop_count <= 3
            touched = [contribution.edges[0].source_id] + [e.target_id for e in contribution.edges]
            assert len(touched) == len(set(touched))
