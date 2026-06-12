import { useEffect, useMemo, useState } from "react";
import { ArrowRight, ChevronRight } from "lucide-react";
import { apiFetch } from "../hooks/api";
import type {
  CycleStatus,
  Employee,
  FeedbackEntry,
  FeedbackStats,
  HealthData,
  Milestone,
  OKRDoc,
  RoleContext,
  TeamHealthSummary,
} from "../types";
import { aiNotReady, aiUnavailableMessage } from "../utils/aiHealth";
import { REQUIRED_GOAL_COUNT, canManageEmployeeGoals } from "../utils/goals";
import { canLogFeedbackForEmployee } from "../utils/feedback";

interface Props {
  activeEmployee: Employee | null;
  setActivePanel: (panel: string) => void;
  reviseMilestone?: (milestone: Milestone) => void;
  user?: { role?: string; is_manager?: boolean; employee_id?: string | null };
  directReports?: Employee[];
}

const tierColors: Record<string, string> = {
  junior: "bg-gray-100 text-gray-700",
  mid: "bg-blue-100 text-blue-700",
  senior: "bg-brand-100 text-brand-700",
  lead: "bg-purple-100 text-purple-700",
  director: "bg-amber-100 text-amber-700",
};

export default function Dashboard({
  activeEmployee,
  setActivePanel,
  reviseMilestone,
  user,
  directReports = [],
}: Props) {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [profile, setProfile] = useState<Employee | null>(null);
  const [roleContext, setRoleContext] = useState<RoleContext | null>(null);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [okrs, setOkrs] = useState<OKRDoc[]>([]);
  const [cycleStatus, setCycleStatus] = useState<CycleStatus | null>(null);
  const [recentFeedback, setRecentFeedback] = useState<FeedbackEntry[]>([]);
  const [feedbackStats, setFeedbackStats] = useState<FeedbackStats | null>(null);
  const [teamHealthTeaser, setTeamHealthTeaser] = useState<TeamHealthSummary | null>(null);

  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!activeEmployee?.employee_id) {
      setProfile(null);
      setRoleContext(null);
      setMilestones([]);
      setCycleStatus(null);
      setRecentFeedback([]);
      setFeedbackStats(null);
      return;
    }

    const empId = activeEmployee.employee_id;

    apiFetch(`/api/employees/${empId}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setProfile(data ?? activeEmployee))
      .catch(() => setProfile(activeEmployee));

    apiFetch(
      `/api/org/role-context?department=${encodeURIComponent(activeEmployee.department)}&business_unit=${encodeURIComponent(activeEmployee.sub_department)}&designation=${encodeURIComponent(activeEmployee.job_title)}`
    )
      .then((r) => r.json())
      .then(setRoleContext)
      .catch(() => setRoleContext(null));

    apiFetch(`/api/employees/${empId}/milestones`)
      .then((r) => r.json())
      .then(setMilestones)
      .catch(() => setMilestones([]));

    apiFetch(`/api/employees/${empId}/cycle-status`)
      .then((r) => (r.ok ? r.json() : null))
      .then(setCycleStatus)
      .catch(() => setCycleStatus(null));

    apiFetch(`/api/employees/${empId}/feedback`)
      .then((r) => (r.ok ? r.json() : []))
      .then((items: FeedbackEntry[]) => setRecentFeedback(items.slice(0, 3)))
      .catch(() => setRecentFeedback([]));

    apiFetch(`/api/feedback/stats?employee_id=${encodeURIComponent(empId)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then(setFeedbackStats)
      .catch(() => setFeedbackStats(null));
  }, [activeEmployee]);

  useEffect(() => {
    if (!user?.is_manager || !user.employee_id) {
      setTeamHealthTeaser(null);
      return;
    }
    apiFetch(`/api/team-health/team?manager_id=${encodeURIComponent(user.employee_id)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setTeamHealthTeaser(data?.team_summary ?? null))
      .catch(() => setTeamHealthTeaser(null));
  }, [user?.is_manager, user?.employee_id]);

  useEffect(() => {
    const dept = activeEmployee?.department;
    const url = dept
      ? `/api/okrs?status=active&department=${encodeURIComponent(dept)}`
      : "/api/okrs?status=active";
    apiFetch(url)
      .then((r) => r.json())
      .then(setOkrs)
      .catch(() => setOkrs([]));
  }, [activeEmployee]);

  const relevantOkrs = useMemo(() => {
    if (!roleContext?.okr_categories?.length) return okrs;
    const categories = new Set(roleContext.okr_categories.map((c) => c.trim()));
    const filtered = okrs.filter((okr) => categories.has(okr.category));
    return filtered.length > 0 ? filtered : okrs;
  }, [okrs, roleContext]);

  const calibratedCount =
    cycleStatus?.calibrated_count ?? milestones.filter((m) => m.status === "calibrated").length;
  const goalsRequired = cycleStatus?.goals_required ?? REQUIRED_GOAL_COUNT;
  const goalsComplete = cycleStatus?.goals_complete ?? calibratedCount >= goalsRequired;
  const canManage = canManageEmployeeGoals(user, activeEmployee, directReports);
  const canLogFeedback = canLogFeedbackForEmployee(user, activeEmployee, directReports);
  const isSelf =
    !!activeEmployee &&
    !!user?.employee_id &&
    activeEmployee.employee_id === user.employee_id;
  const suggestedGoals = milestones.filter((m) => m.status === "suggested");
  const reviewCompleteness = cycleStatus?.review_completeness ?? 0;
  const feedbackCount = cycleStatus?.feedback_count ?? recentFeedback.length;
  const cycleFeedbackCount = feedbackStats?.current_cycle_entries ?? feedbackCount;
  const cycleStages = cycleStatus?.stages ?? [
    "Goal Setting",
    "Mid-year Review",
    "Calibration",
    "Year-end Review",
    "Close-out",
  ];
  const currentStage = cycleStatus?.current_stage_index ?? 0;
  const currentStageLabel = cycleStages[currentStage] ?? "Goal Setting";

  const displayEmployee = profile ?? activeEmployee;

  const primaryAction = useMemo(() => {
    if (!displayEmployee) return null;
    if (!goalsComplete || suggestedGoals.length > 0) {
      return {
        label: canManage
          ? "Assign OKRs & calibrate goals"
          : suggestedGoals.length > 0
            ? "Review goal suggestions"
            : "Calibrate your goals",
        panel: "calibrator",
      };
    }
    if (canLogFeedback && cycleFeedbackCount === 0) {
      return { label: "Log continuous feedback", panel: "continuous_feedback" };
    }
    if (reviewCompleteness > 0 && reviewCompleteness < 100) {
      return { label: "Continue performance review", panel: "feedback" };
    }
    return { label: "Open Growth Coach", panel: "coach" };
  }, [
    displayEmployee,
    goalsComplete,
    suggestedGoals.length,
    canManage,
    canLogFeedback,
    cycleFeedbackCount,
    reviewCompleteness,
  ]);

  return (
    <div className="space-y-6 max-w-6xl">
      <div>
        <h1 className="page-title">
          {displayEmployee ? `Welcome, ${displayEmployee.name}` : "Dashboard"}
        </h1>
        {displayEmployee && (
          <p className="text-sm text-gray-500 mt-1">
            {displayEmployee.job_title} · {displayEmployee.department} /{" "}
            {displayEmployee.sub_department}
            {displayEmployee.location ? ` · ${displayEmployee.location}` : ""}
          </p>
        )}
      </div>

      {health && aiNotReady(health) && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-800">
          <p className="font-medium">
            AI unavailable
            {health.llm_provider === "gemini"
              ? " (Gemini)"
              : health.llm_provider === "ollama"
                ? " (Ollama)"
                : ""}
          </p>
          <p className="mt-1">{aiUnavailableMessage(health)}</p>
        </div>
      )}

      {displayEmployee && (
        <>
          <section aria-label="Cycle overview">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <MetricCard
                label="Goals calibrated"
                value={`${calibratedCount} / ${goalsRequired}`}
                hint={
                  goalsComplete
                    ? "Goal setting complete"
                    : `${Math.max(0, goalsRequired - calibratedCount)} more required`
                }
                highlight={goalsComplete ? "teal" : "amber"}
              />
              <MetricCard
                label="Feedback this cycle"
                value={String(cycleFeedbackCount)}
                hint={
                  feedbackStats?.last_entry_date
                    ? `Last: ${formatRelativeDate(feedbackStats.last_entry_date)}`
                    : "No entries yet"
                }
                highlight={cycleFeedbackCount > 0 ? "teal" : "amber"}
              />
              <MetricCard
                label="Review completeness"
                value={reviewCompleteness > 0 ? `${reviewCompleteness}%` : "—"}
                hint={
                  cycleStatus?.mid_year_status
                    ? `Mid-year: ${cycleStatus.mid_year_status}`
                    : undefined
                }
                highlight={reviewCompleteness >= 100 ? "teal" : "neutral"}
              />
              <MetricCard
                label="Current stage"
                value={currentStageLabel}
                hint={cycleStatus?.cycle}
                highlight="teal"
              />
            </div>

            {primaryAction && (
              <button
                type="button"
                onClick={() => setActivePanel(primaryAction.panel)}
                className="mt-3 inline-flex items-center gap-2 text-sm font-medium text-white bg-brand-500 hover:bg-brand-600 px-4 py-2 rounded-lg transition-colors"
              >
                {primaryAction.label}
                <ArrowRight className="w-4 h-4" />
              </button>
            )}
          </section>

          {user?.is_manager && user.employee_id && teamHealthTeaser && teamHealthTeaser.total > 0 && (
            <button
              type="button"
              onClick={() => setActivePanel("team_health")}
              className="w-full bg-gradient-to-r from-brand-50 to-white border border-brand-100 rounded-xl p-4 text-left hover:border-brand-200 transition-colors"
            >
              <p className="text-sm font-medium text-gray-800 mb-2">Your team health</p>
              <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-sm text-gray-600">
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                  {teamHealthTeaser.on_track} on track
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-amber-500" />
                  {teamHealthTeaser.needs_attention} need attention
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
                  {teamHealthTeaser.at_risk} at risk
                </span>
                <span className="text-brand-600 text-xs flex items-center gap-0.5 ml-auto">
                  View team health <ChevronRight className="w-3.5 h-3.5" />
                </span>
              </div>
            </button>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
            <div className="lg:col-span-2 space-y-4">
              <SectionLabel title="Your cycle" />

              <Panel title="Performance cycle" action={cycleStatus?.cycle}>
                <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
                  {cycleStages.map((stage, i) => (
                    <div key={stage} className="flex items-center gap-1.5 shrink-0">
                      <div
                        className={`text-center py-2 px-2.5 rounded-lg text-xs font-medium whitespace-nowrap ${
                          i === currentStage
                            ? "bg-brand-400 text-white"
                            : i < currentStage
                              ? "bg-brand-50 text-brand-600"
                              : "bg-gray-100 text-gray-500"
                        }`}
                      >
                        {stage}
                      </div>
                      {i < cycleStages.length - 1 && (
                        <div
                          className={`w-3 h-0.5 shrink-0 ${i < currentStage ? "bg-brand-400" : "bg-gray-200"}`}
                        />
                      )}
                    </div>
                  ))}
                </div>
                {cycleStatus && (
                  <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-xs text-gray-500">
                    {cycleStatus.okr_assigned_count != null && (
                      <span>
                        OKRs assigned: {cycleStatus.okr_assigned_count} / {goalsRequired}
                      </span>
                    )}
                    {cycleStatus.mid_year_status && (
                      <span>Mid-year: {cycleStatus.mid_year_status}</span>
                    )}
                    {cycleStatus.year_end_status && (
                      <span>Year-end: {cycleStatus.year_end_status}</span>
                    )}
                  </div>
                )}
              </Panel>

              <Panel
                title={displayEmployee ? `${displayEmployee.name}'s goals` : "Goals"}
                linkLabel={canManage ? "OKRs & goals" : undefined}
                onLink={() => setActivePanel("calibrator")}
              >
                {milestones.length === 0 ? (
                  <EmptyBlock
                    message={
                      canManage
                        ? "Assign OKRs and suggest goals for this employee."
                        : suggestedGoals.length > 0
                          ? `${suggestedGoals.length} goal suggestion(s) awaiting your review.`
                          : "Your manager has not suggested goals yet."
                    }
                    actionLabel={
                      canManage
                        ? "Assign OKRs & suggest goals"
                        : isSelf && suggestedGoals.length > 0
                          ? "Review suggestions"
                          : undefined
                    }
                    onAction={
                      canManage || (isSelf && suggestedGoals.length > 0)
                        ? () => setActivePanel("calibrator")
                        : undefined
                    }
                  />
                ) : (
                  <div className="space-y-2">
                    {milestones.map((m) => (
                      <div
                        key={m.id}
                        className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0"
                      >
                        <div className="flex-1 min-w-0 pr-3">
                          <span className="text-sm text-gray-700 block truncate">
                            {m.smart_goal?.trim() || m.raw_goal}
                          </span>
                          {m.overall_score > 0 && (
                            <span className="text-xs text-gray-400">Score: {m.overall_score}</span>
                          )}
                          {m.employee_self_assessment?.trim() && (
                            <span className="text-xs text-brand-600 block mt-0.5">
                              Self-assessment submitted
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          <span
                            className={`text-xs px-2 py-0.5 rounded-full ${
                              m.status === "calibrated"
                                ? "bg-brand-50 text-brand-600"
                                : m.status === "suggested"
                                  ? "bg-blue-50 text-blue-600"
                                  : "bg-amber-50 text-amber-600"
                            }`}
                          >
                            {m.status === "calibrated"
                              ? "Calibrated"
                              : m.status === "suggested"
                                ? "Suggested"
                                : "Needs work"}
                          </span>
                          {reviseMilestone &&
                            (canManage || (isSelf && m.status === "needs_work")) && (
                              <button
                                onClick={() => reviseMilestone(m)}
                                className="text-xs text-brand-600 hover:text-brand-700 px-2 py-0.5 rounded border border-brand-200 hover:bg-brand-50"
                              >
                                {m.status === "needs_work" ? "Revise" : "Edit"}
                              </button>
                            )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Panel>

              <Panel
                title="Recent feedback"
                linkLabel="View all"
                onLink={() => setActivePanel("feedback")}
              >
                {recentFeedback.length === 0 ? (
                  <EmptyBlock
                    message={
                      canLogFeedback
                        ? "No feedback captured yet."
                        : "No feedback shared with you yet."
                    }
                    actionLabel={canLogFeedback ? "Log feedback" : undefined}
                    onAction={
                      canLogFeedback ? () => setActivePanel("continuous_feedback") : undefined
                    }
                  />
                ) : (
                  <div className="space-y-2">
                    {recentFeedback.map((fb) => (
                      <div key={fb.id} className="py-2 border-b border-gray-100 last:border-0">
                        <div className="flex items-center gap-2 text-xs text-gray-400 mb-1">
                          <span>{fb.author_name}</span>
                          {fb.visibility === "shared" && (
                            <span className="bg-brand-50 text-brand-600 px-1.5 py-0.5 rounded">
                              Shared
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-gray-700 line-clamp-2">{fb.raw_text}</p>
                      </div>
                    ))}
                  </div>
                )}
              </Panel>
            </div>

            <div className="space-y-4">
              <SectionLabel title="About you" />

              <Panel title="Profile">
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <ProfileField label="Employee ID" value={displayEmployee.employee_id} />
                  <ProfileField label="Grade" value={displayEmployee.grade ?? "—"} />
                  <ProfileField label="Work mode" value={displayEmployee.work_mode ?? "—"} />
                  <ProfileField label="Manager" value={displayEmployee.manager_name ?? "—"} />
                </div>
              </Panel>

              {roleContext && (
                <Panel title="Role insight">
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-gray-500 text-sm">{roleContext.focus_description}</p>
                    <span
                      className={`text-xs px-2 py-1 rounded-full font-medium flex-shrink-0 ${
                        tierColors[roleContext.seniority_tier] ?? tierColors.mid
                      }`}
                    >
                      {roleContext.seniority_tier}
                    </span>
                  </div>
                  {(roleContext.okr_categories ?? []).length > 0 && (
                    <div className="flex gap-2 mt-3 flex-wrap">
                      {roleContext.okr_categories.map((cat) => (
                        <span
                          key={cat}
                          className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded-full"
                        >
                          {cat}
                        </span>
                      ))}
                    </div>
                  )}
                </Panel>
              )}

              <Panel
                title={
                  displayEmployee
                    ? `OKRs · ${displayEmployee.department}`
                    : "Relevant OKRs"
                }
                linkLabel={user?.role === "admin" ? "Manage" : undefined}
                onLink={user?.role === "admin" ? () => setActivePanel("okrs") : undefined}
              >
                {relevantOkrs.length === 0 ? (
                  <p className="text-sm text-gray-400 py-2">No active OKRs for this department.</p>
                ) : (
                  <div className="space-y-2">
                    {relevantOkrs.slice(0, 5).map((okr) => (
                      <div key={okr.okr_id} className="py-1.5 border-b border-gray-50 last:border-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-xs bg-brand-50 text-brand-600 px-2 py-0.5 rounded-full">
                            {okr.category}
                          </span>
                          {okr.owner && (
                            <span className="text-xs text-gray-400">{okr.owner}</span>
                          )}
                        </div>
                        <p className="text-sm text-gray-700 mt-1">{okr.title}</p>
                      </div>
                    ))}
                  </div>
                )}
              </Panel>
            </div>
          </div>
        </>
      )}

      {!displayEmployee && user?.role === "admin" && (
        <div className="bg-white border border-dashed border-gray-300 rounded-xl p-8 text-center">
          <p className="text-gray-500 text-sm">
            Select an employee from Employee Lookup to view their dashboard.
          </p>
          <button
            onClick={() => setActivePanel("employees")}
            className="mt-3 text-brand-600 text-sm hover:underline"
          >
            Find employee →
          </button>
        </div>
      )}
    </div>
  );
}

function SectionLabel({ title }: { title: string }) {
  return (
    <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">{title}</p>
  );
}

function Panel({
  title,
  action,
  linkLabel,
  onLink,
  children,
}: {
  title: string;
  action?: string;
  linkLabel?: string;
  onLink?: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5">
      <div className="flex items-center justify-between mb-3 gap-2">
        <h2 className="text-sm font-medium text-gray-700">{title}</h2>
        <div className="flex items-center gap-2 shrink-0">
          {action && <span className="text-xs text-gray-400">{action}</span>}
          {linkLabel && onLink && (
            <button onClick={onLink} className="text-brand-500 text-xs hover:underline">
              {linkLabel} →
            </button>
          )}
        </div>
      </div>
      {children}
    </div>
  );
}

function EmptyBlock({
  message,
  actionLabel,
  onAction,
}: {
  message: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="py-4 text-center">
      <p className="text-sm text-gray-400">{message}</p>
      {actionLabel && onAction && (
        <button onClick={onAction} className="mt-2 text-brand-500 text-sm hover:underline">
          {actionLabel} →
        </button>
      )}
    </div>
  );
}

function formatRelativeDate(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso.includes("T") ? iso : iso.replace(" ", "T") + "Z");
  const days = Math.floor((Date.now() - d.getTime()) / 86400000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 14) return `${days}d ago`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function ProfileField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-gray-400 mb-0.5">{label}</p>
      <p className="text-gray-700 font-medium">{value}</p>
    </div>
  );
}

function MetricCard({
  label,
  value,
  hint,
  highlight = "teal",
}: {
  label: string;
  value: string;
  hint?: string;
  highlight?: "teal" | "amber" | "neutral";
}) {
  const valueClass =
    highlight === "amber"
      ? "text-amber-500"
      : highlight === "neutral"
        ? "text-slate-700"
        : "text-brand-600";

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-lg font-semibold leading-tight ${valueClass}`}>{value}</p>
      {hint && <p className="text-xs text-gray-400 mt-1 line-clamp-2">{hint}</p>}
    </div>
  );
}
