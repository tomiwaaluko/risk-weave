"""Hand-computed fixture tests for the propagation engine (RIS-13, ADR-001).

Every expected number below is worked out on paper from the ADR-001 formula:

    path_contribution = magnitude * product(edge weights) * 0.60**(hops - 1)
    raw_node_impact   = sum(retained path contributions)
    risk_score        = 100 * (1 - exp(-abs(raw_node_impact)))
"""

import math

import pytest

from riskweave.propagation import (
    DAMPING,
    ENGINE_VERSION,
    FLOOR,
    MAX_HOPS,
    GraphEdge,
    GraphNode,
    GraphSnapshot,
    Scenario,
    ScenarioError,
    ShockFactor,
    SnapshotError,
    propagate,
)


def node(node_id: str, node_type: str = "company") -> GraphNode:
    return GraphNode(node_id=node_id, node_type=node_type, name=node_id.upper())


def edge(edge_id: str, source: str, target: str, weight: float) -> GraphEdge:
    return GraphEdge(
        edge_id=edge_id,
        source_id=source,
        target_id=target,
        weight=weight,
        method_id="DER-CREDIT",
        provenance_ref=f"prov:{edge_id}",
    )


def snapshot(nodes, edges, snapshot_id: str = "snap-1") -> GraphSnapshot:
    return GraphSnapshot(
        snapshot_id=snapshot_id,
        graph_version="1.0.0",
        nodes=tuple(nodes),
        edges=tuple(edges),
    )


def scenario_on(node_id: str, magnitude: float = 1.0) -> Scenario:
    return Scenario(
        scenario_id="scn-1",
        factors=(ShockFactor(factor_id="f1", node_id=node_id, magnitude=magnitude),),
    )


def score(raw: float) -> float:
    return 100.0 * (1.0 - math.exp(-abs(raw)))


# --------------------------------------------------------------------------- #
# Hand-computed fixtures                                                       #
# --------------------------------------------------------------------------- #
class TestDiamond:
    """S→A→C and S→B→C converge on C: contributions must add, not double."""

    @pytest.fixture()
    def result(self):
        snap = snapshot(
            [node(n) for n in ("s", "a", "b", "c")],
            [
                edge("e1", "s", "a", 0.5),
                edge("e2", "s", "b", 0.4),
                edge("e3", "a", "c", 0.5),
                edge("e4", "b", "c", 0.5),
            ],
        )
        return propagate(snap, scenario_on("s"))

    def test_first_order_is_magnitude_times_weight(self, result):
        # damping**0 == 1, so first order is exactly magnitude * weight.
        assert result.impacts["a"].raw_impact == pytest.approx(0.5)
        assert result.impacts["b"].raw_impact == pytest.approx(0.4)

    def test_converging_paths_add(self, result):
        # 1.0*0.5*0.5*0.6 = 0.15 and 1.0*0.4*0.5*0.6 = 0.12 → 0.27
        assert result.impacts["c"].raw_impact == pytest.approx(0.27)
        assert len(result.impacts["c"].contributions) == 2

    def test_risk_score_formula(self, result):
        assert result.impacts["c"].risk_score == pytest.approx(score(0.27))

    def test_origin_node_not_impacted(self, result):
        assert "s" not in result.impacts


class TestCycle:
    """A→B→C→A: the cycle-closing path is rejected — no double count, no loop."""

    @pytest.fixture()
    def result(self):
        snap = snapshot(
            [node(n) for n in ("a", "b", "c")],
            [
                edge("e1", "a", "b", 0.5),
                edge("e2", "b", "c", 0.5),
                edge("e3", "c", "a", 0.5),
            ],
        )
        return propagate(snap, scenario_on("a"))

    def test_cycle_does_not_double_count(self, result):
        # b: 0.5 via one path; c: 0.25 * 0.6 = 0.15 via one path;
        # a itself: the only route back revisits a → rejected.
        assert result.impacts["b"].raw_impact == pytest.approx(0.5)
        assert len(result.impacts["b"].contributions) == 1
        assert result.impacts["c"].raw_impact == pytest.approx(0.15)
        assert len(result.impacts["c"].contributions) == 1
        assert "a" not in result.impacts


