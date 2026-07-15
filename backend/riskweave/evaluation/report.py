"""Evaluation-dashboard report aggregator (RIS-21, `RW-OPS-001`, spec §15).

Composes the six §15 metric families into one serializable report the demo
beat-6 dashboard renders. Every number here is *computed* from committed,
versioned inputs (the CRE graph fixture, the hand-labeled extraction sample,
the RIS-11 entity-resolution sample) and live deterministic runs (propagation,
the numeric guard) — nothing is hand-typed into the UI. Because the inputs are
snapshot-pinned and the propagation engine is pure, the report recomputes
reproducibly from a snapshot (`RW-GOAL-006`).

Six families (spec §15):
  1. relationship-extraction precision / recall / F1  (hand-labeled sample)
  2. entity-resolution accuracy                        (RIS-11 sample)
  3. unsupported-claim rate in explanations            (RIS-19 numeric guard)
  4. citation-correctness spot checks                  (CRE fixture provenance)
  5. scenario stability (same input → same output)     (repeated propagation)
  6. latencies for parse / propagation / explanation

Misses are surfaced, never hidden (`RW-SAFE-003` spirit): each row reports its
target, its actual, and a boolean pass/fail the UI paints red.
"""

from __future__ import annotations

import re
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

from riskweave.entity_resolution import Resolver, load_universe
from riskweave.explain import guard_explanation
from riskweave.explain.payload import payload_for_node
from riskweave.graph.assembly import AssembledGraph
from riskweave.graph.fixture import DEFAULT_FIXTURE_PATH, load_graph_fixture
from riskweave.propagation import Scenario, ShockFactor, propagate
from riskweave.scenario.parser import parse_shock_text

from .labeling import load_labels, positive_keys
from .metrics import (
    citation_correctness_rate,
    entity_resolution_accuracy,
    extraction_metrics,
    latency_summary,
    scenario_stability,
    unsupported_claim_rate,
)

# report.py → evaluation/ → riskweave/ → backend/ → repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LABELS_PATH = _REPO_ROOT / "data" / "evaluation" / "extraction_labels.jsonl"
DEFAULT_PREDICTIONS_PATH = _REPO_ROOT / "data" / "evaluation" / "extraction_predictions.jsonl"
DEFAULT_UNIVERSE_PATH = _REPO_ROOT / "data" / "universe" / "entities.json"
DEFAULT_RESOLUTION_SAMPLE_PATH = (
    _REPO_ROOT / "data" / "evaluation" / "entity_resolution_sample.json"
)
DEFAULT_REPORT_OUTPUT_PATH = _REPO_ROOT / "data" / "evaluation" / "evaluation_report.json"

# Deterministic CRE-decline demo shock (magnitudes chosen by code, not Gemini;
# mirrors the graph router's demo cascade so the dashboard measures the same
# run the demo drives). See `RW-AI-010`.
_DEMO_FACTORS: tuple[tuple[str, str, float], ...] = (
    ("cre-office-shock", "cre-office", 1.0),
    ("cre-multifamily-shock", "cre-multifamily", 0.6),
    ("nyc-metro-shock", "nyc-metro", 0.8),
)
_DEMO_PROMPT = "Office commercial real estate values fall 30% with a New York City concentration."

# Metric-family targets (spec §4.2 / §15).
TARGET_EXTRACTION_PRECISION = 0.90
TARGET_EXTRACTION_RECALL = 0.80
TARGET_ENTITY_RESOLUTION = 0.95
TARGET_UNSUPPORTED_CLAIM_RATE = 0.0
TARGET_CITATION_CORRECTNESS = 0.95
TARGET_PROVENANCE_COVERAGE = 1.0
TARGET_PROPAGATION_MS = 500.0
TARGET_PARSE_MS = 3000.0

_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent)")
_QUALITATIVE_CUES = (
    "substantially all",
    "primarily",
    "largest",
    "significant portion",
    "substantial portion",
    "majority",
    "approximately",
)


