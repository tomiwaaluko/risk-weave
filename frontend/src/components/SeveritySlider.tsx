"use client";

import type { CSSProperties } from "react";

export default function SeveritySlider({
  severity,
  onSeverityChange,
  disabled = false,
}: {
  severity: number;
  onSeverityChange: (value: number) => void;
  disabled?: boolean;
}) {
  const value = Math.round(severity * 100);
  return (
    <div className="terminal-slider">
      <div className="terminal-slider__header">
        <label htmlFor="severity-input">SHOCK SEVERITY</label>
        <output>{value.toString().padStart(3, "0")}%</output>
      </div>
      <input
        id="severity-input"
        aria-label="Shock severity"
        type="range"
        min="0"
        max="100"
        value={value}
        disabled={disabled}
        onChange={(event) => onSeverityChange(Number(event.target.value) / 100)}
        style={{ "--slider-value": `${value}%` } as CSSProperties}
      />
      <div className="terminal-slider__scale">
        <span>0 / BASE</span>
        <span>50 / MOD</span>
        <span>100 / MAX</span>
      </div>
    </div>
  );
}
