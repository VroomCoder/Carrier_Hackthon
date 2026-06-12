import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ChevronDown,
  ChevronUp,
  HeartPulse,
  RefreshCw,
  X,
} from "lucide-react";
import { apiFetch } from "../hooks/api";
import type {
  AuthUser,
  Employee,
  EmployeeHealthCard,
  EmployeeHealthDetail,
  HealthAlert,
  RAGStatus,
  TeamHealthResponse,
  ToastType,
  Trajectory,
} from "../types";

interface Props {
  user: AuthUser;
  selfEmployee: Employee | null;
  directReports: Employee[];
  selectedManagerId: string | null;
  setSelectedManagerId: (id: string | null) => void;
  setActiveEmployee: (emp: Employee | null) => void;
  setActivePanel: (panel: string) => void;
  addToast: (message: string, type?: ToastType) => void;
}

type SortKey = "score" | "name" | "risk";
type FilterKey = "all" | RAGStatus;

function ragDotClass(status: RAGStatus): string {
  if (status === "on_track") return "bg-emerald-500";
  if (status === "needs_attention") return "bg-amber-500";
  return "bg-red-500 rag-pulse";
}

function scoreBarColor(score: number): string {
  if (score >= 70) return "bg-emerald-500";
  if (score >= 40) return "bg-amber-400";
  return "bg-red-400";
}

function dimensionLabel(score: number): string {
  if (score >= 70) return "Strong";
  if (score >= 40) return "Developing";
  return "Needs focus";
}

function trajectoryBadge(traj: Trajectory): { label: string; className: string } {
  const map: Record<Trajectory, { label: string; className: string }> = {
    improving: { label: "↑ Improving", className: "bg-emerald-50 text-emerald-700" },
    steady: { label: "→ Steady", className: "bg-gray-100 text-gray-600" },
    declining: { label: "↓ Watch", className: "bg-amber-50 text-amber-700" },
    insufficient_data: { label: "? Insufficient data", className: "bg-gray-100 text-gray-500" },
  };
  return map[traj] ?? map.insufficient_data;
}

