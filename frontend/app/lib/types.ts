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
  };
  case: null | RiskCase;
  ai_result?: unknown;
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
