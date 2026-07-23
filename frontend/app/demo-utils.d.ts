export interface QuickFill {
  amount: string;
  transaction_type: string;
  recipient: string;
  source_device: string;
  city: string;
  occurred_at: string;
  transaction_frequency_24h: number;
  is_new_device: boolean;
  home_city: string;
}
export function activeVerificationCases<T extends { case?: { status?: string } | null }>(items: T[]): T[];
export function unseenVerificationIds<T extends { case?: { id: string; status?: string } | null }>(items: T[], seenIds: Set<string>): string[];
export function highRiskQuickFill(): QuickFill;
export function normalQuickFill(): QuickFill;
