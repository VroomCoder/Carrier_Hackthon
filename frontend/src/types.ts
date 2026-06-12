export interface MilestoneScore {
  S: number;
  M: number;
  A: number;
  R: number;
  T: number;
}

export interface CalibrationResult {
  scores: MilestoneScore;
  rewritten_goal: string;
  gaps: string[];
  okr_alignment: string;
  policy_references: string[];
  seniority_tier: string;
  role_benchmark: string;
  overall: number;
  milestone_id?: string;
  status?: string;
}

export interface BiasFlag {
  type: string;
  passage: string;
  suggestion: string;
  severity: "high" | "medium" | "low";
}

export interface SynthesisResult {
  synthesis_id?: string;
  commentary: string;
  score: number;
  flags: BiasFlag[];
  policy_references: string[];
  gate_blocked?: boolean;
  gate_reason?: string | null;
  finalised_at?: string | null;
  acknowledged_flags?: string[];
}

export interface BiasCheckResult {
  flags: BiasFlag[];
  score: number;
}

export type FeedbackVisibility = "manager_only" | "shared" | "shared_with_employee";
export type FeedbackType = "continuous" | "peer" | "upward";
export type StructuredFeedbackType =
  | "strength"
  | "development"
  | "project"
  | "behaviour"
  | "general";
export type FeedbackSentiment = "positive" | "constructive" | "neutral";
export type ReviewType = "mid_year" | "year_end";
export type ReviewStatus = "draft" | "submitted" | "locked";

export interface FeedbackEntry {
  id: string;
  entry_id?: string;
  employee_id: string;
  author_employee_id: string;
  author_name: string;
  manager_name?: string;
  feedback_type: FeedbackType | StructuredFeedbackType | string;
  raw_text: string;
  content?: string;
  context?: string;
  sentiment?: FeedbackSentiment;
  tags?: string[];
  review_cycle?: string;
  is_draft?: boolean;
  synthesized_commentary: string | null;
  objectivity_score: number | null;
  visibility: FeedbackVisibility;
  milestone_id: string | null;
  cycle: string;
  created_at: string;
  updated_at: string;
}

export interface FeedbackSummary {
  summary_id: string;
  employee_id: string;
  review_cycle: string;
  review_type: ReviewType;
  content: string;
  entry_count: number;
  themes: string[];
  strengths?: string[];
  development_areas?: string[];
  trajectory?: string;
  notable_pattern?: string | null;
  quality_score?: number;
  confidence?: string;
  generated_at: string;
  status: "draft" | "finalised";
  self_corrections?: number;
}

export interface FeedbackSummaryResult extends FeedbackSummary {
  summary: string;
}

export type AchievementType =
  | "certification"
  | "accomplishment"
  | "training"
  | "award"
  | "project"
  | "other";

export interface EmployeeAchievement {
  achievement_id: string;
  employee_id: string;
  type: AchievementType | string;
  title: string;
  description: string;
  issuer_or_context: string;
  achieved_at: string | null;
  review_cycle: string | null;
  linked_milestone_id: string | null;
  visibility: "self" | "manager" | string;
  source: string;
  created_at: string;
  updated_at: string;
}

export interface FeedbackStats {
  total_entries: number;
  current_cycle_entries: number;
  by_type: Record<string, number>;
  by_sentiment: Record<string, number>;
  by_cycle: Record<string, number>;
  has_summary_this_cycle: boolean;
  last_entry_date: string | null;
}

