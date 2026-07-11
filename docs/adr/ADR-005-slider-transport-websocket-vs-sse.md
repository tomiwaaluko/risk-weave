# ADR-005: Slider Recompute Transport

## Status

Accepted for v1.

## Context

The severity slider must feel live and propagation must recompute within
`RW-NFR-002`. The spec's planned architecture mentions FastAPI plus WebSocket,
but Section 24 left WebSocket versus SSE open.

MDN describes WebSocket as a two-way interactive browser-server session. SSE is
server-to-client push over `EventSource`. Slider recompute is initiated by
client input and returns streamed or latest-result server output, so the
interaction is naturally bidirectional.

## Original Requirement

Choose WebSocket or SSE for live severity-slider recompute without weakening the
`RW-NFR-002` latency requirement.

## Proposed Change

Use a run-scoped WebSocket protocol for slider updates and recompute deltas.

## Reason

The slider loop is bidirectional and sequence-sensitive; one socket gives a
simpler stale-response and latency model than SSE plus separate POST requests.

## Decision

Use a WebSocket endpoint for slider recompute sessions.

Protocol shape:

- client opens one run-scoped socket after scenario confirmation;
- client sends debounced slider updates with monotonically increasing
  `client_sequence`;
- server replies with `client_sequence`, `run_id`, propagation version,
  recompute latency, graph delta, ranked node deltas, and evidence references;
- client ignores stale responses with an older sequence than the latest rendered
  sequence;
- server may send progress/heartbeat messages but must not call Gemini during
  slider recompute.

Use plain HTTP endpoints for initial scenario creation, evidence detail fetches,
and immutable run retrieval. Do not use SSE for the primary slider loop.

## Alternatives Considered

- SSE plus POST slider updates: workable, but splits a single interactive loop
  across two mechanisms and complicates stale-response handling.
- Polling: rejected because it wastes latency budget and makes the demo feel
  less live.
- WebTransport: not needed for v1 and less broadly supported than WebSocket.

## Consequences

The backend must manage connection lifecycle, cancellation/stale sequencing, and
heartbeats. The frontend must debounce slider input and render only the newest
sequence. The propagation payload remains deterministic and run-scoped.

## User And Judging Impact

Users get a live-feeling slider. Judges can inspect recompute latency and see
that the path does not call Gemini during slider updates.

## Security, Data, Cost, And Performance Impact

The WebSocket carries only scenario/run IDs and deterministic recompute payloads;
no secrets and no Gemini API key are exposed to the client. Recompute messages
must be validated and authorized against the run/session.

## Migration Or Rollback

If deployment infrastructure blocks WebSockets, write a superseding ADR for
SSE-plus-POST before changing the architecture.

## Human Approval Required

No.

No MUST-level requirement is weakened by this ADR.

## Affected Requirements

`RW-FR-020`, `RW-FR-021`, `RW-NFR-002`, `RW-SEC-001`, `RW-SEC-003`,
`RW-AI-011`.

## Sources

- MDN WebSocket API: https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API
- MDN Server-sent events: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events
