export type Role = "CUSTOMER" | "ANALYST" | "SUPERVISOR" | "ADMIN";

export interface AuthUser {
  id: string;
  first_name: string;
  last_name: string;
  email: string | null;
  gsm: string | null;
  role: Role;
}

export interface AuthSession {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: AuthUser;
}

export interface ApiEnvelope<T> {
  success: boolean;
  data: T;
  error: null | {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

export interface AIScoringResult {
  status?: "SCORED" | "UNAVAILABLE" | string;
  risk_score: string | number | null;
  fraud_type: string;
  risk_level: string;
  decision: string;
  risk_reasons?: string[];
  model_version: string | null;
  assigned_analyst_id?: string | null;
  assignment_status?: string;
  message?: string;
}

export interface CaseHistoryEntry {
  id: string;
  from_status: string | null;
  to_status: string;
  actor_user_id: string | null;
  note: string | null;
  created_at: string;
}

export interface GamificationProfile {
  analyst_id: string;
  total_points: number;
  level: string;
  badges: string[];
  resolved_cases: number;
  average_points_per_case: number;
  daily_rank: number | null;
  weekly_rank: number | null;
  recent_score_entries: Array<{ points: number; reason: string; occurred_at: string }>;
}

export interface TransactionItem {
  transaction: {
    id: string;
    transaction_number: string;
    amount: string;
    transaction_type: string;
    recipient: string;
    source_device: string;
    city: string;
    occurred_at: string;
    risk_score: string | null;
    fraud_type: string;
    risk_level: string;
    decision: string;
    ai_status?: string;
    model_version?: string | null;
    risk_reasons?: string[];
  };
  case: null | RiskCase;
  ai_result?: AIScoringResult;
  ai_fallback?: boolean;
}

export interface RiskCase {
  id: string;
  transaction_id: string;
  status: string;
  assigned_analyst_id: string | null;
  decision_note: string | null;
  customer_response: string | null;
  sla_due_at: string;
  sla_remaining_seconds: number | null;
  sla_exceeded: boolean;
  transaction?: TransactionItem["transaction"];
  risk_reasons?: string[];
  history?: CaseHistoryEntry[];
  feedback: null | { id: string; rating: number; created_at: string };
}

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