export interface PerformanceReview {
  id: string;
  employee_id: string;
  cycle: string;
  review_type: ReviewType;
  status: ReviewStatus;
  employee_self_assessment: string;
  manager_summary: string;
  development_areas: string;
  overall_rating: number | null;
  submitted_at: string | null;
  locked_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReviewDraftFromFeedback {
  review_type: ReviewType;
  cycle: string;
  manager_summary: string;
  development_areas: string;
  feedback_entries_used: number;
}

export interface CycleStatus {
  cycle: string;
  current_stage_index: number;
  current_stage: string;
  stages: string[];
  milestone_count: number;
  calibrated_count: number;
  goals_required: number;
  goals_complete: boolean;
  suggested_count?: number;
  okr_assigned_count?: number;
  feedback_count: number;
  mid_year_status: ReviewStatus | null;
  year_end_status: ReviewStatus | null;
  review_completeness: number;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export type UserRole = "employee" | "admin";

export interface AuthUser {
  user_id: string;
  role: UserRole;
  is_manager: boolean;
  display_name: string;
  employee_id?: string | null;
}

export interface Milestone {
  id: string;
  employee_id: string;
  raw_goal: string;
  smart_goal: string | null;
  overall_score: number;
  status: "suggested" | "calibrated" | "needs_work" | string;
  seniority_tier?: string;
  created_at?: string;
  updated_at?: string;
  employee_self_assessment?: string;
  self_assessment_updated_at?: string | null;
  source_okr_id?: string | null;
  suggested_by?: string | null;
  manager_suggestion?: string;
  linked_okr_id?: string | null;
}

export interface OkrAssignment {
  id: string;
  employee_id: string;
  okr_id: string;
  assigned_by: string;
  cycle: string;
  created_at: string;
  title: string;
  description: string;
  category: string;
  owner: string;
}

export interface Employee {
  employee_id: string;
  name: string;
  email?: string;
  department: string;
  sub_department: string;
  job_title: string;
  grade?: string;
  manager_id?: string;
  manager_name?: string;
  location?: string;
  work_mode?: string;
  employment_type?: string;
  leave_balance?: number;
}

export interface OKRDoc {
  okr_id: string;
  title: string;
  description: string;
  category: string;
  owner: string;
  cycle: string;
  status: "active" | "archived";
  created_at: string;
  updated_at: string;
}

export interface OrgNode {
  node_id: string;
  department: string;
  business_unit: string;
  designation: string;
  seniority_tier: string;
  focus_description: string;
  okr_categories: string;
  status: "active" | "archived";
  created_at: string;
  updated_at: string;
}

export interface RoleContext {
  designation: string;
  department: string;
  business_unit: string;
  seniority_tier: string;
  focus_description: string;
  okr_categories: string[];
  valid: boolean;
}

export interface PolicyDoc {
  doc_id: string;
  filename: string;
  title: string;
  description: string;
  chunk_count: number;
  status: "active" | "archived";
  uploaded_at: string;
  updated_at: string;
}

export interface PolicySearchResult {
  text: string;
  section_title: string;
  doc_title: string;
  filename: string;
  doc_id: string;
  chunk_index: number;
}

export type ToastType = "success" | "error" | "info" | "warning";

export interface Toast {
  id: string;
  message: string;
  type: ToastType;
}

export interface HealthData {
  status: string;
  employees_indexed: number;
  active_okrs: number;
  active_org_nodes: number;
  policy_docs: number;
  policy_chunks: number;
  llm_provider?: string;
  llm_ok?: boolean;
  llm_model_ready?: boolean;
  llm_detail?: string;
  model: string;
  llm_url?: string;
  ollama_url: string;
  ollama_ok?: boolean;
  ollama_model_ready?: boolean;
  ollama_models?: string[];
}

export type RAGStatus = "on_track" | "needs_attention" | "at_risk";

export type Trajectory =
  | "improving"
  | "steady"
  | "declining"
  | "insufficient_data";

export interface EmployeeHealthScore {
  score_id: string;
  employee_id: string;
  composite_score: number;
  rag_status: RAGStatus;
  goal_quality_score: number;
  checkin_score: number;
  feedback_score: number;
  review_readiness: number;
  trajectory_score: number;
  goals_total: number;
  goals_calibrated: number;
  goals_needs_work: number;
  avg_smart_score: number;
  last_goal_updated: string | null;
  last_checkin_date: string | null;
  days_since_checkin: number | null;
  total_sessions: number;
  feedback_count_cycle: number;
  feedback_count_total: number;
  last_feedback_date: string | null;
  days_since_feedback: number | null;
  sentiment_positive: number;
  sentiment_constructive: number;
  sentiment_neutral: number;
  has_balanced_feedback: boolean;
  has_calibrated_goal: boolean;
  has_feedback_cycle: boolean;
  has_summary: boolean;
  had_recent_checkin: boolean;
  trajectory: Trajectory;
  at_risk_reasons: string[];
  computed_at: string;
  review_cycle: string;
}

export interface EmployeeHealthCard extends EmployeeHealthScore {
  name: string;
  job_title: string;
  department: string;
  sub_department: string;
  grade: string;
  location: string;
  work_mode: string;
  last_feedback_snippet?: string | null;
}

export interface TeamHealthSummary {
  total: number;
  on_track: number;
  needs_attention: number;
  at_risk: number;
  avg_score: number;
  avg_goal_quality: number;
  avg_feedback_coverage: number;
  avg_checkin_recency: number;
}

export interface HealthAlert {
  employee_id: string;
  name: string;
  rag_status: RAGStatus;
  composite_score: number;
  at_risk_reasons: string[];
  suggested_actions: string[];
}

export interface TeamHealthResponse {
  team_summary: TeamHealthSummary;
  employees: EmployeeHealthCard[];
  alerts: HealthAlert[];
  last_computed: string | null;
}

export interface EmployeeHealthDetail extends EmployeeHealthScore {
  name?: string;
  job_title?: string;
  department?: string;
  grade?: string;
  milestones?: Milestone[];
  feedback_entries?: FeedbackEntry[];
  feedback_summary?: FeedbackSummary | null;
}

export type AgentStepType = "handoff" | "search" | "load" | "llm" | "result" | "decision" | "confidence";

export interface AgentRationale {
  decision: string;
  explanation: string;
  sources: string[];
}

export interface AgentActivityStep {
  type: AgentStepType | string;
  from?: string;
  to?: string;
  detail?: string;
  collection?: string;
  query?: string;
  hit_count?: number;
  hits?: string[];
  resource?: string;
  source?: string;
  count?: number;
  model?: string;
  reason?: string;
}

export interface AgentActivityEvent {
  id: string;
  agent: string;
  agent_label: string;
  employee_id: string | null;
  workflow_id?: string | null;
  status: string;
  summary: string;
  duration_ms: number;
  confidence_level?: string | null;
  confidence_score?: number | null;
  confidence_reason?: string | null;
  rationale?: AgentRationale | null;
  steps: AgentActivityStep[];
  created_at: string;
}

export interface TransparencyCoverage {
  window_days: number;
  employee_id: string | null;
  total_runs: number;
  confidence_coverage_pct: number;
  rationale_coverage_pct: number;
  agents: Array<{
    agent: string;
    total_runs: number;
    with_confidence: number;
    with_rationale: number;
    confidence_pct: number;
    rationale_pct: number;
  }>;
}
