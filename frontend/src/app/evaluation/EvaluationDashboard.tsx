import type { EvaluationReport, MetricRow } from "./types";

/**
 * Presentational evaluation dashboard (RIS-21, demo beat 6 — "not a wrapper").
 *
 * Pure render of a computed report: no fetching, no derivation. Grouped by the
 * six §15 metric families, each row shows target vs actual and a green/red
 * status a judge reads in ~15 seconds. Misses are painted red, never hidden
 * (`RW-SAFE-003` spirit).
 */

function statusChip(passed: boolean | null): { text: string; cls: string } {
  if (passed === null) return { text: "info", cls: "eval-chip eval-chip-info" };
  if (passed) return { text: "PASS", cls: "eval-chip eval-chip-pass" };
  return { text: "MISS", cls: "eval-chip eval-chip-miss" };
}

function rowStateClass(passed: boolean | null): string {
  if (passed === null) return "eval-row eval-row-info";
  return passed ? "eval-row eval-row-pass" : "eval-row eval-row-miss";
}

export default function EvaluationDashboard({
  report,
}: {
  report: EvaluationReport;
}) {
  const scored = report.rows.filter((r) => r.passed !== null);
  const passing = scored.filter((r) => r.passed).length;
  const bannerCls = report.all_passed
    ? "eval-banner eval-banner-pass"
    : "eval-banner eval-banner-miss";

  const byFamily = new Map<string, MetricRow[]>();
  for (const family of report.families) byFamily.set(family, []);
  for (const row of report.rows) {
    const bucket = byFamily.get(row.family) ?? [];
    bucket.push(row);
    byFamily.set(row.family, bucket);
  }

  return (
    <div className="eval-dashboard" id="evaluation-dashboard">
      <div className={bannerCls} id="evaluation-banner">
        <span className="eval-banner-score">
          {passing}/{scored.length}
        </span>
        <span className="eval-banner-text">
          quality checks passing
          {report.all_passed ? "" : " — misses flagged below"}
        </span>
      </div>

      <p className="eval-meta">
        Snapshot <span className="mono">{report.snapshot_id}</span> · graph{" "}
        <span className="mono">v{report.graph_version}</span> · as of{" "}
        <span className="mono">{report.generated_at}</span>
      </p>

      <div className="eval-families">
        {report.families.map((family) => {
          const rows = byFamily.get(family) ?? [];
          if (rows.length === 0) return null;
          return (
            <section className="eval-family" key={family}>
              <h2 className="eval-family-title">{family}</h2>
              <div className="eval-rows">
                {rows.map((row) => {
                  const chip = statusChip(row.passed);
                  return (
                    <article
                      className={rowStateClass(row.passed)}
                      key={row.key}
                      data-metric={row.key}
                    >
                      <div className="eval-row-head">
                        <span className="eval-row-label">{row.label}</span>
                        <span className={chip.cls}>{chip.text}</span>
                      </div>
                      <div className="eval-row-numbers">
                        <span className="eval-actual">{row.actual_display}</span>
                        <span className="eval-target">
                          target {row.target_display}
                        </span>
                      </div>
                      {row.detail && (
                        <p className="eval-detail">{row.detail}</p>
                      )}
                    </article>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
