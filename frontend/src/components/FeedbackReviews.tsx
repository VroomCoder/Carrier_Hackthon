import { useCallback, useEffect, useState } from "react";
import { Lock, Share2, Sparkles } from "lucide-react";
import { apiFetch } from "../hooks/api";
import AchievementsPanel from "./AchievementsPanel";
import type {
  AuthUser,
  Employee,
  FeedbackEntry,
  FeedbackSummary,
  Milestone,
  PerformanceReview,
  ReviewType,
  ToastType,
} from "../types";

interface Props {
  activeEmployee: Employee | null;
  user: AuthUser;
  selfEmployee: Employee | null;
  directReports: Employee[];
  addToast: (message: string, type?: ToastType) => void;
  setActivePanel?: (panel: string) => void;
}

type Tab = "continuous" | "self_assessment" | "mid_year" | "year_end";

function formatDate(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso.replace(" ", "T") + "Z");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function statusBadge(status: string): string {
  switch (status) {
    case "submitted":
      return "bg-blue-50 text-blue-700";
    case "locked":
      return "bg-gray-100 text-gray-600";
    default:
      return "bg-amber-50 text-amber-700";
  }
}

export default function FeedbackReviews({
  activeEmployee,
  user,
  selfEmployee,
  directReports,
  addToast,
  setActivePanel,
}: Props) {
  const [tab, setTab] = useState<Tab>("self_assessment");
  const [feedbackList, setFeedbackList] = useState<FeedbackEntry[]>([]);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [midYearReview, setMidYearReview] = useState<PerformanceReview | null>(null);
  const [yearEndReview, setYearEndReview] = useState<PerformanceReview | null>(null);

  const [reviewDraft, setReviewDraft] = useState({
    employee_self_assessment: "",
    manager_summary: "",
    development_areas: "",
    overall_rating: "" as string | number,
  });
  const [reviewSaving, setReviewSaving] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [assessmentDrafts, setAssessmentDrafts] = useState<Record<string, string>>({});
  const [assessmentSaving, setAssessmentSaving] = useState<string | null>(null);
  const [feedbackSummary, setFeedbackSummary] = useState<FeedbackSummary | null>(null);
  const [generatingSummary, setGeneratingSummary] = useState(false);
  const [cycleFeedbackCount, setCycleFeedbackCount] = useState(0);

  const empId = activeEmployee?.employee_id;
  const isSelf = selfEmployee?.employee_id === empId;
  const isDirectReport =
    !!empId &&
    !!selfEmployee &&
    user.is_manager &&
    empId !== selfEmployee.employee_id &&
    directReports.some((r) => r.employee_id === empId);
  const canWriteManagerFeedback = user.role === "admin" || isDirectReport;
  const canEditManagerReview = user.role === "admin" || isDirectReport;
  const canEditGoalSelfAssessment = isSelf || user.role === "admin";

  const loadData = useCallback(async () => {
    if (!empId) return;
    const [fbRes, msRes, revRes, statsRes] = await Promise.all([
      apiFetch(`/api/employees/${empId}/feedback`),
      apiFetch(`/api/employees/${empId}/milestones`),
      apiFetch(`/api/employees/${empId}/reviews`),
      apiFetch(`/api/feedback/stats?employee_id=${encodeURIComponent(empId)}`),
    ]);
    if (fbRes.ok) setFeedbackList(await fbRes.json());
    if (statsRes.ok) {
      const stats = await statsRes.json();
      setCycleFeedbackCount(stats.current_cycle_entries ?? stats.total_entries ?? 0);
    } else {
      setCycleFeedbackCount(0);
    }
    if (msRes.ok) {
      const ms: Milestone[] = await msRes.json();
      setMilestones(ms);
      const drafts: Record<string, string> = {};
      for (const m of ms) {
        drafts[m.id] = m.employee_self_assessment ?? "";
      }
      setAssessmentDrafts(drafts);
    }
    if (revRes.ok) {
      const reviews: PerformanceReview[] = await revRes.json();
      const mid = reviews.find((r) => r.review_type === "mid_year") ?? null;
      const ye = reviews.find((r) => r.review_type === "year_end") ?? null;
      setMidYearReview(mid);
      setYearEndReview(ye);
    }
  }, [empId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const loadFeedbackSummary = useCallback(
    async (reviewType: ReviewType) => {
      if (!empId || !canEditManagerReview) {
        setFeedbackSummary(null);
        return;
      }
      const res = await apiFetch(
        `/api/feedback/summary?employee_id=${encodeURIComponent(empId)}&review_type=${reviewType}`
      );
      if (res.ok) {
        setFeedbackSummary(await res.json());
      } else {
        setFeedbackSummary(null);
      }
    },
    [empId, canEditManagerReview]
  );

  const activeReview = tab === "mid_year" ? midYearReview : tab === "year_end" ? yearEndReview : null;

  useEffect(() => {
    if ((tab === "mid_year" || tab === "year_end") && canEditManagerReview) {
      loadFeedbackSummary(tab);
    } else {
      setFeedbackSummary(null);
    }
  }, [tab, empId, canEditManagerReview, loadFeedbackSummary]);

  useEffect(() => {
    if (activeReview) {
      setReviewDraft({
        employee_self_assessment: activeReview.employee_self_assessment ?? "",
        manager_summary: activeReview.manager_summary ?? "",
        development_areas: activeReview.development_areas ?? "",
        overall_rating: activeReview.overall_rating ?? "",
      });
    }
  }, [activeReview?.id, activeReview?.updated_at]);

  useEffect(() => {
    if (!empId) return;
    if (canWriteManagerFeedback) {
      setTab("continuous");
    } else if (isSelf) {
      setTab("self_assessment");
    }
  }, [empId]);

  const saveGoalSelfAssessment = async (milestoneId: string) => {
    if (!empId) return;
    const text = assessmentDrafts[milestoneId]?.trim();
    if (!text) {
      addToast("Enter your self-assessment for this goal", "warning");
      return;
    }
    setAssessmentSaving(milestoneId);
    try {
      const res = await apiFetch(
        `/api/employees/${empId}/milestones/${milestoneId}/self-assessment`,
        {
          method: "PUT",
          body: JSON.stringify({ employee_self_assessment: text }),
        }
      );
      if (!res.ok) {
        const err = await res.json();
        addToast(err.detail || "Failed to save self-assessment", "error");
        return;
      }
      addToast("Goal self-assessment saved", "success");
      await loadData();
    } catch {
      addToast("Failed to save self-assessment", "error");
    } finally {
      setAssessmentSaving(null);
    }
  };

  const shareFeedback = async (entry: FeedbackEntry) => {
    const res = await apiFetch(`/api/feedback/${entry.id}`, {
      method: "PATCH",
      body: JSON.stringify({ visibility: "shared" }),
    });
    if (res.ok) {
      addToast("Feedback shared with employee", "success");
      loadData();
    } else {
      addToast("Could not update visibility", "error");
    }
  };

  const saveReview = async (reviewType: ReviewType) => {
    if (!empId) return;
    setReviewSaving(true);
    try {
      const body: Record<string, unknown> = {};
      if (isSelf || user.role === "admin") {
        body.employee_self_assessment = reviewDraft.employee_self_assessment;
      }
      if (canEditManagerReview) {
        body.manager_summary = reviewDraft.manager_summary;
        body.development_areas = reviewDraft.development_areas;
        if (reviewType === "year_end" && reviewDraft.overall_rating !== "") {
          body.overall_rating = Number(reviewDraft.overall_rating);
        }
      }
      const res = await apiFetch(`/api/employees/${empId}/reviews/${reviewType}`, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json();
        addToast(err.detail || "Failed to save review", "error");
        return;
      }
      addToast("Review saved", "success");
      await loadData();
    } catch {
      addToast("Failed to save review", "error");
    } finally {
      setReviewSaving(false);
    }
  };

  const generateFeedbackSummary = async (reviewType: ReviewType) => {
    if (!empId) return;
    setGeneratingSummary(true);
    try {
      const res = await apiFetch("/api/feedback/summarise", {
        method: "POST",
        body: JSON.stringify({ employee_id: empId, review_type: reviewType }),
      });
      if (res.status === 503) {
        const err = await res.json().catch(() => ({}));
        addToast(typeof err.detail === "string" ? err.detail : "AI unavailable", "error");
        return;
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        addToast(typeof err.detail === "string" ? err.detail : "Summary generation failed", "error");
        return;
      }
      const data = await res.json();
      if (data.reason === "no_feedback") {
        addToast("No continuous feedback entries to summarise yet", "warning");
        return;
      }
      addToast("AI feedback summary generated", "success");
      await loadFeedbackSummary(reviewType);
    } catch {
      addToast("Failed to generate summary", "error");
    } finally {
      setGeneratingSummary(false);
    }
  };

  const draftFromFeedback = async (reviewType: ReviewType) => {
    if (!empId) return;
    const entryCount = Math.max(feedbackList.length, cycleFeedbackCount);
    if (entryCount === 0) {
      addToast("Add continuous feedback before drafting a review", "warning");
      return;
    }
    setDrafting(true);
    try {
      const res = await apiFetch(
        `/api/employees/${empId}/reviews/${reviewType}/draft-from-feedback`,
        { method: "POST" }
      );
      if (res.status === 503) {
        const err = await res.json().catch(() => ({}));
        addToast(typeof err.detail === "string" ? err.detail : "AI service unavailable", "error");
        return;
      }
      if (!res.ok) {
        const err = await res.json();
        addToast(err.detail || "Draft generation failed", "error");
        return;
      }
      const data = await res.json();
      setReviewDraft((d) => ({
        ...d,
        manager_summary: data.manager_summary ?? d.manager_summary,
        development_areas: data.development_areas ?? d.development_areas,
      }));
      addToast(
        `Draft created from ${data.feedback_entries_used} feedback entries`,
        "success"
      );
    } catch {
      addToast("Failed to generate draft", "error");
    } finally {
      setDrafting(false);
    }
  };

  const submitReview = async (reviewType: ReviewType) => {
    if (!empId) return;
    await saveReview(reviewType);
    const res = await apiFetch(`/api/employees/${empId}/reviews/${reviewType}/submit`, {
      method: "POST",
    });
    if (res.ok) {
      addToast("Review submitted", "success");
      loadData();
    } else {
      const err = await res.json();
      addToast(err.detail || "Submit failed", "error");
    }
  };

  const lockReview = async (reviewType: ReviewType) => {
    if (!empId) return;
    const res = await apiFetch(`/api/employees/${empId}/reviews/${reviewType}/lock`, {
      method: "POST",
    });
    if (res.ok) {
      addToast("Review locked", "success");
      loadData();
    } else {
      const err = await res.json();
      addToast(err.detail || "Lock failed", "error");
    }
  };

  if (!activeEmployee) {
    return (
      <div className="text-center py-12 text-gray-500">
        <p>Select an employee to view or capture feedback and reviews.</p>
      </div>
    );
  }

  const tabs: { id: Tab; label: string; show: boolean }[] = [
    { id: "self_assessment", label: "Goal Self-Assessment", show: true },
    {
      id: "continuous",
      label: canWriteManagerFeedback ? "Feedback history" : "Manager feedback",
      show: canWriteManagerFeedback || feedbackList.length > 0,
    },
    { id: "mid_year", label: "Mid-year Review", show: true },
    { id: "year_end", label: "Year-end Review", show: true },
  ].filter((t): t is { id: Tab; label: string; show: boolean } => t.show);

  return (
    <div>
      <h1 className="page-title mb-1">Feedback & Reviews</h1>
      <p className="text-sm text-gray-500 mb-6">
        {canWriteManagerFeedback
          ? `${activeEmployee.name} · review history and complete formal reviews`
          : isSelf
            ? "Reflect on your goals and review manager feedback"
            : `${activeEmployee.name} · reviews and goal assessments`}
      </p>

      <div className="flex gap-2 mb-6 border-b border-gray-200">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t.id
                ? "border-brand-400 text-brand-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "self_assessment" && (
        <div className="space-y-4">
          <p className="text-sm text-gray-600">
            {canEditGoalSelfAssessment
              ? "Assess your progress against each calibrated goal."
              : "Employee self-assessments against their goals."}
          </p>
          {milestones.length === 0 ? (
            <p className="text-sm text-gray-400 py-6">
              No goals set yet. Calibrate milestones first under SMART Milestones.
            </p>
          ) : (
            milestones.map((m) => (
              <div key={m.id} className="bg-white border border-gray-200 rounded-xl p-4">
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div>
                    <p className="text-sm font-medium text-gray-800">{m.raw_goal}</p>
                    {m.smart_goal && (
                      <p className="text-xs text-gray-500 mt-1">{m.smart_goal}</p>
                    )}
                  </div>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full flex-shrink-0 ${
                      m.status === "calibrated"
                        ? "bg-brand-50 text-brand-600"
                        : "bg-amber-50 text-amber-600"
                    }`}
                  >
                    {m.status === "calibrated" ? "Calibrated" : "Needs work"}
                  </span>
                </div>
                {canEditGoalSelfAssessment ? (
                  <>
                    <AchievementsPanel
                      employeeId={empId!}
                      canEdit
                      scope="goal"
                      milestoneId={m.id}
                      onApply={(text) =>
                        setAssessmentDrafts((d) => {
                          const current = d[m.id] ?? "";
                          const next = current.trim() ? `${current.trim()}\n\n${text}` : text;
                          return { ...d, [m.id]: next };
                        })
                      }
                      onError={(msg) => addToast(msg, "warning")}
                    />
                    <textarea
                      value={assessmentDrafts[m.id] ?? ""}
                      onChange={(e) =>
                        setAssessmentDrafts((d) => ({ ...d, [m.id]: e.target.value }))
                      }
                      rows={4}
                      placeholder="How are you progressing against this goal? Include evidence and outcomes…"
                      className="w-full border border-gray-200 rounded-lg p-3 text-sm focus:ring-2 focus:ring-brand-400 focus:outline-none"
                    />
                    <button
                      onClick={() => saveGoalSelfAssessment(m.id)}
                      disabled={assessmentSaving === m.id}
                      className="mt-2 bg-brand-400 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-brand-600 disabled:opacity-50"
                    >
                      {assessmentSaving === m.id ? "Saving…" : "Save self-assessment"}
                    </button>
                  </>
                ) : (
                  <p className="text-sm text-gray-600 whitespace-pre-wrap">
                    {m.employee_self_assessment?.trim()
                      ? m.employee_self_assessment
                      : "No self-assessment submitted for this goal yet."}
                  </p>
                )}
                {m.self_assessment_updated_at && (
                  <p className="text-xs text-gray-400 mt-2">
                    Updated {formatDate(m.self_assessment_updated_at)}
                  </p>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {tab === "continuous" && (
        <div className="space-y-6">
          {canWriteManagerFeedback && (
            <div className="bg-brand-50 border border-brand-100 rounded-xl p-4 flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-brand-900">
                Log new feedback with bias checks and optional AI synthesis in Continuous Feedback.
              </p>
              <button
                type="button"
                onClick={() => setActivePanel?.("continuous_feedback")}
                className="text-sm bg-brand-400 text-white px-4 py-2 rounded-lg hover:bg-brand-600"
              >
                Log feedback →
              </button>
            </div>
          )}
          {!canWriteManagerFeedback && (
            <p className="text-sm text-gray-600">
              Feedback from your manager. Only shared feedback is visible to you.
            </p>
          )}
          <div className="bg-white border border-gray-200 rounded-xl p-5">
            <h2 className="text-sm font-medium text-gray-500 mb-3">
              {canWriteManagerFeedback ? "Feedback history" : "Manager feedback"}
            </h2>
            {feedbackList.length === 0 ? (
              <p className="text-sm text-gray-400 py-4">
                {canWriteManagerFeedback
                  ? "No feedback captured yet."
                  : "No shared feedback from your manager yet."}
              </p>
            ) : (
              <div className="space-y-3 max-h-64 overflow-y-auto">
                {feedbackList.map((entry) => (
                  <div key={entry.id} className="border border-gray-100 rounded-lg p-3">
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span className="text-xs font-medium text-gray-600">
                        {entry.author_name} · {formatDate(entry.created_at)}
                      </span>
                      <div className="flex items-center gap-2">
                        {entry.visibility === "manager_only" && (
                          <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">
                            Manager only
                          </span>
                        )}
                        {entry.visibility === "shared" && (
                          <span className="text-xs bg-brand-50 text-brand-600 px-2 py-0.5 rounded-full">
                            Shared
                          </span>
                        )}
                        {entry.visibility === "manager_only" && canEditManagerReview && (
                          <button
                            onClick={() => shareFeedback(entry)}
                            className="text-xs text-brand-600 hover:underline flex items-center gap-1"
                          >
                            <Share2 className="w-3 h-3" /> Share
                          </button>
                        )}
                      </div>
                    </div>
                    <p className="text-sm text-gray-700">{entry.raw_text}</p>
                    {entry.synthesized_commentary && (
                      <p className="text-sm text-gray-500 mt-2 italic border-l-2 border-brand-200 pl-2">
                        {entry.synthesized_commentary}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {(tab === "mid_year" || tab === "year_end") && activeReview && (
        <ReviewForm
          review={activeReview}
          reviewType={tab}
          draft={reviewDraft}
          setDraft={setReviewDraft}
          isSelf={!!isSelf}
          canEditManager={!!canEditManagerReview}
          isAdmin={user.role === "admin"}
          employeeId={empId!}
          saving={reviewSaving}
          drafting={drafting}
          onDraftFromFeedback={() => draftFromFeedback(tab)}
          onGenerateSummary={() => generateFeedbackSummary(tab)}
          onSave={() => saveReview(tab)}
          onSubmit={() => submitReview(tab)}
          onLock={() => lockReview(tab)}
          feedbackCount={Math.max(feedbackList.length, cycleFeedbackCount)}
          feedbackSummary={feedbackSummary}
          generatingSummary={generatingSummary}
          goalAssessments={milestones}
          onError={(msg) => addToast(msg, "warning")}
        />
      )}
    </div>
  );
}

function ReviewForm({
  review,
  reviewType,
  draft,
  setDraft,
  isSelf,
  canEditManager,
  isAdmin,
  employeeId,
  saving,
  drafting,
  onDraftFromFeedback,
  onGenerateSummary,
  onSave,
  onSubmit,
  onLock,
  feedbackCount,
  feedbackSummary,
  generatingSummary,
  goalAssessments,
  onError,
}: {
  review: PerformanceReview;
  reviewType: ReviewType;
  draft: {
    employee_self_assessment: string;
    manager_summary: string;
    development_areas: string;
    overall_rating: string | number;
  };
  setDraft: React.Dispatch<React.SetStateAction<typeof draft>>;
  isSelf: boolean;
  canEditManager: boolean;
  isAdmin: boolean;
  employeeId: string;
  saving: boolean;
  drafting: boolean;
  onDraftFromFeedback: () => void;
  onGenerateSummary: () => void;
  onSave: () => void;
  onSubmit: () => void;
  onLock: () => void;
  feedbackCount: number;
  feedbackSummary: FeedbackSummary | null;
  generatingSummary: boolean;
  goalAssessments: Milestone[];
  onError: (message: string) => void;
}) {
  const locked = review.status === "locked";
  const submitted = review.status === "submitted";
  const title = reviewType === "mid_year" ? "Mid-year Review" : "Year-end Review";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-medium text-slate-900">{title}</h2>
          <p className="text-sm text-gray-500">
            {review.cycle} · {feedbackCount} continuous feedback entries on record
          </p>
        </div>
        <span className={`text-xs px-3 py-1 rounded-full font-medium ${statusBadge(review.status)}`}>
          {review.status}
        </span>
      </div>

      {(isSelf || isAdmin) && (
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          {goalAssessments.some((m) => m.employee_self_assessment?.trim()) && (
            <div className="mb-4 pb-4 border-b border-gray-100">
              <p className="text-xs font-medium text-gray-500 mb-2">Goal self-assessments</p>
              <div className="space-y-2">
                {goalAssessments
                  .filter((m) => m.employee_self_assessment?.trim())
                  .map((m) => (
                    <div key={m.id} className="text-sm">
                      <p className="font-medium text-gray-700">{m.raw_goal}</p>
                      <p className="text-gray-600 mt-0.5">{m.employee_self_assessment}</p>
                    </div>
                  ))}
              </div>
            </div>
          )}
          <label className="text-sm font-medium text-gray-700 block mb-2">
            Overall employee self-assessment
          </label>
          {(isSelf || isAdmin) && !locked && (
            <div className="mb-3">
              <AchievementsPanel
                employeeId={employeeId}
                canEdit={isSelf || isAdmin}
                scope="overall"
                onApply={(text) =>
                  setDraft((d) => {
                    const current = d.employee_self_assessment.trim();
                    const next = current ? `${current}\n\n${text}` : text;
                    return { ...d, employee_self_assessment: next };
                  })
                }
                onError={onError}
              />
            </div>
          )}
          <textarea
            value={draft.employee_self_assessment}
            onChange={(e) =>
              setDraft((d) => ({ ...d, employee_self_assessment: e.target.value }))
            }
            disabled={locked || (!isSelf && !isAdmin)}
            rows={5}
            className="w-full border border-gray-200 rounded-lg p-3 text-sm disabled:bg-gray-50"
            placeholder="Reflect on progress against goals, strengths, and areas to develop…"
          />
        </div>
      )}

      {canEditManager && (
        <>
          {!locked && (
            <div className="rounded-xl border border-brand-100 bg-brand-50/40 p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-brand-500" />
                <h3 className="text-sm font-medium text-brand-900">AI-assisted review</h3>
              </div>
              <p className="text-xs text-brand-800/80">
                Generate a cycle summary from continuous feedback, then draft the manager
                summary and development areas.
              </p>
              {feedbackSummary?.content ? (
                <div className="bg-white rounded-lg border border-brand-100 p-3 space-y-2">
                  <div className="flex flex-wrap gap-2 text-xs text-gray-500">
                    <span>{feedbackSummary.review_cycle}</span>
                    {feedbackSummary.confidence && (
                      <span>· Confidence: {feedbackSummary.confidence}</span>
                    )}
                    {feedbackSummary.entry_count > 0 && (
                      <span>· {feedbackSummary.entry_count} entries</span>
                    )}
                  </div>
                  <p className="text-sm text-gray-700 whitespace-pre-wrap line-clamp-4">
                    {feedbackSummary.content}
                  </p>
                  {feedbackSummary.themes?.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {feedbackSummary.themes.slice(0, 4).map((t) => (
                        <span
                          key={t}
                          className="text-[10px] bg-brand-50 text-brand-700 px-2 py-0.5 rounded-full"
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-xs text-gray-600">
                  {feedbackCount > 0
                    ? `${feedbackCount} feedback ${feedbackCount === 1 ? "entry" : "entries"} ready to summarise.`
                    : "Log continuous feedback first, then generate an AI summary."}
                </p>
              )}
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={onGenerateSummary}
                  disabled={generatingSummary || drafting || feedbackCount === 0}
                  className="flex items-center gap-1.5 text-xs border border-brand-200 text-brand-700 px-3 py-1.5 rounded-lg hover:bg-brand-50 disabled:opacity-50"
                >
                  <Sparkles className="w-3 h-3" />
                  {generatingSummary
                    ? "Summarising…"
                    : feedbackSummary?.content
                      ? "Regenerate summary"
                      : "Generate AI summary"}
                </button>
                <button
                  type="button"
                  onClick={onDraftFromFeedback}
                  disabled={drafting || generatingSummary || feedbackCount === 0}
                  className="text-xs bg-brand-400 text-white px-3 py-1.5 rounded-lg hover:bg-brand-600 disabled:opacity-50"
                >
                  {drafting ? "Drafting…" : "Draft manager review"}
                </button>
                {feedbackSummary?.content && (
                  <button
                    type="button"
                    onClick={() =>
                      setDraft((d) => {
                        const block = feedbackSummary.content.trim();
                        const current = d.manager_summary.trim();
                        const next = current ? `${current}\n\n${block}` : block;
                        return { ...d, manager_summary: next };
                      })
                    }
                    className="text-xs border border-gray-200 text-gray-700 px-3 py-1.5 rounded-lg hover:bg-gray-50"
                  >
                    Insert summary text
                  </button>
                )}
              </div>
            </div>
          )}

          <div className="bg-white border border-gray-200 rounded-xl p-4">
            <label className="text-sm font-medium text-gray-700 block mb-2">
              Manager summary
            </label>
            <textarea
              value={draft.manager_summary}
              onChange={(e) => setDraft((d) => ({ ...d, manager_summary: e.target.value }))}
              disabled={locked}
              rows={5}
              className="w-full border border-gray-200 rounded-lg p-3 text-sm disabled:bg-gray-50"
              placeholder="Summarise performance, incorporating continuous feedback…"
            />
          </div>
          <div className="bg-white border border-gray-200 rounded-xl p-4">
            <label className="text-sm font-medium text-gray-700 block mb-2">
              Development areas
            </label>
            <textarea
              value={draft.development_areas}
              onChange={(e) => setDraft((d) => ({ ...d, development_areas: e.target.value }))}
              disabled={locked}
              rows={3}
              className="w-full border border-gray-200 rounded-lg p-3 text-sm disabled:bg-gray-50"
            />
          </div>
          {reviewType === "year_end" && (
            <div className="bg-white border border-gray-200 rounded-xl p-4 max-w-xs">
              <label className="text-sm font-medium text-gray-700 block mb-2">
                Overall rating (1–5)
                <span className="text-xs font-normal text-gray-500 ml-1">Required at submit</span>
              </label>
              <select
                value={draft.overall_rating}
                onChange={(e) => setDraft((d) => ({ ...d, overall_rating: e.target.value }))}
                disabled={locked}
                className="w-full border border-gray-200 rounded-lg p-2 text-sm disabled:bg-gray-50"
              >
                <option value="">Not rated</option>
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </div>
          )}
        </>
      )}

      {canEditManager && reviewType === "mid_year" && (
        <p className="text-xs text-gray-500">
          Mid-year reviews focus on progress and development — no overall rating is required.
        </p>
      )}

      {!locked && (
        <div className="flex flex-wrap gap-2">
          <button
            onClick={onSave}
            disabled={saving || drafting}
            className="bg-brand-400 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-brand-600 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save draft"}
          </button>
          {!submitted && (
            <button
              onClick={onSubmit}
              className="border border-brand-200 text-brand-700 px-4 py-2 rounded-lg text-sm hover:bg-brand-50"
            >
              Submit review
            </button>
          )}
          {isAdmin && submitted && (
            <button
              onClick={onLock}
              className="flex items-center gap-1 border border-gray-200 text-gray-600 px-4 py-2 rounded-lg text-sm hover:bg-gray-50"
            >
              <Lock className="w-4 h-4" /> Lock review
            </button>
          )}
        </div>
      )}
    </div>
  );
}
