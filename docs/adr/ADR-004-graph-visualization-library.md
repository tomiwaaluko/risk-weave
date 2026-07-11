# ADR-004: Graph Visualization Library

## Status

Accepted for v1 with a required implementation spike.

## Context

RiskWeave must render an interactive graph with node-click evidence panels and
live severity re-weighting (`RW-FR-020`, `RW-FR-021`) on a curated graph of about
100 to 200 entities. The spec left React Flow versus Cytoscape.js open.

React Flow is strong for React-native node editors, but its own performance
guidance focuses on avoiding unnecessary React re-renders, memoizing components,
and simplifying large node/edge styles. Cytoscape.js is purpose-built for graph
visualization and analysis, and exposes renderer-level performance controls for
large graph styling.

## Original Requirement

Choose React Flow or Cytoscape.js for the 100 to 200 entity interactive graph
while preserving live slider recompute and evidence-panel requirements.

## Proposed Change

Use Cytoscape.js for the main contagion graph and require a 200-node RIS-15
implementation spike before final UI lock-in.

## Reason

The v1 graph is an analytical network, not a node-editor workflow. Cytoscape.js
better matches dense graph rendering while the spike keeps performance honest.

## Decision

Use Cytoscape.js for the main contagion graph. Use React/Next.js for surrounding
panels and controls, but keep graph rendering and graph interactions inside the
Cytoscape component boundary.

Implementation must include a short RIS-15 spike before locking UI details:

- load a synthetic 200-node graph with representative edge density;
- update node and edge classes from recompute results at slider cadence;
- click nodes and edges to open evidence panels;
- verify panning/zooming and recompute updates remain usable on the demo laptop.

If the spike fails the live-slider budget, revisit this ADR before building the
full graph UI.

## Alternatives Considered

- React Flow: rejected as the default because RiskWeave needs dense graph
  exploration more than visual workflow editing, and frequent whole-node/edge
  state updates create more React re-render risk.
- D3-only custom graph: flexible, but too much implementation surface for v1.
- Server-rendered static graph: rejected because it cannot satisfy interactive
  evidence panels and live recompute.

## Consequences

The UI should treat Cytoscape graph state as a rendering layer over backend
propagation results. Evidence panels remain normal React components fed by
selected graph element IDs.

## User And Judging Impact

Users get graph-native panning, zooming, selection, and evidence inspection.
Judges get a spike-backed performance gate before the demo-critical graph ships.

## Security, Data, Cost, And Performance Impact

No security or data-source impact. Performance risk shifts to the implementation
spike and style discipline: avoid expensive labels, animations, gradients, and
unbounded edge styling in the demo graph.

## Migration Or Rollback

If the spike fails, write a superseding ADR choosing React Flow or a custom
renderer before RIS-15 proceeds.

## Human Approval Required

No, unless the spike fails and the team decides to override the result.

No MUST-level requirement is weakened by this ADR.

## Affected Requirements

`RW-FR-017`, `RW-FR-018`, `RW-FR-020`, `RW-FR-021`, `RW-NFR-002`,
`RW-OPS-001`.

## Sources

- React Flow performance guide: https://reactflow.dev/learn/advanced-use/performance
- Cytoscape.js documentation: https://js.cytoscape.org/
