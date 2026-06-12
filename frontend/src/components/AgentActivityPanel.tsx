import { useCallback, useEffect, useState } from "react";
import { Bot, ChevronDown, ChevronRight, RefreshCw, Search } from "lucide-react";
import { apiFetch } from "../hooks/api";
import type { AgentActivityEvent, AgentActivityStep, TransparencyCoverage } from "../types";

interface Props {
  employeeId?: string | null;
  className?: string;
}

const COLLECTION_LABELS: Record<string, string> = {
  policy_chunks: "Policy docs",
  okr_embeddings: "Company OKRs",
  milestone_embeddings: "Goals",
  feedback_embeddings: "Feedback",
  feedback_entries: "Feedback entries",
  feedback_summaries: "Feedback summaries",
  milestones: "Goals",
  context_brief: "Context brief",
};

function confidenceBadge(level: string | null | undefined) {
  if (!level) return null;
  const styles: Record<string, string> = {
    high: "bg-emerald-50 text-emerald-700 border-emerald-200",
    medium: "bg-amber-50 text-amber-700 border-amber-200",
    low: "bg-rose-50 text-rose-700 border-rose-200",
  };
  return (
    <span
      className={`text-[10px] px-1.5 py-0.5 rounded border font-medium capitalize ${styles[level] ?? "bg-gray-50 text-gray-600 border-gray-200"}`}
    >
      {level}
    </span>
  );
}

function stepIcon(step: AgentActivityStep) {
  if (step.type === "search") return <Search className="w-3 h-3 shrink-0" />;
  return <ChevronRight className="w-3 h-3 shrink-0 text-gray-400" />;
}

function stepLabel(step: AgentActivityStep): string {
  switch (step.type) {
    case "handoff":
      return step.to
        ? `${step.from ?? "agent"} → ${step.to}${step.detail ? `: ${step.detail}` : ""}`
        : step.detail ?? "Handoff";
    case "search": {
      const coll = COLLECTION_LABELS[step.collection ?? ""] ?? step.collection ?? "Search";
      const hits = step.hit_count ?? 0;
      return `${coll}: "${step.query ?? step.detail ?? ""}" (${hits} hit${hits === 1 ? "" : "s"})`;
    }
    case "load":
      return step.detail ?? `Loaded ${step.resource ?? step.source ?? "data"}`;
    case "llm":
      return `LLM ${step.model ?? ""}${step.detail ? ` — ${step.detail}` : ""}`.trim();
    case "decision":
      return step.detail ? `Decision: ${step.detail}` : "Decision recorded";
    case "confidence":
      return step.reason ? `Confidence: ${step.reason}` : step.detail ?? "Confidence scored";
    case "result":
      return step.detail ?? "Done";
    default:
      return step.detail ?? step.type;
  }
}

