"use client";

import { useEffect, useState } from "react";

export default function StatusBar({
  scenario,
  connected,
  state,
  latencyMs,
}: {
  scenario: string;
  connected: boolean;
  state: string;
  latencyMs: number | null;
}) {
  const [time, setTime] = useState("--:--:--");
  useEffect(() => {
    const tick = () =>
      setTime(new Date().toLocaleTimeString("en-US", { hour12: false }));
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <header className="status-bar">
      <div className="status-bar__brand">
        <span className="brand-mark">RW</span>
        <strong>RISKWEAVE</strong>
        <span className="brand-function">FINANCIAL CONTAGION INTELLIGENCE</span>
      </div>
      <div className="status-bar__scenario">
        <span>SCENARIO</span>
        <strong>{scenario}</strong>
      </div>
      <div className="status-bar__right">
        <span className={`status-light ${connected ? "is-live" : ""}`} />
        {connected ? "LIVE" : state.toUpperCase()}
        <span>{latencyMs === null ? "---" : `${latencyMs.toFixed(0)}MS`}</span>
        <time>{time} ET</time>
      </div>
    </header>
  );
}
