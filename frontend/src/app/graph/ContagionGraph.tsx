"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import cytoscape, { type Core, type EventObject } from "cytoscape";
import type { SpikeNode, SpikeEdge, SliderUpdate } from "../spike/types";

// ---------------------------------------------------------------------------
// Node type -> color mapping (curated palette)
// ---------------------------------------------------------------------------

export const TYPE_COLORS: Record<string, string> = {
  bank: "#3b82f6",
  company: "#8b5cf6",
  reit: "#ec4899",
  security: "#f59e0b",
  commodity: "#10b981",
  geography: "#06b6d4",
  sector: "#f97316",
};

const DEFAULT_COLOR = "#6b7280";
const STAGE_DELAY_MS = 180;
const MAX_STAGE = 3;

type StylesheetRule = {
  selector: string;
  style: Record<string, string | number>;
};

// Two distinct visual channels (RW-FR-019): fill = scenario impact,
// ring (border) = structural centrality. Selection uses an overlay so it
// never collides with the centrality ring.
const STYLE: StylesheetRule[] = [
  {
    selector: "node",
    style: {
      label: "data(label)",
      "background-color": "data(color)",
      color: "#e2e8f0",
      "font-size": "9px",
      "font-family": "'Inter', 'Segoe UI', system-ui, sans-serif",
      "text-valign": "bottom",
      "text-margin-y": 6,
      "text-outline-color": "#0f172a",
      "text-outline-width": 1.5,
      width: "data(size)",
      height: "data(size)",
      "border-width": "data(centralityWidth)",
      "border-color": "data(centralityColor)",
      "border-opacity": 0.9,
      "overlay-opacity": 0,
      "transition-property":
        "width, height, background-color, border-width, border-color, opacity",
      "transition-duration": 150,
    },
  },
  {
    selector: "node.stage-hidden",
    style: {
      opacity: 0.12,
    },
  },
  {
    selector: "node:selected",
    style: {
      "overlay-color": "#facc15",
      "overlay-opacity": 0.35,
      "overlay-padding": 4,
    },
  },
  {
    selector: "node.focused",
    style: {
      "overlay-color": "#38bdf8",
      "overlay-opacity": 0.4,
      "overlay-padding": 6,
    },
  },
  {
    selector: "node.shocked",
    style: {
      "border-width": 3,
      "border-color": "#ef4444",
      shape: "diamond",
    },
  },
  {
    selector: "edge",
    style: {
      width: "data(edgeWidth)",
      "line-color": "data(edgeColor)",
      "target-arrow-color": "data(edgeColor)",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
      opacity: 0.5,
      "overlay-opacity": 0,
      "transition-property": "line-color, width, opacity",
      "transition-duration": 150,
    },
  },
  {
    selector: "edge.stage-hidden",
    style: {
      opacity: 0.04,
    },
  },
  {
    selector: "edge:selected",
    style: {
      opacity: 1,
      "line-color": "#facc15",
      "target-arrow-color": "#facc15",
      width: 3,
    },
  },
];

interface ContagionGraphProps {
  nodes: SpikeNode[];
  edges: SpikeEdge[];
  shockedNodeIds: Set<string>;
  sliderUpdate: SliderUpdate | null;
  focusNodeId: string | null;
  onSelectNode: (nodeId: string) => void;
  onSelectEdge: (edgeId: string) => void;
  onDeselect: () => void;
}