class TestFloorAndHops:
    def test_below_floor_first_hop_not_retained(self):
        snap = snapshot(
            [node("s"), node("x"), node("y")],
            [edge("e1", "s", "x", 0.004), edge("e2", "x", "y", 0.9)],
        )
        result = propagate(snap, scenario_on("s"))
        # 1.0 * 0.004 = 0.004 < 0.005: x not retained, y never explored.
        assert result.impacts == {}

    def test_below_floor_path_stops_expanding(self):
        snap = snapshot(
            [node("s"), node("p"), node("q")],
            [edge("e1", "s", "p", 0.05), edge("e2", "p", "q", 0.1)],
        )
        result = propagate(snap, scenario_on("s"))
        # p retained at 0.05; s→p→q = 1.0*0.05*0.1*0.6 = 0.003 < floor → dropped.
        assert result.impacts["p"].raw_impact == pytest.approx(0.05)
        assert "q" not in result.impacts

    def test_propagation_stops_at_three_hops(self):
        chain = ["s", "a", "b", "c", "d"]
        snap = snapshot(
            [node(n) for n in chain],
            [edge(f"e{i}", chain[i], chain[i + 1], 1.0) for i in range(len(chain) - 1)],
        )
        result = propagate(snap, scenario_on("s"))
        assert result.impacts["a"].raw_impact == pytest.approx(1.0)
        assert result.impacts["b"].raw_impact == pytest.approx(0.6)
        assert result.impacts["c"].raw_impact == pytest.approx(0.36)
        # d is four hops out: never reached even though 0.216 would clear the floor.
        assert "d" not in result.impacts
        deepest = max(c.hop_count for ni in result.impacts.values() for c in ni.contributions)
        assert deepest == MAX_HOPS


class TestDecompositionAndRanking:
    @pytest.fixture()
    def result(self):
        snap = snapshot(
            [node(n) for n in ("s", "a", "b", "c")],
            [
                edge("e1", "s", "a", 0.9),
                edge("e2", "s", "b", 0.4),
                edge("e3", "a", "c", 0.5),
                edge("e4", "b", "c", 0.5),
                edge("e5", "a", "b", 0.3),
            ],
        )
        return propagate(snap, scenario_on("s"))

    def test_path_contributions_sum_to_node_score(self, result):
        for impact in result.impacts.values():
            total = math.fsum(c.contribution for c in impact.contributions)
            assert impact.raw_impact == pytest.approx(total, abs=1e-15)
            assert impact.risk_score == pytest.approx(score(total))

    def test_contributions_ranked_by_magnitude(self, result):
        for impact in result.impacts.values():
            magnitudes = [abs(c.contribution) for c in impact.contributions]
            assert magnitudes == sorted(magnitudes, reverse=True)

    def test_ranked_entities_sorted_by_score(self, result):
        ranked = result.ranked_entities()
        scores = [ni.risk_score for ni in ranked]
        assert scores == sorted(scores, reverse=True)
        assert {ni.node_id for ni in ranked} == set(result.impacts)

    def test_paths_carry_method_and_provenance(self, result):
        for impact in result.impacts.values():
            for contribution in impact.contributions:
                for hop in contribution.edges:
                    assert hop.method_id
                    assert hop.provenance_ref

    def test_path_keys_are_unique_and_stable(self, result):
        keys = [c.path_key for ni in result.impacts.values() for c in ni.contributions]
        assert len(keys) == len(set(keys))
        for key in keys:
            assert key.startswith("scn-1|f1|")