function formatTime(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso.includes("T") ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function CoverageBar({ coverage }: { coverage: TransparencyCoverage | null }) {
  if (!coverage || coverage.total_runs === 0) return null;
  return (
    <div className="mb-3 p-2.5 rounded-lg bg-brand-50/60 border border-accent-400/20 ring-1 ring-accent-400/10">
      <p className="text-[10px] font-medium text-brand-800 mb-1.5">Transparency (7d)</p>
      <div className="space-y-1">
        <div className="flex justify-between text-[10px] text-gray-600">
          <span>Confidence scoring</span>
          <span>{coverage.confidence_coverage_pct}%</span>
        </div>
        <div className="h-1.5 bg-white rounded-full overflow-hidden">
          <div
            className="h-full bg-brand-500 rounded-full"
            style={{ width: `${coverage.confidence_coverage_pct}%` }}
          />
        </div>
        <div className="flex justify-between text-[10px] text-gray-600">
          <span>Decision rationale</span>
          <span>{coverage.rationale_coverage_pct}%</span>
        </div>
        <div className="h-1.5 bg-white rounded-full overflow-hidden">
          <div
            className="h-full bg-brand-400 rounded-full"
            style={{ width: `${coverage.rationale_coverage_pct}%` }}
          />
        </div>
      </div>
    </div>
  );
}

function ActivityCard({ event }: { event: AgentActivityEvent }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border border-gray-100 rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full text-left px-3 py-2.5 hover:bg-gray-50 flex items-start gap-2"
      >
        {open ? (
          <ChevronDown className="w-3.5 h-3.5 mt-0.5 shrink-0 text-gray-400" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 mt-0.5 shrink-0 text-gray-400" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-medium text-brand-700">{event.agent_label}</span>
            <div className="flex items-center gap-1 shrink-0">
              {confidenceBadge(event.confidence_level)}
              <span className="text-[10px] text-gray-400">{formatTime(event.created_at)}</span>
            </div>
          </div>
          {event.summary && (
            <p className="text-xs text-gray-600 mt-0.5 line-clamp-2">{event.summary}</p>
          )}
          {event.confidence_reason && (
            <p className="text-[10px] text-gray-500 mt-0.5 line-clamp-1">{event.confidence_reason}</p>
          )}
          <div className="flex items-center gap-2 mt-0.5">
            {event.duration_ms > 0 && (
              <p className="text-[10px] text-gray-400">{event.duration_ms}ms</p>
            )}
            {event.workflow_id && (
              <p className="text-[10px] text-gray-400 truncate" title={event.workflow_id}>
                {event.workflow_id.slice(0, 14)}…
              </p>
            )}
          </div>
        </div>
      </button>
      {open && (
        <div className="px-3 pb-3 pt-0 border-t border-gray-50 bg-gray-50/50">
          {event.rationale && (
            <div className="mt-2 p-2 rounded bg-white border border-gray-100 text-[11px]">
              <p className="font-medium text-gray-700">{event.rationale.decision}</p>
              <p className="text-gray-600 mt-1">{event.rationale.explanation}</p>
              {event.rationale.sources.length > 0 && (
                <p className="text-gray-400 mt-1">
                  Sources: {event.rationale.sources.map((s) => COLLECTION_LABELS[s] ?? s).join(", ")}
                </p>
              )}
            </div>
          )}
          {event.steps.length > 0 && (
            <ul className="space-y-1.5 mt-2">
              {event.steps.map((step, i) => (
                <li key={i} className="flex items-start gap-1.5 text-[11px] text-gray-600">
                  <span className="mt-0.5">{stepIcon(step)}</span>
                  <span className="min-w-0 break-words">{stepLabel(step)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export default function AgentActivityPanel({ employeeId, className = "" }: Props) {
  const [events, setEvents] = useState<AgentActivityEvent[]>([]);
  const [coverage, setCoverage] = useState<TransparencyCoverage | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    const empParam = employeeId ? `employee_id=${encodeURIComponent(employeeId)}&` : "";
    const activityUrl = `/api/agent-activity?${empParam}limit=12`;
    const coverageUrl = `/api/transparency/coverage${employeeId ? `?employee_id=${encodeURIComponent(employeeId)}` : ""}`;
    setLoading(true);
    Promise.all([
      apiFetch(activityUrl).then((r) => (r.ok ? r.json() : [])),
      apiFetch(coverageUrl).then((r) => (r.ok ? r.json() : null)),
    ])
      .then(([data, cov]) => {
        setEvents(Array.isArray(data) ? data : []);
        setCoverage(cov);
      })
      .catch(() => {
        setEvents([]);
        setCoverage(null);
      })
      .finally(() => setLoading(false));
  }, [employeeId]);

  useEffect(() => {
    load();
    const interval = setInterval(load, 8000);
    return () => clearInterval(interval);
  }, [load]);

  return (
    <aside
      className={`bg-white border border-gray-200 rounded-xl p-4 xl:sticky xl:top-6 ${className}`.trim()}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Bot className="w-4 h-4 text-accent-400" />
          <h2 className="text-sm font-medium text-gray-700">Agent activity</h2>
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600 disabled:opacity-50"
          title="Refresh"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>
      <p className="text-[11px] text-gray-400 mb-3">
        Traces, confidence scores, and decision rationale — correlated by workflow ID.
      </p>
      <CoverageBar coverage={coverage} />
      {events.length === 0 ? (
        <p className="text-xs text-gray-400 py-6 text-center">
          No agent runs yet. Use Growth Coach, calibrate a goal, or synthesise feedback.
        </p>
      ) : (
        <div className="space-y-2 max-h-[calc(100vh-12rem)] overflow-y-auto">
          {events.map((ev) => (
            <ActivityCard key={ev.id} event={ev} />
          ))}
        </div>
      )}
    </aside>
  );
}
