"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import cytoscape, { type Core, type EventObject } from "cytoscape";
import fcose from "cytoscape-fcose";
import type { SliderUpdate, SpikeEdge, SpikeNode } from "@/app/spike/types";

cytoscape.use(fcose);

export const TYPE_COLORS: Record<string, string> = {
  bank: "#00aaff",
  company: "#9d5cff",
  reit: "#ff2d88",
  commodity: "#00ff88",
  security: "#ffb800",
  sector: "#ff6600",
  geography: "#00e5ff",
};
const DEFAULT_COLOR = "#7b8496";

interface Props {
  nodes: SpikeNode[];
  edges: SpikeEdge[];
  shockedNodeIds: Set<string>;
  sliderUpdate: SliderUpdate | null;
  focusNodeId: string | null;
  visibleNodeIds: Set<string>;
  onSelectNode: (id: string) => void;
  onSelectEdge: (id: string) => void;
  onDeselect: () => void;
}

export default function ContagionGraph({
  nodes,
  edges,
  shockedNodeIds,
  sliderUpdate,
  focusNodeId,
  visibleNodeIds,
  onSelectNode,
  onSelectEdge,
  onDeselect,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const timers = useRef<number[]>([]);
  const degrees = useMemo(() => {
    const map = new Map(nodes.map((node) => [node.node_id, 0]));
    edges.forEach((edge) => {
      map.set(edge.source_id, (map.get(edge.source_id) ?? 0) + 1);
      map.set(edge.target_id, (map.get(edge.target_id) ?? 0) + 1);
    });
    const max = Math.max(1, ...map.values());
    return new Map(Array.from(map, ([id, value]) => [id, value / max]));
  }, [edges, nodes]);

  useEffect(() => {
    if (!containerRef.current) return;
    const elements = [
      ...nodes.map((node) => {
        const degree = degrees.get(node.node_id) ?? 0;
        const color = TYPE_COLORS[node.node_type] ?? DEFAULT_COLOR;
        return {
          data: {
            id: node.node_id,
            label: node.name,
            type: node.node_type,
            color,
            size: 22 + degree * 38,
            degree,
          },
        };
      }),
      ...edges.map((edge) => ({
        data: {
          id: edge.edge_id,
          source: edge.source_id,
          target: edge.target_id,
          weight: edge.weight,
          width: Math.max(0.5, edge.weight * 3),
          confidence: 0.28 + Math.min(1, edge.weight) * 0.42,
        },
      })),
    ];
    const cy = cytoscape({
      container: containerRef.current,
      elements,
      pixelRatio: "auto",
      minZoom: 0.2,
      maxZoom: 3,
      wheelSensitivity: 0.22,
      style: [
        {
          selector: "node",
          style: {
            label: "data(label)",
            width: "data(size)",
            height: "data(size)",
            "background-fill": "radial-gradient",
            "background-gradient-stop-colors": [
              "#ffffff",
              "#00aaff",
              "#050505",
            ],
            "background-gradient-stop-positions": [0, 32, 100],
            "background-opacity": 0.95,
            "border-width": 1.5,
            "border-color": "data(color)",
            "border-opacity": 0.8,
            color: "#aeb5c0",
            "font-family": "JetBrains Mono, monospace",
            "font-size": 9,
            "text-valign": "bottom",
            "text-margin-y": 7,
            "text-outline-color": "#000",
            "text-outline-width": 2,
            "overlay-opacity": 0,
            "transition-property":
              "opacity, width, height, border-width, background-opacity",
            "transition-duration": 180,
          },
        },
        {
          selector: "edge",
          style: {
            width: "data(width)",
            opacity: 0.4,
            "line-color": "#405269",
            "target-arrow-color": "#405269",
            "target-arrow-shape": "triangle-backcurve",
            "arrow-scale": 0.5,
            "curve-style": "unbundled-bezier",
            "control-point-distances": 18,
            "control-point-weights": 0.5,
            "overlay-opacity": 0,
            "transition-property": "opacity, width, line-color",
            "transition-duration": 180,
          },
        },
        { selector: ".dim", style: { opacity: 0.16 } },
        {
          selector: "edge.active",
          style: {
            opacity: 0.88,
            "line-color": "#ff6600",
            "target-arrow-color": "#ff6600",
          },
        },
        {
          selector: "node:selected, node.focused",
          style: {
            "border-width": 4,
            "border-color": "#fff",
            "overlay-color": "#fff",
            "overlay-opacity": 0.12,
            "overlay-padding": 8,
          },
        },
        {
          selector: "node.shocked",
          style: { "border-width": 3, "border-color": "#ff2d55" },
        },
        {
          selector: "node.ripple",
          style: {
            "overlay-color": "#ff6600",
            "overlay-opacity": 0.28,
            "overlay-padding": 18,
          },
        },
      ],
      layout: {
        name: "fcose",
        quality: "proof",
        animate: true,
        animationDuration: 1000,
        randomize: true,
        nodeDimensionsIncludeLabels: true,
        gravity: 0.25,
        idealEdgeLength: 92,
        nodeRepulsion: 6500,
      } as cytoscape.LayoutOptions,
    });
    shockedNodeIds.forEach((id) => cy.getElementById(id).addClass("shocked"));
    cy.edges().forEach((edge) => {
      edge.style("opacity", edge.data("confidence") as number);
    });
    const hover = (event: EventObject) => {
      const node = event.target;
      cy.elements().addClass("dim");
      node.closedNeighborhood().removeClass("dim");
      node.connectedEdges().addClass("active");
    };
    cy.on("mouseover", "node", hover);
    cy.on("mouseout", "node", () => {
      cy.elements().removeClass("dim");
      cy.edges().removeClass("active");
    });
    cy.on("tap", "node", (event) => onSelectNode(event.target.id()));
    cy.on("tap", "edge", (event) => onSelectEdge(event.target.id()));
    cy.on("tap", (event) => {
      if (event.target === cy) onDeselect();
    });
    cyRef.current = cy;
    return () => {
      timers.current.forEach(clearTimeout);
      cy.destroy();
      cyRef.current = null;
    };
  }, [
    degrees,
    edges,
    nodes,
    onDeselect,
    onSelectEdge,
    onSelectNode,
    shockedNodeIds,
  ]);

  const applyUpdate = useCallback((update: SliderUpdate) => {
    const cy = cyRef.current;
    if (!cy) return;
    timers.current.forEach(clearTimeout);
    timers.current = [];
    const hops = new Map<string, number>();
    Object.entries(update.impacts).forEach(([id, impact]) => {
      const hop = Math.min(
        ...impact.contributions.map((path) => path.hop_count),
        0,
      );
      hops.set(id, hop);
    });
    cy.batch(() => {
      cy.nodes().addClass("dim");
      cy.edges().removeClass("active").addClass("dim");
      Object.entries(update.impacts).forEach(([id, impact]) => {
        const node = cy.getElementById(id);
        node.data("size", 22 + Math.min(1, impact.risk_score / 100) * 38);
      });
    });
    [0, 1, 2, 3].forEach((stage) => {
      const timer = window.setTimeout(() => {
        cy.batch(() => {
          hops.forEach((hop, id) => {
            if (hop !== stage) return;
            const node = cy.getElementById(id);
            node.removeClass("dim").addClass("ripple");
            node.connectedEdges().removeClass("dim").addClass("active");
            window.setTimeout(() => node.removeClass("ripple"), 320);
          });
        });
      }, stage * 200);
      timers.current.push(timer);
    });
  }, []);
  useEffect(() => {
    if (sliderUpdate) applyUpdate(sliderUpdate);
  }, [applyUpdate, sliderUpdate]);
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().toggleClass("filtered", false);
    cy.nodes().forEach((node) => {
      node.style("display", visibleNodeIds.has(node.id()) ? "element" : "none");
    });
  }, [visibleNodeIds]);
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().removeClass("focused");
    if (focusNodeId) {
      const node = cy.getElementById(focusNodeId);
      node.addClass("focused");
      cy.animate(
        { center: { eles: node }, zoom: Math.max(1.1, cy.zoom()) },
        { duration: 350 },
      );
    }
  }, [focusNodeId]);
  return (
    <div className="graph-canvas-wrap">
      <div className="graph-bloom" />
      <div
        ref={containerRef}
        className="graph-canvas"
        id="contagion-graph-container"
      />
      <div className="graph-hint">
        SCROLL TO ZOOM · DRAG TO PAN · SELECT NODE FOR INTELLIGENCE
      </div>
    </div>
  );
}