class TestMultiFactor:
    def test_simultaneous_factors_add_on_shared_target(self):
        snap = snapshot(
            [node(n) for n in ("s1", "s2", "t")],
            [edge("e1", "s1", "t", 0.5), edge("e2", "s2", "t", 0.3)],
        )
        scn = Scenario(
            scenario_id="scn-multi",
            factors=(
                ShockFactor(factor_id="f1", node_id="s1", magnitude=1.0),
                ShockFactor(factor_id="f2", node_id="s2", magnitude=2.0),
            ),
        )
        result = propagate(snap, scn)
        # f1: 0.5; f2: 2.0*0.3 = 0.6 → 1.1 total from two distinct paths.
        assert result.impacts["t"].raw_impact == pytest.approx(1.1)
        assert {c.factor_id for c in result.impacts["t"].contributions} == {"f1", "f2"}

    def test_negative_weight_offsets_positive(self):
        snap = snapshot(
            [node(n) for n in ("s1", "s2", "t")],
            [edge("e1", "s1", "t", 0.5), edge("e2", "s2", "t", -0.2)],
        )
        scn = Scenario(
            scenario_id="scn-signed",
            factors=(
                ShockFactor(factor_id="f1", node_id="s1", magnitude=1.0),
                ShockFactor(factor_id="f2", node_id="s2", magnitude=1.0),
            ),
        )
        result = propagate(snap, scn)
        assert result.impacts["t"].raw_impact == pytest.approx(0.3)


class TestReproducibility:
    def build(self):
        snap = snapshot(
            [node(n) for n in ("s", "a", "b", "c")],
            [
                edge("e1", "s", "a", 0.7),
                edge("e2", "a", "b", 0.6),
                edge("e3", "b", "c", 0.5),
                edge("e4", "s", "c", 0.2),
            ],
        )
        scn = Scenario(
            scenario_id="scn-repro",
            factors=(ShockFactor(factor_id="f1", node_id="s", magnitude=1.5),),
            seed=42,
        )
        return propagate(snap, scn)

    def test_same_seed_reproduces_identically(self):
        first, second = self.build(), self.build()
        assert first == second  # bit-identical: dataclass equality on floats
        assert first.seed == 42

    def test_result_embeds_reproducibility_metadata(self):
        result = self.build()
        assert result.engine_version == ENGINE_VERSION
        assert result.snapshot_id == "snap-1"
        assert result.graph_version == "1.0.0"
        assert result.damping == DAMPING
        assert result.floor == FLOOR
        assert result.max_hops == MAX_HOPS


# --------------------------------------------------------------------------- #
# Validation                                                                   #
# --------------------------------------------------------------------------- #
class TestValidation:
    def test_rejects_edge_without_provenance(self):
        with pytest.raises(SnapshotError):
            GraphEdge(
                edge_id="e1",
                source_id="a",
                target_id="b",
                weight=0.5,
                method_id="DER-CREDIT",
                provenance_ref="  ",
            )

    def test_rejects_edge_without_method(self):
        with pytest.raises(SnapshotError):
            GraphEdge(
                edge_id="e1",
                source_id="a",
                target_id="b",
                weight=0.5,
                method_id="",
                provenance_ref="prov:e1",
            )

    def test_rejects_self_loop(self):
        with pytest.raises(SnapshotError):
            edge("e1", "a", "a", 0.5)

    def test_rejects_dangling_edge(self):
        with pytest.raises(SnapshotError):
            snapshot([node("a")], [edge("e1", "a", "ghost", 0.5)])

    def test_rejects_duplicate_edge_ids(self):
        with pytest.raises(SnapshotError):
            snapshot(
                [node("a"), node("b")],
                [edge("e1", "a", "b", 0.5), edge("e1", "a", "b", 0.4)],
            )

    def test_rejects_shock_on_unknown_node(self):
        snap = snapshot([node("a"), node("b")], [edge("e1", "a", "b", 0.5)])
        with pytest.raises(ScenarioError):
            propagate(snap, scenario_on("ghost"))

    def test_rejects_empty_scenario(self):
        with pytest.raises(ScenarioError):
            Scenario(scenario_id="scn", factors=())

    def test_rejects_duplicate_factor_ids(self):
        with pytest.raises(ScenarioError):
            Scenario(
                scenario_id="scn",
                factors=(
                    ShockFactor(factor_id="f1", node_id="a", magnitude=1.0),
                    ShockFactor(factor_id="f1", node_id="b", magnitude=1.0),
                ),
            )