function formatRelative(iso: string | null): string {
  if (!iso) return "never";
  const d = new Date(iso.includes("T") ? iso : iso.replace(" ", "T") + "Z");
  const days = Math.floor((Date.now() - d.getTime()) / 86400000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 14) return `${days}d ago`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function checkinLabel(days: number | null): string {
  if (days === null) return "No check-in";
  if (days === 0) return "Today";
  return `${days}d ago`;
}

export default function ManagerHealthDashboard({
  user,
  selfEmployee,
  directReports: _directReports,
  selectedManagerId,
  setSelectedManagerId,
  setActiveEmployee,
  setActivePanel,
  addToast,
}: Props) {
  const [managerQuery, setManagerQuery] = useState("");
  const [managerResults, setManagerResults] = useState<Employee[]>([]);
  const [data, setData] = useState<TeamHealthResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<FilterKey>("all");
  const [sort, setSort] = useState<SortKey>("risk");
  const [alertsOpen, setAlertsOpen] = useState(true);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EmployeeHealthDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const effectiveManagerId = useMemo(() => {
    if (selectedManagerId) return selectedManagerId;
    if (user.is_manager && user.employee_id) return user.employee_id;
    return null;
  }, [selectedManagerId, user]);

  const managerName = useMemo(() => {
    if (!effectiveManagerId) return "";
    if (selfEmployee?.employee_id === effectiveManagerId) return selfEmployee.name;
    const fromResults = managerResults.find((m) => m.employee_id === effectiveManagerId);
    if (fromResults) return fromResults.name;
    return effectiveManagerId;
  }, [effectiveManagerId, selfEmployee, managerResults]);

  const loadTeam = useCallback(async () => {
    if (!effectiveManagerId) return;
    setLoading(true);
    try {
      const res = await apiFetch(
        `/api/team-health/team?manager_id=${encodeURIComponent(effectiveManagerId)}`
      );
      if (!res.ok) {
        addToast("Failed to load team health", "error");
        return;
      }
      setData(await res.json());
    } catch {
      addToast("Failed to load team health", "error");
    } finally {
      setLoading(false);
    }
  }, [effectiveManagerId, addToast]);

  useEffect(() => {
    loadTeam();
  }, [loadTeam]);

  useEffect(() => {
    if (!managerQuery.trim() || user.role !== "admin") {
      setManagerResults([]);
      return;
    }
    const t = setTimeout(() => {
      apiFetch(`/api/employees?q=${encodeURIComponent(managerQuery)}&limit=20`)
        .then((r) => (r.ok ? r.json() : []))
        .then((rows: Employee[]) => setManagerResults(rows))
        .catch(() => setManagerResults([]));
    }, 300);
    return () => clearTimeout(t);
  }, [managerQuery, user.role]);

  useEffect(() => {
    if (!detailId) {
      setDetail(null);
      return;
    }
    setDetailLoading(true);
    apiFetch(`/api/team-health/employee/${encodeURIComponent(detailId)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false));
  }, [detailId]);

  const refreshScores = async () => {
    if (!effectiveManagerId) return;
    setRefreshing(true);
    try {
      const res = await apiFetch(
        `/api/team-health/refresh?manager_id=${encodeURIComponent(effectiveManagerId)}`,
        { method: "POST" }
      );
      if (res.ok) setData(await res.json());
      else addToast("Refresh failed", "error");
    } finally {
      setRefreshing(false);
    }
  };

  const isHr = user.role === "admin";

  const navigateToEmployee = (card: EmployeeHealthCard, panel: string) => {
    setActiveEmployee({
      employee_id: card.employee_id,
      name: card.name,
      job_title: card.job_title,
      department: card.department,
      sub_department: card.sub_department,
      grade: card.grade,
      location: card.location,
      work_mode: card.work_mode,
    });
    setActivePanel(panel);
  };

  const filteredEmployees = useMemo(() => {
    if (!data) return [];
    let list = [...data.employees];
    if (filter !== "all") list = list.filter((e) => e.rag_status === filter);
    if (sort === "score") list.sort((a, b) => a.composite_score - b.composite_score);
    else if (sort === "name") list.sort((a, b) => a.name.localeCompare(b.name));
    else list.sort((a, b) => a.composite_score - b.composite_score);
    return list;
  }, [data, filter, sort]);

  const summary = data?.team_summary;
  const totalForBar = summary?.total || 1;

  if (detailId && detail) {
    return (
      <DetailDrawer
        detail={detail}
        loading={detailLoading}
        onBack={() => setDetailId(null)}
        onNavigate={(panel) => {
          const card = data?.employees.find((e) => e.employee_id === detailId);
          if (card) navigateToEmployee(card, panel);
        }}
        setActivePanel={setActivePanel}
        isHr={isHr}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="page-title flex items-center gap-2">
            <HeartPulse className="w-7 h-7 text-brand-500" />
            Team health
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Performance cycle health for your direct reports
          </p>
        </div>
      </div>

      {/* Manager selector */}
      <div className="bg-white border border-gray-200 rounded-xl p-4">
        {effectiveManagerId ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-gray-600">
              Showing team of <strong>{managerName}</strong>
            </span>
            {(user.role === "admin" || selectedManagerId) && (
              <button
                type="button"
                onClick={() => setSelectedManagerId(null)}
                className="inline-flex items-center gap-1 text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded-full hover:bg-gray-200"
              >
                View as manager: {managerName} <X className="w-3 h-3" />
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-2">
            <label className="text-sm text-gray-600">Search for a manager…</label>
            <input
              value={managerQuery}
              onChange={(e) => setManagerQuery(e.target.value)}
              placeholder="Manager name or ID"
              className="w-full max-w-md border border-gray-200 rounded-lg px-3 py-2 text-sm"
            />
            {managerResults.length > 0 && (
              <div className="border border-gray-200 rounded-lg divide-y max-w-md">
                {managerResults.map((m) => (
                  <button
                    key={m.employee_id}
                    type="button"
                    onClick={() => {
                      setSelectedManagerId(m.employee_id);
                      setManagerQuery("");
                      setManagerResults([]);
                    }}
                    className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50"
                  >
                    {m.name} · {m.job_title}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {!effectiveManagerId && (
        <p className="text-sm text-gray-500 py-8 text-center">
          Select a manager to view team health, or sign in as a manager.
        </p>
      )}

      {effectiveManagerId && loading && !data && (
        <p className="text-sm text-gray-400 text-center py-12">Loading team health…</p>
      )}

      {effectiveManagerId && data && summary && summary.total === 0 && (
        <p className="text-sm text-gray-500 py-8 text-center">
          No direct reports found for this manager. Check that employee records include manager_id.
        </p>
      )}

      {effectiveManagerId && data && summary && summary.total > 0 && (
        <>
          {/* Summary bar */}
          <div className="bg-white border border-gray-200 rounded-xl p-5 space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <SummaryTile label="Team" value={String(summary.total)} />
              <SummaryTile
                label="On track"
                value={String(summary.on_track)}
                highlight="teal"
                onClick={() => setFilter("on_track")}
              />
              <SummaryTile
                label="Needs attention"
                value={String(summary.needs_attention)}
                highlight="amber"
                onClick={() => setFilter("needs_attention")}
              />
              <SummaryTile
                label="At risk"
                value={String(summary.at_risk)}
                highlight="red"
                onClick={() => setFilter("at_risk")}
              />
              <SummaryTile
                label="Avg health"
                value={`${Math.round(summary.avg_score)} / 100`}
                highlight={
                  summary.avg_score >= 70 ? "teal" : summary.avg_score >= 45 ? "amber" : "red"
                }
              />
            </div>
            <div className="h-3 rounded-full overflow-hidden flex bg-gray-100">
              {summary.on_track > 0 && (
                <div
                  className="bg-emerald-500 h-full"
                  style={{ width: `${(summary.on_track / totalForBar) * 100}%` }}
                  title={`On track: ${summary.on_track}`}
                />
              )}
              {summary.needs_attention > 0 && (
                <div
                  className="bg-amber-400 h-full"
                  style={{ width: `${(summary.needs_attention / totalForBar) * 100}%` }}
                />
              )}
              {summary.at_risk > 0 && (
                <div
                  className="bg-red-400 h-full"
                  style={{ width: `${(summary.at_risk / totalForBar) * 100}%` }}
                />
              )}
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-gray-500">
              <span>
                <span className="inline-block w-2 h-2 rounded-full bg-emerald-500 mr-1" />
                On track ·{" "}
                <span className="inline-block w-2 h-2 rounded-full bg-amber-400 mr-1 ml-2" />
                Needs attention ·{" "}
                <span className="inline-block w-2 h-2 rounded-full bg-red-400 mr-1 ml-2" />
                At risk
              </span>
              <span className="flex items-center gap-2">
                Last computed: {formatRelative(data.last_computed)}
                <button
                  type="button"
                  onClick={refreshScores}
                  disabled={refreshing}
                  className="inline-flex items-center gap-1 border border-gray-200 px-2 py-1 rounded-lg hover:bg-gray-50 disabled:opacity-50"
                >
                  <RefreshCw className={`w-3 h-3 ${refreshing ? "animate-spin" : ""}`} />
                  Refresh scores
                </button>
              </span>
            </div>
          </div>

          {/* Alerts */}
          {data.alerts.length > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl overflow-hidden">
              <button
                type="button"
                onClick={() => setAlertsOpen((o) => !o)}
                className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-amber-800"
              >
                <span className="flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4" />
                  {data.alerts.length} employee{data.alerts.length !== 1 ? "s" : ""} need attention
                </span>
                {alertsOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>
              {alertsOpen && (
                <div className="divide-y divide-amber-100 border-t border-amber-200">
                  {data.alerts.map((alert) => (
                    <AlertRow key={alert.employee_id} alert={alert} onAction={() => {
                      setDetailId(alert.employee_id);
                    }} />
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Filters */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap gap-2">
              {(["all", "on_track", "needs_attention", "at_risk"] as FilterKey[]).map((f) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => setFilter(f)}
                  className={`text-xs px-3 py-1 rounded-full ${
                    filter === f ? "bg-brand-400 text-white" : "bg-gray-100 text-gray-600"
                  }`}
                >
                  {f === "all" ? "All" : f.replace(/_/g, " ")}
                </button>
              ))}
            </div>
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as SortKey)}
              className="text-xs border border-gray-200 rounded-lg px-2 py-1"
            >
              <option value="risk">Sort: At risk first</option>
              <option value="score">Sort: Health score ↑</option>
              <option value="name">Sort: Name</option>
            </select>
          </div>

          {/* Card grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {filteredEmployees.map((card) => (
              <HealthCard
                key={card.employee_id}
                card={card}
                onLogFeedback={
                  isHr ? undefined : () => navigateToEmployee(card, "continuous_feedback")
                }
                onViewGoals={isHr ? undefined : () => navigateToEmployee(card, "calibrator")}
                onDetail={() => setDetailId(card.employee_id)}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function SummaryTile({
  label,
  value,
  highlight,
  onClick,
}: {
  label: string;
  value: string;
  highlight?: "teal" | "amber" | "red";
  onClick?: () => void;
}) {
  const color =
    highlight === "teal"
      ? "text-brand-600"
      : highlight === "amber"
        ? "text-amber-600"
        : highlight === "red"
          ? "text-red-600"
          : "text-slate-900";
  const inner = (
    <>
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-xl font-semibold ${color}`}>{value}</p>
    </>
  );
  if (onClick) {
    return (
      <button type="button" onClick={onClick} className="text-left hover:opacity-80">
        {inner}
      </button>
    );
  }
  return <div>{inner}</div>;
}

function AlertRow({ alert, onAction }: { alert: HealthAlert; onAction: () => void }) {
  return (
    <div className="px-4 py-3 text-sm flex flex-wrap items-start justify-between gap-2">
      <div>
        <p className="font-medium text-gray-800 flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${ragDotClass(alert.rag_status)}`} />
          {alert.name}
        </p>
        <p className="text-gray-600 text-xs mt-1">{alert.at_risk_reasons.join(" · ")}</p>
        {alert.suggested_actions[0] && (
          <p className="text-gray-500 text-xs mt-1">Suggested: {alert.suggested_actions[0]}</p>
        )}
      </div>
      <button
        type="button"
        onClick={onAction}
        className="text-xs text-brand-600 hover:underline whitespace-nowrap"
      >
        View detail ↗
      </button>
    </div>
  );
}

function DimBar({ score }: { score: number }) {
  return (
    <div className="h-1 bg-gray-100 rounded-full overflow-hidden">
      <div
        className={`h-full ${scoreBarColor(score)}`}
        style={{ width: `${Math.min(100, Math.max(0, score))}%` }}
      />
    </div>
  );
}

function HealthCard({
  card,
  onLogFeedback,
  onViewGoals,
  onDetail,
}: {
  card: EmployeeHealthCard;
  onLogFeedback?: () => void;
  onViewGoals?: () => void;
  onDetail: () => void;
}) {
  const traj = trajectoryBadge(card.trajectory);
  const reasons = card.at_risk_reasons.slice(0, 2);
  const extraReasons = card.at_risk_reasons.length - 2;

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-2 min-w-0">
          <span className={`w-2.5 h-2.5 rounded-full mt-1.5 flex-shrink-0 ${ragDotClass(card.rag_status)}`} />
          <div className="min-w-0">
            <p className="font-medium text-gray-900 truncate">{card.name}</p>
            <p className="text-xs text-gray-500 truncate">{card.job_title}</p>
            <p className="text-xs text-gray-400">
              {card.department} · {card.location || "—"}
            </p>
          </div>
        </div>
        {card.grade && (
          <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full flex-shrink-0">
            {card.grade}
          </span>
        )}
      </div>

      <div>
        <div className="flex justify-between text-xs text-gray-500 mb-1">
          <span>Health score</span>
          <span className="font-medium text-gray-800">
            {Math.round(card.composite_score)} / 100
          </span>
        </div>
        <DimBar score={card.composite_score} />
      </div>

      <div className="grid grid-cols-4 gap-2 text-xs">
        <div>
          <p className="text-gray-400 mb-0.5">Goals</p>
          <p className="text-gray-700">
            {card.goals_calibrated} / {card.goals_total}
          </p>
          <DimBar score={card.goal_quality_score} />
        </div>
        <div>
          <p className="text-gray-400 mb-0.5">Check-in</p>
          <p className="text-gray-700">{checkinLabel(card.days_since_checkin)}</p>
          <DimBar score={card.checkin_score} />
        </div>
        <div>
          <p className="text-gray-400 mb-0.5">Feedback</p>
          <p className="text-gray-700">{card.feedback_count_cycle} entries</p>
          <DimBar score={card.feedback_score} />
        </div>
        <div>
          <p className="text-gray-400 mb-0.5">Review</p>
          <p className="text-gray-700">
            {[card.has_calibrated_goal, card.has_feedback_cycle, card.has_summary, card.had_recent_checkin].filter(Boolean).length} / 4
          </p>
          <DimBar score={card.review_readiness} />
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <span className={`text-xs px-2 py-0.5 rounded-full ${traj.className}`}>{traj.label}</span>
        {reasons.map((r) => (
          <span key={r} className="text-xs bg-red-50 text-red-600 px-2 py-0.5 rounded-full">
            {r}
          </span>
        ))}
        {extraReasons > 0 && (
          <span className="text-xs text-gray-400">+{extraReasons} more</span>
        )}
      </div>

      {card.last_feedback_snippet && (
        <p className="text-xs text-gray-500 italic border-l-2 border-brand-100 pl-2">
          Last feedback: &quot;{card.last_feedback_snippet}&quot;
        </p>
      )}

      <div className="flex flex-wrap gap-2 pt-1 border-t border-gray-100">
        {onLogFeedback && (
          <button type="button" onClick={onLogFeedback} className="text-xs text-brand-600 hover:underline">
            Log feedback ↗
          </button>
        )}
        {onViewGoals && (
          <button type="button" onClick={onViewGoals} className="text-xs text-brand-600 hover:underline">
            View goals ↗
          </button>
        )}
        <button type="button" onClick={onDetail} className="text-xs text-gray-600 hover:underline ml-auto">
          View detail →
        </button>
      </div>
    </div>
  );
}

function DetailDrawer({
  detail,
  loading,
  onBack,
  onNavigate,
  setActivePanel,
  isHr,
}: {
  detail: EmployeeHealthDetail;
  loading: boolean;
  onBack: () => void;
  onNavigate: (panel: string) => void;
  setActivePanel: (panel: string) => void;
  isHr: boolean;
}) {
  const traj = trajectoryBadge(detail.trajectory);
  const dims = [
    {
      name: "Goal quality",
      score: detail.goal_quality_score,
      signal: `${detail.goals_calibrated}/${detail.goals_total} calibrated · avg SMART ${Math.round(detail.avg_smart_score)}`,
    },
    {
      name: "Check-in recency",
      score: detail.checkin_score,
      signal: `Last: ${checkinLabel(detail.days_since_checkin)} · ${detail.total_sessions} sessions`,
    },
    {
      name: "Feedback coverage",
      score: detail.feedback_score,
      signal: `${detail.feedback_count_cycle} this cycle · last ${formatRelative(detail.last_feedback_date)}`,
    },
    {
      name: "Review readiness",
      score: detail.review_readiness,
      signal: `${Math.round(detail.review_readiness / 25)}/4 checklist items`,
    },
    {
      name: "Trajectory",
      score: detail.trajectory_score,
      signal: traj.label,
    },
  ];

  if (loading) {
    return <p className="text-gray-400 py-12 text-center">Loading detail…</p>;
  }

  return (
    <div className="space-y-6">
      <button type="button" onClick={onBack} className="inline-flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900">
        <ArrowLeft className="w-4 h-4" /> Back to team
      </button>

      <div className="bg-white border border-gray-200 rounded-xl p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold text-slate-900">{detail.name}</h2>
            <p className="text-sm text-gray-500">
              {detail.job_title} · {detail.department}
            </p>
          </div>
          <span
            className={`text-sm px-3 py-1 rounded-full text-white capitalize ${
              detail.rag_status === "on_track"
                ? "bg-emerald-500"
                : detail.rag_status === "needs_attention"
                  ? "bg-amber-500"
                  : "bg-red-500"
            }`}
          >
            {detail.rag_status.replace(/_/g, " ")}
          </span>
        </div>
        <p className="mt-4 text-lg font-medium text-gray-800">
          Composite health score: {Math.round(detail.composite_score)} / 100
        </p>
        <DimBar score={detail.composite_score} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {dims.map((d) => (
          <div key={d.name} className="bg-white border border-gray-200 rounded-xl p-4">
            <div className="flex justify-between items-center mb-2">
              <p className="text-sm font-medium text-gray-700">{d.name}</p>
              <span className="text-sm font-semibold">{Math.round(d.score)}</span>
            </div>
            <DimBar score={d.score} />
            <p className="text-xs text-gray-500 mt-2">{d.signal}</p>
            <p className="text-xs text-gray-400 mt-1">{dimensionLabel(d.score)}</p>
          </div>
        ))}
      </div>

      {detail.milestones && detail.milestones.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <h3 className="text-sm font-medium text-gray-700 mb-2">Goals</h3>
          <div className="space-y-2 text-xs">
            {detail.milestones.slice(0, 4).map((m) => (
              <div key={m.id} className="flex justify-between gap-2 border-b border-gray-50 pb-1">
                <span className="truncate text-gray-600">{m.raw_goal.slice(0, 50)}…</span>
                <span className="text-gray-400 whitespace-nowrap">
                  {m.overall_score} · {m.status}
                </span>
              </div>
            ))}
          </div>
          {detail.goals_needs_work > 0 && !isHr && (
            <button
              type="button"
              onClick={() => onNavigate("calibrator")}
              className="text-xs text-brand-600 mt-2 hover:underline"
            >
              Calibrate goals ↗
            </button>
          )}
        </div>
      )}

      {detail.feedback_entries && detail.feedback_entries.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <h3 className="text-sm font-medium text-gray-700 mb-3">Feedback timeline</h3>
          <div className="space-y-3 border-l-2 border-brand-100 pl-3">
            {detail.feedback_entries.map((e) => (
              <div key={e.id ?? e.entry_id}>
                <p className="text-xs text-gray-400">
                  {formatRelative(e.created_at)} · {e.feedback_type} · {e.sentiment}
                </p>
                <p className="text-sm text-gray-700">{(e.content ?? e.raw_text ?? "").slice(0, 100)}…</p>
              </div>
            ))}
          </div>
          {!isHr && (
            <button
              type="button"
              onClick={() => {
                onNavigate("continuous_feedback");
                setActivePanel("continuous_feedback");
              }}
              className="text-xs text-brand-600 mt-3 hover:underline"
            >
              View all in continuous feedback →
            </button>
          )}
        </div>
      )}

      <div className="bg-brand-50 border border-brand-100 rounded-xl p-4 space-y-3">
        <h3 className="text-sm font-medium text-brand-800">Feedback summary</h3>
        {detail.feedback_summary ? (
          <>
            <p className="text-sm text-gray-700 whitespace-pre-wrap">{detail.feedback_summary.content}</p>
            <p className="text-xs text-gray-500">
              Trajectory: {traj.label} · Confidence: {detail.feedback_summary.confidence}
            </p>
          </>
        ) : (
          <p className="text-sm text-gray-600">No summary generated yet.</p>
        )}
        {!isHr && (
          <button
            type="button"
            onClick={() => {
              onNavigate("continuous_feedback");
              setActivePanel("continuous_feedback");
            }}
            className="text-sm text-brand-700 font-medium hover:underline"
          >
            Open continuous feedback ↗
          </button>
        )}
      </div>
    </div>
  );
}
