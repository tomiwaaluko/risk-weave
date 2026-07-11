"use client";

interface SeveritySliderProps {
  severity: number;
  onSeverityChange: (severity: number) => void;
  disabled?: boolean;
}

export default function SeveritySlider({
  severity,
  onSeverityChange,
  disabled = false,
}: SeveritySliderProps) {
  return (
    <div className="severity-slider" id="severity-slider">
      <label htmlFor="severity-input" className="severity-label">
        Severity
      </label>
      <div className="severity-track-container">
        <input
          type="range"
          id="severity-input"
          min={0}
          max={100}
          step={1}
          value={Math.round(severity * 100)}
          disabled={disabled}
          onChange={(e) => onSeverityChange(Number(e.target.value) / 100)}
          className="severity-input"
        />
        <span className="severity-value">{(severity * 100).toFixed(0)}%</span>
      </div>
    </div>
  );
}