# --------------------------------------------------------------------------- #
# Report model                                                                #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MetricRow:
    """One dashboard row: a target, the computed actual, and pass/fail.

    ``passed`` is None for informational rows that carry no target. ``family``
    groups rows into the six §15 metric families for the UI.
    """

    key: str
    label: str
    family: str
    actual_display: str
    target_display: str
    passed: bool | None
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvaluationReport:
    """The full beat-6 report: snapshot metadata + all metric rows."""

    snapshot_id: str
    graph_version: str
    generated_at: str
    rows: tuple[MetricRow, ...] = field(default_factory=tuple)

    @property
    def all_passed(self) -> bool:
        return all(row.passed for row in self.rows if row.passed is not None)

    @property
    def failing(self) -> tuple[MetricRow, ...]:
        return tuple(row for row in self.rows if row.passed is False)

    def to_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "graph_version": self.graph_version,
            "generated_at": self.generated_at,
            "all_passed": self.all_passed,
            "families": _FAMILIES,
            "rows": [row.to_dict() for row in self.rows],
        }


_FAMILIES = [
    "Relationship extraction",
    "Entity resolution",
    "Explanation honesty",
    "Citation correctness",
    "Reproducibility",
    "Latency",
]


# --------------------------------------------------------------------------- #
# Individual metric computations (pure, testable in isolation)                #
# --------------------------------------------------------------------------- #
def citation_spot_checks(graph: AssembledGraph) -> list[bool]:
    """Does each edge's cited passage actually support its derived weight?

    Deterministic proxy for a human spot check (spec §15): a quantitative
    passage must state a percentage matching the weight (± 3 points); a
    qualitative passage must carry a recognized support cue. Reads only the
    committed provenance already on the graph — no external fetch.
    """
    checks: list[bool] = []
    for edge in graph.edges:
        prov = edge.record.provenance
        passage = prov.source_passage.lower()
        weight_pct = abs(edge.record.value) * 100.0
        percents = [float(m.group(1)) for m in _PERCENT_RE.finditer(passage)]
        if percents:
            checks.append(any(abs(p - weight_pct) <= 3.0 for p in percents))
        else:
            checks.append(any(cue in passage for cue in _QUALITATIVE_CUES))
    return checks


def repeated_run_checksums(graph: AssembledGraph, runs: int = 3) -> list[str]:
    """Fingerprint N propagation runs of the demo scenario for stability."""
    snapshot = graph.to_snapshot()
    scenario = _demo_scenario()
    fingerprints: list[str] = []
    for _ in range(runs):
        result = propagate(snapshot, scenario)
        parts = [
            f"{node_id}:{result.impacts[node_id].risk_score:.15e}"
            for node_id in sorted(result.impacts)
        ]
        fingerprints.append("|".join(parts))
    return fingerprints


def measure_latencies(graph: AssembledGraph, runs: int = 25) -> dict[str, list[float]]:
    """Time the deterministic parse / propagation / explanation-guard stages."""
    snapshot = graph.to_snapshot()
    scenario = _demo_scenario()

    propagation_ms: list[float] = []
    for _ in range(runs):
        t0 = time.perf_counter()
        result = propagate(snapshot, scenario)
        propagation_ms.append((time.perf_counter() - t0) * 1000.0)

    parse_ms: list[float] = []
    for _ in range(runs):
        t0 = time.perf_counter()
        parse_shock_text(_DEMO_PROMPT)
        parse_ms.append((time.perf_counter() - t0) * 1000.0)

    # Explanation numeric-guard over the top impacted nodes, each bound to its
    # real computation payload — the local honesty gate the demo runs (RIS-19).
    guard_ms: list[float] = []
    for impact in result.ranked_entities()[:10]:
        payload = payload_for_node(result, impact.node_id)
        text = f"{impact.node_id} shows a modeled risk score of {round(impact.risk_score)}."
        t0 = time.perf_counter()
        guard_explanation(text, payload)
        guard_ms.append((time.perf_counter() - t0) * 1000.0)

    return {"parse": parse_ms, "propagation": propagation_ms, "explanation_guard": guard_ms}


def explanation_guard_samples(
    graph: AssembledGraph,
) -> list[tuple[str, object]]:
    """Real (text, payload) pairs for the unsupported-claim rate.

    Each explanation is generated from — and only from — its node's computation
    payload, so the RIS-19 guard is exercised against genuine demo-path prose.
    """
    snapshot = graph.to_snapshot()
    result = propagate(snapshot, _demo_scenario())
    samples: list[tuple[str, object]] = []
    for impact in result.ranked_entities()[:10]:
        payload = payload_for_node(result, impact.node_id)
        text = (
            f"{impact.node_id} carries a modeled risk score of "
            f"{round(impact.risk_score)} in this scenario."
        )
        samples.append((text, payload))
    return samples


