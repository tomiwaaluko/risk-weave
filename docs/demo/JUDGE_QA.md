# Judge Q&A

## Why isn't this just RAG?

Because Gemini does not generate weights or impacts. It parses intent and
retrieves evidence, while deterministic derivation methods and the propagation
engine produce the numbers shown in the graph.

## How do you prevent hallucinated magnitudes?

The UI only exposes numbers that exist in the frozen bundle or deterministic
recompute payload. Every edge weight is tied to a registered `DER-*` method and
cannot exist without provenance.

## How do you handle cycles?

The propagation engine uses simple-path traversal with a three-hop cap and
rejects paths that revisit a node. That keeps decomposition auditable and avoids
double counting.

## What does the confidence badge mean?

It is extraction or data-quality confidence, not statistical probability. Low
confidence is shown visibly and never changes the underlying deterministic math.

## What if the live demo fails?

Switch to replay mode. The UI labels that state explicitly and serves the
precomputed frozen bundle tied to a snapshot id, graph version, engine version,
prompt version, and seed.

## Is this data live?

No. For the hackathon demo the graph is a reduced, curated fixture with
real-filing-sourced, pre-baked provenance. The live pieces are Gemini parsing
the trusted shock prompt and generating the evidence-bound explanation from the
computed payload. The full live-ingested snapshot freeze is deferred.

## What is the fallback recording for?

It is the last-resort delivery artifact if the room, browser, or network fails.
It must show the same fixture bundle, replay label, provenance drill, and judge
Q&A path as the live script.
