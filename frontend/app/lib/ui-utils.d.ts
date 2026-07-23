export interface ApiErrorLike {
  status?: number;
  code?: string;
  message?: string;
  details?: Record<string, unknown>;
}

export interface CaseSummaryInput {
  status: string;
  assigned_analyst_id?: string | null;
  sla_exceeded?: boolean;
  transaction?: { risk_level?: string } | null;
}

export function apiErrorText(error: unknown, fallback?: string): string;
export function loginErrorText(error: unknown): string;
export function remainingSlaSeconds(dueAt: string, nowMs?: number): number | null;
export function newlyEarnedBadges(previous: string[], current: string[]): string[];
export function summarizeCases(cases: CaseSummaryInput[]): {
  active: number;
  critical: number;
  slaExceeded: number;
  queued: number;
};
export function countBy(values: Array<string | null | undefined>): Array<{ label: string; count: number }>;
export function isUuid(value: string): boolean;
