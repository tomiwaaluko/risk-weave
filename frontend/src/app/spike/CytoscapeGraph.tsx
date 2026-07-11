"use client";

import { useCallback, useEffect, useRef } from "react";
import cytoscape, { type Core, type EventObject } from "cytoscape";
import type { SpikeNode, SpikeEdge, SliderUpdate } from "./types";

// ---------------------------------------------------------------------------
// Node type → color mapping (curated palette)
// ---------------------------------------------------------------------------

const TYPE_COLORS: Record<string, string> = {
  bank: "#3b82f6", // blue
  company: "#8b5cf6", // violet
  reit: "#ec4899", // pink
  security: "#f59e0b", // amber
  commodity: "#10b981", // emerald
  geography: "#06b6d4", // cyan
  sector: "#f97316", // orange
};

const DEFAULT_COLOR = "#6b7280"; // gray

// ---------------------------------------------------------------------------
// Cytoscape stylesheet
// ---------------------------------------------------------------------------

type StylesheetRule = {
  selector: string;
  style: Record<string, string | number>;
};

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
      "border-width": 0,
      "overlay-opacity": 0,
      "transition-property":
        "width, height, background-color, border-width, border-color",
      "transition-duration": 150,
    },
  },
  {
    selector: "node:selected",
    style: {
      "border-width": 3,
      "border-color": "#facc15",
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
    selector: "edge:selected",
    style: {
      opacity: 1,
      "line-color": "#facc15",
      "target-arrow-color": "#facc15",
      width: 3,
    },
  },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface CytoscapeGraphProps {
  nodes: SpikeNode[];
  edges: SpikeEdge[];
  shockedNodeIds: Set<string>;
  sliderUpdate: SliderUpdate | null;
  onSelectNode: (nodeId: string) => void;
  onSelectEdge: (edgeId: string) => void;
  onDeselect: () => void;
}

export default function CytoscapeGraph({
  nodes,
  edges,
  shockedNodeIds,
  sliderUpdate,
  onSelectNode,
  onSelectEdge,
  onDeselect,
}: CytoscapeGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);

  // -----------------------------------------------------------------------
  // Initialize Cytoscape
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (!containerRef.current || nodes.length === 0) return;

    const cyNodes = nodes.map((n) => ({
      data: {
        id: n.node_id,
        label: n.name,
        nodeType: n.node_type,
        color: TYPE_COLORS[n.node_type] ?? DEFAULT_COLOR,
        size: 20,
      },
    }));

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

    // Mark shocked nodes.
    shockedNodeIds.forEach((id) => {
      cy.getElementById(id).addClass("shocked");
    });

    cyRef.current = cy;

    // Event handlers.
    cy.on("tap", "node", (evt: EventObject) => {
      onSelectNode(evt.target.id());
    });
    cy.on("tap", "edge", (evt: EventObject) => {
      onSelectEdge(evt.target.id());
    });
    cy.on("tap", (evt: EventObject) => {
      if (evt.target === cy) {
        onDeselect();
      }
    });

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
    // We only rebuild the graph when the topology changes, not on callback changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges]);

  // -----------------------------------------------------------------------
  // Apply propagation results (batch update for performance)
  // -----------------------------------------------------------------------
  const applyUpdate = useCallback((update: SliderUpdate) => {
    const cy = cyRef.current;
    if (!cy) return;

    cy.batch(() => {
      // Reset all nodes to base size.
      cy.nodes().forEach((node) => {
        node.data("size", 16);
      });

      // Scale impacted nodes by risk score.
      for (const [nodeId, impact] of Object.entries(update.impacts)) {
        const node = cy.getElementById(nodeId);
        if (node.length === 0) continue;

        const score = impact.risk_score;
        const size = 16 + (score / 100) * 40; // 16–56px
        node.data("size", size);

        // Tint node color by impact intensity.
        const baseColor = TYPE_COLORS[node.data("nodeType")] ?? DEFAULT_COLOR;
        if (score > 50) {
          node.data("color", blendToRed(baseColor, (score - 50) / 50));
        } else {
          node.data("color", baseColor);
        }
      }

      // Update edge styling based on whether their targets are impacted.
      cy.edges().forEach((edge) => {
        const targetId = edge.data("target");
        const impact = update.impacts[targetId];
        if (impact && impact.risk_score > 20) {
          const intensity = Math.min(impact.risk_score / 100, 1);
          edge.data("edgeColor", `rgba(239, 68, 68, ${0.3 + intensity * 0.7})`);
          edge.data("edgeWidth", 1 + intensity * 4);
        } else {
          const w = edge.data("weight") ?? 0.5;
          edge.data("edgeColor", `rgba(148, 163, 184, ${0.3 + w * 0.5})`);
          edge.data("edgeWidth", Math.max(0.5, w * 3));
        }
      });
    });
  }, []);

  useEffect(() => {
    if (sliderUpdate) {
      applyUpdate(sliderUpdate);
    }
  }, [sliderUpdate, applyUpdate]);

  return (
    <div
      ref={containerRef}
      id="cytoscape-container"
      style={{
        width: "100%",
        height: "100%",
        background: "#0f172a",
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Linearly blend a hex color toward red (#ef4444) by factor t in [0, 1]. */
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
