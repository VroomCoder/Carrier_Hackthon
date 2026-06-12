import { useCallback, useEffect, useMemo, useState } from "react";
import { MessageSquarePlus, Plus, Share2, Trash2 } from "lucide-react";
import { apiFetch } from "../hooks/api";
import type {
  AuthUser,
  BiasFlag,
  BiasCheckResult,
  Employee,
  FeedbackEntry,
  FeedbackSentiment,
  FeedbackStats,
  FeedbackSummary,
  StructuredFeedbackType,
  ToastType,
} from "../types";
import {
  FEEDBACK_TAGS_SUGGESTED,
  FEEDBACK_TYPE_CONFIG,
  TYPE_BADGE_CLASS,
} from "../data/seedData";
import { canLogFeedbackForEmployee } from "../utils/feedback";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import FeedbackSynthesiser from "./FeedbackSynthesiser";
import type { SynthesisResult } from "../types";

interface Props {
  activeEmployee: Employee | null;
  user: AuthUser;
  directReports: Employee[];
  addToast: (message: string, type?: ToastType) => void;
  setActivePanel?: (panel: string) => void;
}

const TYPES: StructuredFeedbackType[] = [
  "strength",
  "development",
  "project",
  "behaviour",
  "general",
];

const SENTIMENTS: FeedbackSentiment[] = ["positive", "neutral", "constructive"];

const GENERATE_STEPS = [
  "Retrieving feedback entries…",
  "Identifying themes…",
  "Drafting review summary…",
  "Evaluating quality…",
  "Finalising…",
];

function formatDate(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso.includes("T") ? iso : iso.replace(" ", "T") + "Z");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function qualityColor(score: number): string {
  if (score >= 8) return "bg-brand-400";
  if (score >= 6) return "bg-amber-400";
  return "bg-red-400";
}

