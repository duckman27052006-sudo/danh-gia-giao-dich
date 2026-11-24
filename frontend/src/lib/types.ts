export type Role = "admin" | "analyst" | "viewer";

export interface User {
  id: string;
  full_name: string;
  email: string;
  role: Role;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface CaseBrief {
  id: string;
  code: string;
  status: string;
  priority: string;
  decision: string | null;
}

export interface Transaction {
  id: string;
  external_id: string;
  customer_id: string;
  customer_name: string;
  amount: number;
  currency: string;
  channel: string;
  merchant_name: string;
  merchant_category: string;
  merchant_country: string;
  card_country: string;
  ip_country: string;
  device_id: string;
  occurred_at: string;
  ingested_at: string;
  hour: number;
  is_night: boolean;
  country_mismatch: boolean;
  new_device: boolean;
  velocity_1h: number;
  velocity_24h: number;
  amount_ratio: number;
  distinct_merchants_24d: number;
  account_age_days: number;
  ml_score: number;
  rule_score: number;
  risk_score: number;
  risk_band: string;
  is_flagged: boolean;
  rule_hits: RuleHit[];
  contributions: Contribution[];
  model_version: string;
  is_simulated: boolean;
  case: CaseBrief | null;
}

export interface RuleHit {
  rule_id: string;
  name: string;
  severity: string;
  weight: number;
  category: string;
  conditions: RuleCondition[];
}

export interface Contribution {
  feature: string;
  label: string;
  value: string;
  impact: number;
  direction: "up" | "down";
}

export interface CaseItem {
  id: string;
  code: string;
  priority: "P1" | "P2" | "P3";
  status: "open" | "in_review" | "awaiting_info" | "resolved";
  decision: string | null;
  risk_score: number;
  created_at: string;
  updated_at: string;
  sla_due_at: string | null;
  assignee: User | null;
  transaction: Transaction;
}

export interface Note {
  id: string;
  body: string;
  kind: string;
  created_at: string;
  author: User | null;
}

export interface CaseEvent {
  id: string;
  type: string;
  message: string;
  meta: Record<string, unknown>;
  created_at: string;
  actor: User | null;
}

export interface ExplanationContent {
  summary: string;
  why_flagged: string[];
  normal_comparison: string;
  verification_questions: string[];
  draft_note: string;
  disclaimer: string;
}

export interface Signal {
  type: string;
  label: string;
  detail: string;
  weight: number;
  severity: string;
}

export interface Explanation {
  id: string;
  provider: string;
  model: string;
  content: ExplanationContent;
  signals: Signal[];
  latency_ms: number;
  created_at: string;
}

export interface CaseDetail {
  id: string;
  code: string;
  priority: "P1" | "P2" | "P3";
  status: "open" | "in_review" | "awaiting_info" | "resolved";
  decision: string | null;
  decision_note: string | null;
  risk_score: number;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  sla_due_at: string | null;
  assignee: User | null;
  transaction: Transaction;
  notes: Note[];
  events: CaseEvent[];
  explanations: Explanation[];
  latest_explanation: Explanation | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface RuleCondition {
  field: string;
  op: string;
  value: string | number | boolean | string[];
}

export interface Rule {
  id: string;
  name: string;
  description: string;
  conditions: RuleCondition[];
  weight: number;
  severity: "low" | "medium" | "high";
  category: string;
  enabled: boolean;
  hit_count: number;
  last_hit_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RuleField {
  key: string;
  label: string;
  type: "number" | "bool" | "enum" | "string";
  ops: string[];
  options?: string[];
}

export interface Settings {
  review_threshold: number;
  high_threshold: number;
  ml_weight: number;
  rule_weight: number;
  /** Xác suất ML tối thiểu để model tự gắn cờ (0–1). */
  ml_flag_probability: number;
  /** Tổng điểm rule tối thiểu để rule engine tự gắn cờ (0–100). */
  rule_flag_threshold: number;
  ai_enabled: boolean;
  updated_at: string;
}

export interface ModelInfo {
  version: string;
  trained_at: string;
  algorithm: string;
  auc: number;
  precision: number;
  recall: number;
  samples: number;
  feature_importance: { feature: string; label: string; importance: number }[];
  baseline: Record<string, { mean: number; std: number }>;
}

export interface Summary {
  total_transactions: number;
  flagged_transactions: number;
  total_volume: number;
  fraud_rate: number;
  open_cases: number;
  p1_cases: number;
  unassigned_cases: number;
  confirmed_fraud: number;
  false_positive: number;
  precision: number;
  amount_at_risk: number;
  prevented_amount: number;
  avg_resolution_hours: number;
  today_transactions: number;
  today_flagged: number;
  delta_volume_pct: number;
  model_version: string;
  model_auc: number;
  ai_provider: string;
}

export interface DashboardData {
  summary: Summary;
  trend: { date: string; total: number; flagged: number; confirmed: number; volume: number }[];
  channels: { name: string; value: number; extra: number | null }[];
  categories: { name: string; value: number; extra: number | null }[];
  score_bands: { name: string; value: number }[];
  priority_queue: { name: string; value: number }[];
  recent_alerts: CaseItem[];
  rules_performance: { id: string; name: string; hits: number; weight: number; severity: string; enabled: boolean }[];
}

export interface AuditEntry {
  id: string;
  actor_email: string;
  action: string;
  entity_type: string;
  entity_id: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ip: string;
  created_at: string;
}

export interface CaseStats {
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  open_by_priority: Record<string, number>;
  unassigned: number;
  overdue: number;
  total: number;
}

export interface SystemStatus {
  environment: string;
  ai: { configured: boolean; provider: string; model: string; enabled: boolean };
  demo_mode: boolean;
  model: { version: string; auc: number };
}

export interface LoginResult {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}
