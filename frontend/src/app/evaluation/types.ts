/**
 * Evaluation-dashboard payload (RIS-21, `RW-OPS-001`, spec §15).
 *
 * Mirrors `EvaluationReportOut` served by the backend `/evaluation/report`
 * endpoint. Every value is computed server-side from committed fixtures — the
 * dashboard only renders; it never derives a metric itself.
 */

export interface MetricRow {
  key: string;
  label: string;
  family: string;
  actual_display: string;
  target_display: string;
  /** true = pass, false = miss (painted red), null = informational. */
  passed: boolean | null;
  detail: string;
}

export interface EvaluationReport {
  snapshot_id: string;
  graph_version: string;
  generated_at: string;
  all_passed: boolean;
  families: string[];
  rows: MetricRow[];
}