export default function ContagionGraph({
  nodes,
  edges,
  shockedNodeIds,
  sliderUpdate,
  focusNodeId,
  onSelectNode,
  onSelectEdge,
  onDeselect,
}: ContagionGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const stageTimersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const lastSeverityRef = useRef<number | null>(null);

  // Structural centrality: normalized in+out degree, independent of the
  // scenario shock (RW-FR-019 requires this stay visually distinct).
  const centrality = useMemo(() => {
    const degree = new Map<string, number>();
    for (const n of nodes) degree.set(n.node_id, 0);
    for (const e of edges) {
      degree.set(e.source_id, (degree.get(e.source_id) ?? 0) + 1);
      degree.set(e.target_id, (degree.get(e.target_id) ?? 0) + 1);
    }
    const max = Math.max(1, ...degree.values());
    const normalized = new Map<string, number>();
    for (const [id, d] of degree) normalized.set(id, d / max);
    return normalized;
  }, [nodes, edges]);

  useEffect(() => {
    if (!containerRef.current || nodes.length === 0) return;

    const cyNodes = nodes.map((n) => {
      const c = centrality.get(n.node_id) ?? 0;
      return {
        data: {
          id: n.node_id,
          label: n.name,
          nodeType: n.node_type,
          color: TYPE_COLORS[n.node_type] ?? DEFAULT_COLOR,
          size: 20,
          centrality: c,
          centralityWidth: 1 + c * 4,
          centralityColor: `rgba(56, 189, 248, ${0.25 + c * 0.6})`,
        },
      };
    });

    const cyEdges = edges.map((e) => ({
      data: {
        id: e.edge_id,
        source: e.source_id,
        target: e.target_id,
        weight: e.weight,
        methodId: e.method_id,
        provenanceRef: e.provenance_ref,
        edgeWidth: Math.max(0.5, e.weight * 3),
        edgeColor: `rgba(148, 163, 184, ${0.3 + e.weight * 0.5})`,
      },
    }));

    const cy = cytoscape({
      container: containerRef.current,
      elements: [...cyNodes, ...cyEdges],
      style: STYLE,
      layout: {
        name: "cose",
        animate: false,
        nodeDimensionsIncludeLabels: true,
        idealEdgeLength: 80,
        nodeRepulsion: 8000,
        gravity: 0.25,
        numIter: 300,
        randomize: true,
      } as cytoscape.LayoutOptions,
      minZoom: 0.15,
      maxZoom: 4,
      wheelSensitivity: 0.3,
    });

    shockedNodeIds.forEach((id) => {
      cy.getElementById(id).addClass("shocked");
    });

    cyRef.current = cy;

    cy.on("tap", "node", (evt: EventObject) => onSelectNode(evt.target.id()));
    cy.on("tap", "edge", (evt: EventObject) => onSelectEdge(evt.target.id()));
    cy.on("tap", (evt: EventObject) => {
      if (evt.target === cy) onDeselect();
    });

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
    // Layout is rebuilt only on topology change, per ADR-004 layout stability.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, centrality]);

  const clearStageTimers = useCallback(() => {
    stageTimersRef.current.forEach(clearTimeout);
    stageTimersRef.current = [];
  }, []);

  // Restyles impacted nodes/edges in place (no re-layout) and stages the
  // 1st -> 2nd -> 3rd order reveal on a fresh run.
  const applyUpdate = useCallback(
    (update: SliderUpdate) => {
      const cy = cyRef.current;
      if (!cy) return;

      const isFreshRun = lastSeverityRef.current !== update.severity;
      lastSeverityRef.current = update.severity;
      clearStageTimers();

      // Minimum hop_count reaching each node, used for staged reveal.
      const minHop = new Map<string, number>();
      for (const [nodeId, impact] of Object.entries(update.impacts)) {
        const hop = impact.contributions.reduce(
          (min, c) => Math.min(min, c.hop_count),
          Infinity,
        );
        if (Number.isFinite(hop)) minHop.set(nodeId, hop);
      }

      cy.batch(() => {
        cy.nodes().forEach((node) => {
          node.data("size", 16);
        });

        for (const [nodeId, impact] of Object.entries(update.impacts)) {
          const node = cy.getElementById(nodeId);
          if (node.length === 0) continue;

          const score = impact.risk_score;
          const size = 16 + (score / 100) * 40;
          node.data("size", size);

          const baseColor = TYPE_COLORS[node.data("nodeType")] ?? DEFAULT_COLOR;
          node.data(
            "color",
            score > 50 ? blendToRed(baseColor, (score - 50) / 50) : baseColor,
          );

          if (isFreshRun) {
            const hop = minHop.get(nodeId) ?? 0;
            if (hop > 1) node.addClass("stage-hidden");
          }
        }

        cy.edges().forEach((edge) => {
          const targetId = edge.data("target");
          const impact = update.impacts[targetId];
          if (impact && impact.risk_score > 20) {
            const intensity = Math.min(impact.risk_score / 100, 1);
            edge.data(
              "edgeColor",
              `rgba(239, 68, 68, ${0.3 + intensity * 0.7})`,
            );
            edge.data("edgeWidth", 1 + intensity * 4);
            if (isFreshRun) {
              const hop = minHop.get(targetId) ?? 0;
              if (hop > 1) edge.addClass("stage-hidden");
            }
          } else {
            const w = edge.data("weight") ?? 0.5;
            edge.data("edgeColor", `rgba(148, 163, 184, ${0.3 + w * 0.5})`);
            edge.data("edgeWidth", Math.max(0.5, w * 3));
          }
        });
      });

      if (isFreshRun) {
        for (let stage = 2; stage <= MAX_STAGE; stage++) {
          const timer = setTimeout(
            () => {
              const cyNow = cyRef.current;
              if (!cyNow) return;
              cyNow.batch(() => {
                for (const [nodeId, hop] of minHop) {
                  if (hop === stage) {
                    cyNow.getElementById(nodeId).removeClass("stage-hidden");
                    cyNow
                      .getElementById(nodeId)
                      .connectedEdges()
                      .removeClass("stage-hidden");
                  }
                }
              });
            },
            STAGE_DELAY_MS * (stage - 1),
          );
          stageTimersRef.current.push(timer);
        }
      }
    },
    [clearStageTimers],
  );

  useEffect(() => {
    if (sliderUpdate) applyUpdate(sliderUpdate);
    return clearStageTimers;
  }, [sliderUpdate, applyUpdate, clearStageTimers]);

  // Ranked-sidebar click focuses the node: pan/zoom + halo (RIS-15 sidebar requirement).
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().removeClass("focused");
    if (!focusNodeId) return;
    const node = cy.getElementById(focusNodeId);
    if (node.length === 0) return;
    node.addClass("focused");
    cy.animate(
      { center: { eles: node }, zoom: Math.max(cy.zoom(), 1.2) },
      { duration: 300 },
    );
  }, [focusNodeId]);

  return (
    <div
      ref={containerRef}
      id="contagion-graph-container"
      style={{ width: "100%", height: "100%", background: "#0f172a" }}
    />
  );
}

function blendToRed(hex: string, t: number): string {
  const r1 = parseInt(hex.slice(1, 3), 16);
  const g1 = parseInt(hex.slice(3, 5), 16);
  const b1 = parseInt(hex.slice(5, 7), 16);
  const r2 = 239,
    g2 = 68,
    b2 = 68;
  const r = Math.round(r1 + (r2 - r1) * t);
  const g = Math.round(g1 + (g2 - g1) * t);
  const b = Math.round(b1 + (b2 - b1) * t);
  return `#${r.toString(16).padStart(2, "0")}${g.toString(16).padStart(2, "0")}${b.toString(16).padStart(2, "0")}`;
}