export default function ContinuousFeedback({
  activeEmployee,
  user,
  directReports,
  addToast,
  setActivePanel,
}: Props) {
  const [entries, setEntries] = useState<FeedbackEntry[]>([]);
  const [stats, setStats] = useState<FeedbackStats | null>(null);
  const [summary, setSummary] = useState<FeedbackSummary | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [filterType, setFilterType] = useState<string>("all");
  const [filterCycle, setFilterCycle] = useState<string>("all");
  const [generating, setGenerating] = useState(false);
  const [genStep, setGenStep] = useState(0);
  const [biasCheck, setBiasCheck] = useState<BiasCheckResult | null>(null);
  const [biasChecking, setBiasChecking] = useState(false);
  const [dismissedFlags, setDismissedFlags] = useState<Set<string>>(new Set());
  const [showNoBias, setShowNoBias] = useState(false);
  const [useAiPath, setUseAiPath] = useState(false);
  const [finalisedSynthesis, setFinalisedSynthesis] = useState<SynthesisResult | null>(null);

  const [form, setForm] = useState({
    content: "",
    context: "",
    feedback_type: "general" as StructuredFeedbackType,
    sentiment: "neutral" as FeedbackSentiment,
    visibility: "manager_only" as "manager_only" | "shared_with_employee",
    tags: [] as string[],
    tagInput: "",
    is_draft: false,
  });

  const debouncedContent = useDebouncedValue(form.content, 1200);

  const empId = activeEmployee?.employee_id;
  const canManage = canLogFeedbackForEmployee(user, activeEmployee, directReports);

  const cycles = useMemo(() => {
    const set = new Set(entries.map((e) => e.review_cycle).filter(Boolean));
    return Array.from(set).sort().reverse();
  }, [entries]);

  const filtered = useMemo(() => {
    return entries.filter((e) => {
      if (filterType !== "all" && e.feedback_type !== filterType) return false;
      if (filterCycle !== "all" && e.review_cycle !== filterCycle) return false;
      return true;
    });
  }, [entries, filterType, filterCycle]);

  const selected = entries.find((e) => (e.entry_id || e.id) === selectedId);

  const loadAll = useCallback(async () => {
    if (!empId) return;
    const [listRes, statsRes, sumRes] = await Promise.all([
      apiFetch(`/api/feedback/entries?employee_id=${encodeURIComponent(empId)}&include_drafts=true`),
      apiFetch(`/api/feedback/stats?employee_id=${encodeURIComponent(empId)}`),
      apiFetch(
        `/api/feedback/summary?employee_id=${encodeURIComponent(empId)}&review_type=mid_year`
      ),
    ]);
    if (listRes.ok) {
      const data = await listRes.json();
      setEntries(data.entries ?? []);
    }
    if (statsRes.ok) setStats(await statsRes.json());
    if (sumRes.ok) {
      const s = await sumRes.json();
      setSummary(s);
    }
  }, [empId]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    setDismissedFlags(new Set());
    setFinalisedSynthesis(null);
  }, [form.content]);

  useEffect(() => {
    if (!canManage || debouncedContent.trim().length < 80) {
      setBiasCheck(null);
      return;
    }
    let cancelled = false;
    setBiasChecking(true);
    apiFetch("/api/feedback/check-bias", {
      method: "POST",
      body: JSON.stringify({ text: debouncedContent }),
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data: BiasCheckResult | null) => {
        if (cancelled || !data) return;
        setBiasCheck(data);
        if (data.flags.length === 0) {
          setShowNoBias(true);
          window.setTimeout(() => setShowNoBias(false), 3000);
        }
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setBiasChecking(false);
      });
    return () => {
      cancelled = true;
    };
  }, [debouncedContent, canManage]);

  const visibleBiasFlags = (biasCheck?.flags ?? []).filter((flag) => {
    if (flag.severity === "high") return true;
    const key = `${flag.type}:${flag.passage}`;
    return !dismissedFlags.has(key);
  });

  const resetForm = () => {
    setForm({
      content: "",
      context: "",
      feedback_type: "general",
      sentiment: "neutral",
      visibility: "manager_only",
      tags: [],
      tagInput: "",
      is_draft: false,
    });
    setUseAiPath(false);
    setFinalisedSynthesis(null);
  };

  const submitEntry = async (asDraft: boolean) => {
    if (!empId || !form.content.trim()) {
      addToast("Feedback text is required", "error");
      return;
    }
    if (useAiPath && !asDraft && !finalisedSynthesis?.synthesis_id) {
      addToast("Synthesise and finalise commentary first", "warning");
      return;
    }
    const res = await apiFetch("/api/feedback/entries", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        employee_id: empId,
        content: form.content.trim(),
        context: form.context.trim(),
        feedback_type: form.feedback_type,
        sentiment: form.sentiment,
        visibility: form.visibility,
        tags: form.tags,
        is_draft: asDraft,
        synthesis_id:
          useAiPath && finalisedSynthesis?.synthesis_id
            ? finalisedSynthesis.synthesis_id
            : null,
      }),
    });
    if (!res.ok) {
      addToast("Failed to save feedback", "error");
      return;
    }
    addToast(
      asDraft ? "Draft saved" : `Feedback logged for ${activeEmployee?.name}`,
      "success"
    );
    resetForm();
    setShowForm(false);
    loadAll();
  };

  const generateSummary = async (reviewType: "mid_year" | "year_end") => {
    if (!empId) return;
    setGenerating(true);
    setGenStep(0);
    const stepTimer = setInterval(() => {
      setGenStep((s) => Math.min(s + 1, GENERATE_STEPS.length - 1));
    }, 800);
    try {
      const res = await apiFetch("/api/feedback/summarise", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ employee_id: empId, review_type: reviewType }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        addToast(typeof err.detail === "string" ? err.detail : "Summary failed", "error");
        return;
      }
      const data = await res.json();
      if (data.reason === "no_feedback") {
        addToast("No feedback entries to summarise", "warning");
        return;
      }
      addToast("Review summary generated", "success");
      await loadAll();
      setSummary({
        summary_id: data.summary_id,
        employee_id: empId,
        review_cycle: data.review_cycle,
        review_type: reviewType,
        content: data.summary,
        entry_count: data.entry_count,
        themes: data.themes ?? [],
        strengths: data.strengths,
        development_areas: data.development_areas,
        trajectory: data.trajectory,
        notable_pattern: data.notable_pattern,
        quality_score: data.quality_score,
        confidence: data.confidence,
        generated_at: new Date().toISOString(),
        status: "draft",
        self_corrections: data.self_corrections,
      });
    } finally {
      clearInterval(stepTimer);
      setGenerating(false);
      setGenStep(GENERATE_STEPS.length - 1);
    }
  };

  const deleteEntry = async (id: string) => {
    if (!confirm("Delete this feedback entry?")) return;
    const res = await apiFetch(`/api/feedback/entries/${id}`, { method: "DELETE" });
    if (!res.ok) {
      addToast("Delete failed", "error");
      return;
    }
    addToast("Entry deleted", "info");
    setSelectedId(null);
    loadAll();
  };

  const shareEntry = async (id: string) => {
    const res = await apiFetch(`/api/feedback/entries/${id}/share`, { method: "POST" });
    if (!res.ok) {
      addToast("Share failed", "error");
      return;
    }
    addToast("Shared with employee", "success");
    loadAll();
  };

  if (!activeEmployee) {
    return (
      <div className="text-center py-16 text-gray-400">
        <MessageSquarePlus className="w-10 h-10 mx-auto mb-3 opacity-40" />
        <p>Select an employee to manage continuous feedback.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="page-title">Continuous feedback</h1>
          <p className="text-sm text-gray-500 mt-1">{activeEmployee.name}</p>
          {!canManage && (
            <p className="text-xs text-gray-400 mt-1">
              Only managers can log feedback for their direct reports.
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {stats && (
            <>
              <span className="text-xs bg-gray-100 px-2 py-1 rounded-full">
                {stats.current_cycle_entries} this cycle
              </span>
              <span className="text-xs bg-gray-100 px-2 py-1 rounded-full">
                {stats.total_entries} total
              </span>
            </>
          )}
          {canManage && (
            <button
              onClick={() => {
                setShowForm(true);
                setSelectedId(null);
                resetForm();
              }}
              className="flex items-center gap-1 bg-brand-400 text-white px-3 py-2 rounded-lg text-sm"
            >
              <Plus className="w-4 h-4" /> Add feedback
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr_280px] gap-4 items-start">
        {/* Left — list */}
        <div className="bg-white border border-gray-200 rounded-xl p-3 space-y-3">
          <div className="flex flex-wrap gap-1">
            <select
              value={filterCycle}
              onChange={(e) => setFilterCycle(e.target.value)}
              className="text-xs border border-gray-200 rounded px-2 py-1"
            >
              <option value="all">All cycles</option>
              {cycles.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-wrap gap-1">
            {["all", ...TYPES].map((t) => (
              <button
                key={t}
                onClick={() => setFilterType(t)}
                className={`text-[10px] px-2 py-0.5 rounded-full ${
                  filterType === t ? "bg-brand-100 text-brand-700" : "bg-gray-100 text-gray-600"
                }`}
              >
                {t === "all" ? "All" : FEEDBACK_TYPE_CONFIG[t as StructuredFeedbackType]?.label ?? t}
              </button>
            ))}
          </div>
          <div className="space-y-2 max-h-[420px] overflow-y-auto">
            {filtered.length === 0 ? (
              <p className="text-xs text-gray-400 py-4 text-center">
                {canManage
                  ? "No entries yet. Log feedback after key moments."
                  : "No feedback entries to display."}
              </p>
            ) : (
              filtered.map((e) => {
                const id = e.entry_id || e.id;
                const cfg = FEEDBACK_TYPE_CONFIG[e.feedback_type as StructuredFeedbackType];
                return (
                  <button
                    key={id}
                    type="button"
                    onClick={() => {
                      setSelectedId(id);
                      setShowForm(false);
                    }}
                    className={`w-full text-left p-2 rounded-lg border text-xs ${
                      selectedId === id ? "border-brand-300 bg-brand-50" : "border-gray-100"
                    } ${e.is_draft ? "opacity-70" : ""}`}
                  >
                    <div className="flex gap-1 mb-1">
                      <span
                        className={`px-1.5 py-0.5 rounded ${
                          TYPE_BADGE_CLASS[e.feedback_type] ?? TYPE_BADGE_CLASS.general
                        }`}
                      >
                        {cfg?.label ?? e.feedback_type}
                      </span>
                      {e.is_draft && (
                        <span className="text-gray-400">Draft</span>
                      )}
                    </div>
                    <p className="line-clamp-2 text-gray-700">
                      {e.content || e.raw_text}
                    </p>
                    <p className="text-gray-400 mt-1">
                      {formatDate(e.created_at)} · {e.review_cycle}
                    </p>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Middle — form / detail */}
        <div className="bg-white border border-gray-200 rounded-xl p-4 min-h-[320px]">
          {showForm && canManage ? (
            <div className="space-y-3">
              <h2 className="text-sm font-medium text-gray-700">New feedback entry</h2>
              <div className="flex flex-wrap gap-1">
                {TYPES.map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setForm((f) => ({ ...f, feedback_type: t }))}
                    className={`text-xs px-2 py-1 rounded ${
                      form.feedback_type === t ? "bg-brand-400 text-white" : "bg-gray-100"
                    }`}
                  >
                    {FEEDBACK_TYPE_CONFIG[t].label}
                  </button>
                ))}
              </div>
              <textarea
                value={form.content}
                onChange={(e) => setForm((f) => ({ ...f, content: e.target.value }))}
                rows={4}
                placeholder="Describe what you observed, with specific examples…"
                className="w-full border border-gray-200 rounded-lg p-2 text-sm"
              />
              {canManage && form.content.length >= 80 && (
                <div className="space-y-2">
                  {biasChecking && (
                    <p className="text-[11px] text-gray-400">Checking for bias…</p>
                  )}
                  {showNoBias && !biasChecking && visibleBiasFlags.length === 0 && (
                    <p className="text-[11px] text-brand-600">✓ No bias detected</p>
                  )}
                  {visibleBiasFlags.map((flag, i) => (
                    <BiasNudgeCard
                      key={`${flag.passage}-${i}`}
                      flag={flag}
                      onDismiss={
                        flag.severity === "high"
                          ? undefined
                          : () =>
                              setDismissedFlags((prev) => {
                                const next = new Set(prev);
                                next.add(`${flag.type}:${flag.passage}`);
                                return next;
                              })
                      }
                    />
                  ))}
                </div>
              )}
              {canManage && (
                <div className="space-y-2 pt-1">
                  <button
                    type="button"
                    onClick={() => setUseAiPath((v) => !v)}
                    className="text-xs border border-brand-200 text-brand-700 px-3 py-1 rounded-full hover:bg-brand-50"
                  >
                    {useAiPath ? "Hide AI synthesis" : "Use AI synthesis"}
                  </button>
                  {useAiPath && empId && (
                    <FeedbackSynthesiser
                      employeeId={empId}
                      rawText={form.content}
                      onFinalised={setFinalisedSynthesis}
                      onError={(msg) => addToast(msg, "error")}
                      onApplyRewrite={(text) =>
                        setForm((f) => ({ ...f, content: `${f.content}\n${text}`.trim() }))
                      }
                    />
                  )}
                </div>
              )}
              <input
                value={form.context}
                onChange={(e) => setForm((f) => ({ ...f, context: e.target.value }))}
                placeholder="Context (optional) — e.g. after board presentation"
                className="w-full border border-gray-200 rounded-lg p-2 text-sm"
              />
              <div className="flex gap-2">
                {SENTIMENTS.map((s) => (
                  <label key={s} className="text-xs flex items-center gap-1">
                    <input
                      type="radio"
                      checked={form.sentiment === s}
                      onChange={() => setForm((f) => ({ ...f, sentiment: s }))}
                    />
                    {s}
                  </label>
                ))}
              </div>
              <div className="flex flex-wrap gap-1">
                {FEEDBACK_TAGS_SUGGESTED.map((tag) => (
                  <button
                    key={tag}
                    type="button"
                    onClick={() =>
                      setForm((f) => ({
                        ...f,
                        tags: f.tags.includes(tag) ? f.tags : [...f.tags, tag],
                      }))
                    }
                    className="text-[10px] bg-gray-100 px-2 py-0.5 rounded-full"
                  >
                    {tag}
                  </button>
                ))}
              </div>
              <select
                value={form.visibility}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    visibility: e.target.value as "manager_only" | "shared_with_employee",
                  }))
                }
                className="text-sm border border-gray-200 rounded px-2 py-1"
              >
                <option value="manager_only">Manager only</option>
                <option value="shared_with_employee">Share with employee</option>
              </select>
              <div className="flex gap-2">
                <button
                  onClick={() => submitEntry(true)}
                  className="text-sm border border-gray-200 px-3 py-2 rounded-lg"
                >
                  Save draft
                </button>
                <button
                  onClick={() => submitEntry(false)}
                  disabled={useAiPath && !finalisedSynthesis?.synthesis_id}
                  className="text-sm bg-brand-400 text-white px-3 py-2 rounded-lg disabled:opacity-50"
                >
                  {useAiPath ? "Submit with commentary" : "Submit feedback"}
                </button>
              </div>
            </div>
          ) : selected ? (
            <div className="space-y-3">
              <h2 className="text-sm font-medium text-gray-500">Entry detail</h2>
              <p className="text-sm text-gray-800 whitespace-pre-wrap">
                {selected.content || selected.raw_text}
              </p>
              {selected.synthesized_commentary && (
                <p className="text-sm text-gray-600 italic border-l-2 border-brand-200 pl-2 whitespace-pre-wrap">
                  {selected.synthesized_commentary}
                </p>
              )}
              {selected.context && (
                <p className="text-xs text-gray-500">Context: {selected.context}</p>
              )}
              <p className="text-xs text-gray-400">
                {selected.author_name} · {formatDate(selected.created_at)} · {selected.review_cycle}
              </p>
              {canManage && (
                <div className="flex gap-2">
                  {selected.visibility === "manager_only" && (
                    <button
                      onClick={() => shareEntry(selected.entry_id || selected.id)}
                      className="text-xs text-brand-600 flex items-center gap-1"
                    >
                      <Share2 className="w-3 h-3" /> Share
                    </button>
                  )}
                  <button
                    onClick={() => deleteEntry(selected.entry_id || selected.id)}
                    className="text-xs text-red-500 flex items-center gap-1"
                  >
                    <Trash2 className="w-3 h-3" /> Delete
                  </button>
                </div>
              )}
            </div>
          ) : (
            <p className="text-sm text-gray-400 py-12 text-center">
              Select an entry or add new feedback.
            </p>
          )}
        </div>

        {/* Right — summary */}
        <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-3">
          <h2 className="text-sm font-medium text-gray-700">Review summary</h2>
          <p className="text-xs text-gray-400">AI-generated from cycle feedback entries</p>

          {generating && (
            <div className="space-y-2 py-2">
              {GENERATE_STEPS.map((label, i) => (
                <div
                  key={label}
                  className={`text-xs flex items-center gap-2 ${
                    i <= genStep ? "text-brand-600" : "text-gray-300"
                  }`}
                >
                  <span>{i <= genStep ? "✓" : "○"}</span>
                  {label}
                </div>
              ))}
            </div>
          )}

          {!generating && !summary && canManage && stats && stats.total_entries > 0 && (
            <div className="space-y-2">
              <p className="text-xs text-gray-500">
                {stats.total_entries} entries ready to summarise
              </p>
              <button
                onClick={() => generateSummary("mid_year")}
                className="w-full text-xs border border-brand-200 text-brand-700 py-2 rounded-lg"
              >
                Mid-year summary
              </button>
              <button
                onClick={() => generateSummary("year_end")}
                className="w-full text-xs border border-brand-200 text-brand-700 py-2 rounded-lg"
              >
                Year-end summary
              </button>
            </div>
          )}

          {!generating && summary && (
            <div className="space-y-2 text-sm">
              <div className="flex flex-wrap gap-1 text-xs">
                <span className="bg-gray-100 px-2 py-0.5 rounded">{summary.review_cycle}</span>
                <span className="bg-gray-100 px-2 py-0.5 rounded">{summary.review_type}</span>
              </div>
              {summary.quality_score != null && summary.quality_score > 0 && (
                <div>
                  <p className="text-xs text-gray-500 mb-1">
                    Quality: {summary.quality_score.toFixed(1)} · {summary.confidence}
                  </p>
                  <div className="h-1.5 bg-gray-100 rounded overflow-hidden">
                    <div
                      className={`h-full ${qualityColor(summary.quality_score)}`}
                      style={{ width: `${Math.min(100, summary.quality_score * 10)}%` }}
                    />
                  </div>
                </div>
              )}
              <p className="text-gray-700 text-xs whitespace-pre-wrap">{summary.content}</p>
              {summary.themes?.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {summary.themes.map((t) => (
                    <span key={t} className="text-[10px] bg-brand-50 text-brand-700 px-2 py-0.5 rounded-full">
                      {t}
                    </span>
                  ))}
                </div>
              )}
              {canManage && (
                <div className="flex flex-col gap-1 pt-2">
                  <button
                    onClick={() => {
                      setActivePanel?.("feedback");
                      addToast("Open Mid-year or Year-end tab to draft a review", "info");
                    }}
                    className="text-xs text-brand-600 hover:underline text-left"
                  >
                    Use in review draft →
                  </button>
                  <button
                    onClick={() => generateSummary(summary.review_type)}
                    className="text-xs text-gray-500 hover:underline text-left"
                  >
                    Regenerate
                  </button>
                </div>
              )}
            </div>
          )}

          {!generating && !summary && (!stats || stats.total_entries === 0) && (
            <p className="text-xs text-gray-400 py-4">
              Add feedback throughout the cycle. The agent will summarise at review time.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function BiasNudgeCard({
  flag,
  onDismiss,
}: {
  flag: BiasFlag;
  onDismiss?: () => void;
}) {
  const dotClass =
    flag.severity === "high"
      ? "bg-red-500"
      : flag.severity === "medium"
        ? "bg-amber-500"
        : "bg-gray-400";

  return (
    <div className="border border-gray-100 rounded-lg p-3 text-xs bg-amber-50/40">
      <div className="flex items-start justify-between gap-2">
        <p className="font-medium text-gray-700 flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full shrink-0 ${dotClass}`} />
          {flag.type} · {flag.severity}
        </p>
        {onDismiss && (
          <button type="button" onClick={onDismiss} className="text-gray-400 hover:text-gray-600">
            Dismiss
          </button>
        )}
      </div>
      <p className="text-gray-600 mt-1 italic">&quot;{flag.passage}&quot;</p>
      <p className="text-gray-500 mt-1">→ Consider: {flag.suggestion}</p>
    </div>
  );
}
