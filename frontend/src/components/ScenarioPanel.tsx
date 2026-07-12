"use client";

import type { NodeImpact, SpikeNode } from "../app/spike/types";
import SeveritySlider from "./SeveritySlider";

interface Props {
  scenario: string;
  onScenarioChange: (value: string) => void;
  onAnalyze: () => void;
  severity: number;
  onSeverityChange: (value: number) => void;
  disabled: boolean;
  types: string[];
  activeType: string;
  onTypeChange: (value: string) => void;
  nodes: SpikeNode[];
  impacts: Record<string, NodeImpact>;
  selectedNodeId: string | null;
  onSelectNode: (id: string) => void;
}

export default function ScenarioPanel(props: Props) {
  const affected = Object.values(props.impacts).filter(
    (impact) => impact.risk_score > 0,
  ).length;
  const maxScore = Math.max(
    0,
    ...Object.values(props.impacts).map((impact) => impact.risk_score),
  );
  return (
    <aside className="scenario-panel">
      <section className="terminal-section">
        <div className="section-heading">
          <span>01</span>SCENARIO INPUT
        </div>
        <textarea
          aria-label="Shock description"
          value={props.scenario}
          onChange={(event) => props.onScenarioChange(event.target.value)}
        />
        <button
          className="analyze-button"
          type="button"
          onClick={props.onAnalyze}
        >
          <span>▶</span> ANALYZE SHOCK <kbd>↵</kbd>
        </button>
      </section>
      <section className="terminal-section">
        <div className="section-heading">
          <span>02</span>PROPAGATION CONTROL
        </div>
        <SeveritySlider
          severity={props.severity}
          onSeverityChange={props.onSeverityChange}
          disabled={props.disabled}
        />
      </section>
      <section className="terminal-section terminal-section--entities">
        <div className="section-heading">
          <span>03</span>ENTITY UNIVERSE <em>{props.nodes.length}</em>
        </div>
        <div className="filter-strip">
          {["all", ...props.types].map((type) => (
            <button
              className={props.activeType === type ? "active" : ""}
              onClick={() => props.onTypeChange(type)}
              key={type}
            >
              {type.toUpperCase()}
            </button>
          ))}
        </div>
        <div className="entity-list">
          {props.nodes.map((node, index) => {
            const score = props.impacts[node.node_id]?.risk_score;
            return (
              <button
                className={
                  props.selectedNodeId === node.node_id ? "selected" : ""
                }
                onClick={() => props.onSelectNode(node.node_id)}
                key={node.node_id}
              >
                <span>{String(index + 1).padStart(2, "0")}</span>
                <i data-type={node.node_type} />
                <strong>{node.name}</strong>
                <small>{score === undefined ? "--" : score.toFixed(1)}</small>
              </button>
            );
          })}
        </div>
      </section>
      <section className="terminal-section metrics-block">
        <div className="section-heading">
          <span>04</span>RUN METRICS
        </div>
        <dl>
          <div>
            <dt>AFFECTED</dt>
            <dd>{affected}</dd>
          </div>
          <div>
            <dt>MAX IMPACT</dt>
            <dd className="hot">{maxScore.toFixed(1)}</dd>
          </div>
          <div>
            <dt>MODEL</dt>
            <dd>DET/V1</dd>
          </div>
        </dl>
      </section>
    </aside>
  );
}
