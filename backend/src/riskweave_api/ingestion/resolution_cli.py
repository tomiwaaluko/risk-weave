from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from riskweave.entity_resolution import GeminiMergeProposal, Resolver
from riskweave.entity_resolution.resolver import append_jsonl

REPO_ROOT = Path(__file__).resolve().parents[4]


def main() -> int:
    parser = argparse.ArgumentParser(description="Review RIS-11 entity-resolution queues")
    parser.add_argument("--universe", type=Path, default=REPO_ROOT / "data/universe/entities.json")
    parser.add_argument("--corrections", type=Path, required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve_parser = subparsers.add_parser("resolve")
    resolve_parser.add_argument("--mentions", type=Path, required=True)
    resolve_parser.add_argument("--proposals", type=Path)
    resolve_parser.add_argument("--audit-log", type=Path, required=True)
    resolve_parser.add_argument("--unresolved-queue", type=Path, required=True)

    apply_parser = subparsers.add_parser("apply-correction")
    apply_parser.add_argument("--input-string", required=True)
    apply_parser.add_argument("--entity-id", required=True)
    apply_parser.add_argument("--reviewer", required=True)
    apply_parser.add_argument("--reason", default="manual review")

    args = parser.parse_args()
    resolver = Resolver.from_universe_file(args.universe, corrections_path=args.corrections)

    if args.command == "apply-correction":
        if args.entity_id not in {entity.id for entity in resolver.entities}:
            parser.error(f"unknown entity id: {args.entity_id}")
        append_jsonl(
            args.corrections,
            [
                {
                    "input_string": args.input_string,
                    "entity_id": args.entity_id,
                    "reviewer": args.reviewer,
                    "reason": args.reason,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            ],
        )
        print(json.dumps({"corrections_appended": 1}, sort_keys=True))
        return 0

    mentions = [line.strip() for line in args.mentions.read_text(encoding="utf-8").splitlines()]
    mentions = [mention for mention in mentions if mention]
    proposals = _load_proposals(args.proposals)
    results, audits, unresolved = resolver.resolve_many(mentions, proposals=proposals)
    append_jsonl(args.audit_log, audits)
    append_jsonl(args.unresolved_queue, unresolved)
    print(
        json.dumps(
            {
                "resolved": sum(1 for result in results if result.entity_id is not None),
                "unresolved": len(unresolved),
                "audit_events": len(audits),
            },
            sort_keys=True,
        )
    )
    return 0


def _load_proposals(path: Path | None) -> list[GeminiMergeProposal]:
    if path is None or not path.exists():
        return []
    proposals = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            proposals.append(GeminiMergeProposal.model_validate_json(line))
    return proposals


if __name__ == "__main__":
    raise SystemExit(main())
