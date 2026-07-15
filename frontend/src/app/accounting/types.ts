export interface GeminiRollupRow {
  day: string;
  purpose: string;
  model: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export interface GeminiBudgetStatus {
  day: string;
  spent_usd: number;
  soft_threshold_usd: number;
  hard_threshold_usd: number;
  soft_breached: boolean;
  hard_breached: boolean;
}

export interface ProviderUsage {
  ingestion_run_id: number | null;
  provider_usage: Record<string, Record<string, unknown>>;
}