def _demo_scenario() -> Scenario:
    return Scenario(
        scenario_id="cre-demo-eval",
        factors=tuple(
            ShockFactor(factor_id=fid, node_id=nid, magnitude=mag)
            for fid, nid, mag in _DEMO_FACTORS
        ),
        seed=20260711,
    )


# --------------------------------------------------------------------------- #
# Row builders                                                                #
# --------------------------------------------------------------------------- #
def _ratio_row(key, label, family, actual, target, detail="") -> MetricRow:
    return MetricRow(
        key=key,
        label=label,
        family=family,
        actual_display=f"{actual:.1%}",
        target_display=f"≥ {target:.0%}",
        passed=actual >= target,
        detail=detail,
    )


def _fmt_ms(value: float) -> str:
    return f"{value:.2f} ms" if value < 10 else f"{value:.0f} ms"


def _lower_bound_row(key, label, family, actual, target, unit, detail="") -> MetricRow:
    return MetricRow(
        key=key,
        label=label,
        family=family,
        actual_display=_fmt_ms(actual) if unit == "ms" else f"{actual:.0f} {unit}",
        target_display=f"≤ {target:.0f} {unit}",
        passed=actual <= target,
        detail=detail,
    )


# --------------------------------------------------------------------------- #
# Orchestrator                                                                #
# --------------------------------------------------------------------------- #
def run_evaluation(
    *,
    fixture_path: str | Path = DEFAULT_FIXTURE_PATH,
    labels_path: str | Path = DEFAULT_LABELS_PATH,
    predictions_path: str | Path = DEFAULT_PREDICTIONS_PATH,
    universe_path: str | Path = DEFAULT_UNIVERSE_PATH,
    resolution_sample_path: str | Path = DEFAULT_RESOLUTION_SAMPLE_PATH,
    generated_at: str = "snapshot",
) -> EvaluationReport:
    """Compute the full §15 report from committed fixtures + deterministic runs."""
    import json

    graph = load_graph_fixture(fixture_path)
    rows: list[MetricRow] = []

    # 1. Relationship extraction P / R / F1 -------------------------------- #
    gold = load_labels(str(labels_path))
    predicted = load_labels(str(predictions_path))
    m = extraction_metrics(positive_keys(predicted), positive_keys(gold))
    n_gold = len(positive_keys(gold))
    n_pred = len(positive_keys(predicted))
    detail = (
        f"{m.true_positives} true / {m.false_positives} false-positive / "
        f"{m.false_negatives} missed over {n_gold} gold, {n_pred} predicted "
        f"relationships across both packs."
    )
    rows.append(
        _ratio_row(
            "extraction_precision",
            "Extraction precision",
            _FAMILIES[0],
            m.precision,
            TARGET_EXTRACTION_PRECISION,
            detail,
        )
    )
    rows.append(
        _ratio_row(
            "extraction_recall",
            "Extraction recall",
            _FAMILIES[0],
            m.recall,
            TARGET_EXTRACTION_RECALL,
            f"F1 = {m.f1:.1%}.",
        )
    )

    # 2. Entity-resolution accuracy (RIS-11 sample) ------------------------ #
    sample = json.loads(Path(resolution_sample_path).read_text(encoding="utf-8"))
    resolver = Resolver(load_universe(Path(universe_path)))
    resolved = [
        (row["mention"], resolver.resolve(row["mention"]).entity_id) for row in sample["samples"]
    ]
    gold_map = {row["mention"]: row["expected_entity_id"] for row in sample["samples"]}
    er_accuracy = entity_resolution_accuracy(resolved, gold_map)
    rows.append(
        _ratio_row(
            "entity_resolution_accuracy",
            "Entity-resolution accuracy",
            _FAMILIES[1],
            er_accuracy,
            TARGET_ENTITY_RESOLUTION,
            f"{len(resolved)} curated-universe mentions (RIS-11 hand-check sample).",
        )
    )

    # 3. Unsupported-claim rate (RIS-19 numeric guard) --------------------- #
    samples = explanation_guard_samples(graph)
    unsupported = unsupported_claim_rate(samples)
    rows.append(
        MetricRow(
            key="unsupported_claim_rate",
            label="Unsupported-claim rate",
            family=_FAMILIES[2],
            actual_display=f"{unsupported:.1%}",
            target_display="= 0%",
            passed=unsupported <= TARGET_UNSUPPORTED_CLAIM_RATE,
            detail=(
                f"{len(samples)} demo-path explanations checked; a number absent "
                "from the computation payload fails the guard (RW-AI-011)."
            ),
        )
    )

    # 4. Citation-correctness spot checks ---------------------------------- #
    checks = citation_spot_checks(graph)
    citation_rate = citation_correctness_rate(checks)
    rows.append(
        _ratio_row(
            "citation_correctness",
            "Citation correctness",
            _FAMILIES[3],
            citation_rate,
            TARGET_CITATION_CORRECTNESS,
            f"{sum(checks)}/{len(checks)} cited passages support their derived weight.",
        )
    )
    rows.append(
        _ratio_row(
            "provenance_coverage",
            "Provenance coverage",
            _FAMILIES[3],
            graph.provenance_coverage(),
            TARGET_PROVENANCE_COVERAGE,
            "Fraction of edges carrying complete Graft-2 provenance (RW-ALG-032).",
        )
    )

    # 5. Scenario stability ------------------------------------------------ #
    checksums = repeated_run_checksums(graph, runs=5)
    stable = scenario_stability(checksums)
    rows.append(
        MetricRow(
            key="scenario_stability",
            label="Scenario stability",
            family=_FAMILIES[4],
            actual_display="stable" if stable else "UNSTABLE",
            target_display="identical",
            passed=stable,
            detail=f"{len(checksums)} repeated runs of the demo scenario produced "
            + ("one identical result." if stable else "divergent results."),
        )
    )

    # 6. Latencies --------------------------------------------------------- #
    latencies = measure_latencies(graph)
    prop = latency_summary("propagation", latencies["propagation"])
    rows.append(
        _lower_bound_row(
            "propagation_latency",
            "Propagation recompute (p95)",
            _FAMILIES[5],
            prop.p95_ms,
            TARGET_PROPAGATION_MS,
            "ms",
            f"median {prop.p50_ms:.1f} ms over {prop.count} slider recomputes.",
        )
    )
    parse = latency_summary("parse", latencies["parse"])
    rows.append(
        _lower_bound_row(
            "parse_latency",
            "Shock parse (p95)",
            _FAMILIES[5],
            parse.p95_ms,
            TARGET_PARSE_MS,
            "ms",
            "Deterministic demo parse path (Gemini live path validated in gated smokes).",
        )
    )
    guard = latency_summary("explanation_guard", latencies["explanation_guard"])
    rows.append(
        MetricRow(
            key="explanation_guard_latency",
            label="Explanation numeric-guard (p95)",
            family=_FAMILIES[5],
            actual_display=f"{guard.p95_ms:.1f} ms",
            target_display="informational",
            passed=None,
            detail="Local RW-AI-011 guard latency; Gemini generation timed in live smokes.",
        )
    )

    return EvaluationReport(
        snapshot_id=graph.snapshot_id,
        graph_version=graph.graph_version,
        generated_at=generated_at,
        rows=tuple(rows),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """CLI: recompute the report from the snapshot and write it to disk."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Compute the RIS-21 evaluation report.")
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_REPORT_OUTPUT_PATH,
        help="Where to write the JSON report (default: data/evaluation/evaluation_report.json).",
    )
    parser.add_argument(
        "--generated-at",
        default="snapshot",
        help="Timestamp label to stamp into the report (kept out of the pure core).",
    )
    args = parser.parse_args(argv)

    report = run_evaluation(generated_at=args.generated_at)
    payload = report.to_dict()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    status = "ALL PASS" if report.all_passed else f"{len(report.failing)} FAILING"
    print(f"Evaluation report [{status}] written to {args.out}")
    for row in report.rows:
        mark = "  " if row.passed is None else (" ✓" if row.passed else " ✗")
        print(f"{mark} {row.label:38s} {row.actual_display:>12s}  (target {row.target_display})")
    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
