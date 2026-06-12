import { useCallback, useEffect, useMemo, useState } from "react";
import { Check, Pencil, Sparkles, Trash2, X } from "lucide-react";
import { apiFetch } from "../hooks/api";
import type { Employee, Milestone, OKRDoc, OkrAssignment, ToastType } from "../types";
import { REQUIRED_GOAL_COUNT, canManageEmployeeGoals } from "../utils/goals";

interface Props {
  activeEmployee: Employee | null;
  selfEmployee?: Employee | null;
  setActiveEmployee?: (emp: Employee | null) => void;
  user?: { role?: string; is_manager?: boolean; employee_id?: string | null };
  directReports?: Employee[];
  editMilestone?: Milestone | null;
  clearEditMilestone?: () => void;
  addToast: (message: string, type?: ToastType) => void;
}

const categoryColors: Record<string, string> = {
  Engineering: "bg-brand-100 text-brand-700",
  Sales: "bg-blue-100 text-blue-700",
  People: "bg-purple-100 text-purple-700",
  Product: "bg-amber-100 text-amber-700",
  Security: "bg-red-100 text-red-700",
  "Customer Success": "bg-orange-100 text-orange-700",
  Finance: "bg-green-100 text-green-700",
  Other: "bg-gray-100 text-gray-700",
};

function statusLabel(status: string): string {
  if (status === "suggested") return "Awaiting your review";
  if (status === "calibrated") return "Calibrated";
  if (status === "needs_work") return "Needs work";
  return status;
}

export default function SmartCalibrator({
  activeEmployee,
  user,
  directReports = [],
  editMilestone,
  clearEditMilestone,
  addToast,
}: Props) {
  const canManage = canManageEmployeeGoals(user, activeEmployee, directReports);
  const isSelf =
    !!activeEmployee &&
    !!user?.employee_id &&
    activeEmployee.employee_id === user.employee_id;

  const [assignments, setAssignments] = useState<OkrAssignment[]>([]);
  const [companyOkrs, setCompanyOkrs] = useState<OKRDoc[]>([]);
  const [goals, setGoals] = useState<Milestone[]>([]);
  const [suggestionText, setSuggestionText] = useState("");
  const [linkedOkrId, setLinkedOkrId] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [editingGoalId, setEditingGoalId] = useState<string | null>(null);
  const [calibrationGaps, setCalibrationGaps] = useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState(false);
  const [draftingSuggestion, setDraftingSuggestion] = useState(false);

  const loadAll = useCallback(() => {
    if (!activeEmployee?.employee_id) {
      setAssignments([]);
      setGoals([]);
      return;
    }
    const id = activeEmployee.employee_id;
    apiFetch(`/api/employees/${id}/okr-assignments`)
      .then((r) => (r.ok ? r.json() : []))
      .then(setAssignments)
      .catch(() => setAssignments([]));
    apiFetch(`/api/employees/${id}/milestones`)
      .then((r) => (r.ok ? r.json() : []))
      .then(setGoals)
      .catch(() => setGoals([]));
  }, [activeEmployee?.employee_id]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (!editMilestone) return;
    if (
      editMilestone.status === "suggested" ||
      editMilestone.status === "needs_work" ||
      editMilestone.status === "calibrated"
    ) {
      setDrafts((d) => ({
        ...d,
        [editMilestone.id]: editMilestone.raw_goal,
      }));
      if (editMilestone.status === "needs_work" || editMilestone.status === "calibrated") {
        setEditingGoalId(editMilestone.id);
      }
    }
    clearEditMilestone?.();
  }, [editMilestone, clearEditMilestone]);

  useEffect(() => {
    if (!canManage || !activeEmployee) {
      setCompanyOkrs([]);
      return;
    }
    const deptUrl = activeEmployee.department
      ? `/api/okrs?status=active&department=${encodeURIComponent(activeEmployee.department)}`
      : "/api/okrs?status=active";
    apiFetch(deptUrl)
      .then((r) => (r.ok ? r.json() : []))
      .then((data: OKRDoc[]) => {
        if (data.length > 0 || !activeEmployee.department) return data;
        return apiFetch("/api/okrs?status=active")
          .then((r) => (r.ok ? r.json() : []))
          .catch(() => []);
      })
      .then(setCompanyOkrs)
      .catch(() => setCompanyOkrs([]));
  }, [canManage, activeEmployee]);

  const assignedOkrIds = useMemo(
    () => new Set(assignments.map((a) => a.okr_id)),
    [assignments]
  );
  const availableCompanyOkrs = useMemo(
    () => companyOkrs.filter((o) => !assignedOkrIds.has(o.okr_id)),
    [companyOkrs, assignedOkrIds]
  );

  const suggestedGoals = goals.filter((g) => g.status === "suggested");
  const acceptedGoals = goals.filter((g) => g.status !== "suggested");
  const calibratedCount = goals.filter((g) => g.status === "calibrated").length;
  const goalsComplete = calibratedCount >= REQUIRED_GOAL_COUNT;

  const assignOkr = async (okrId: string) => {
    if (!activeEmployee) return;
    const res = await apiFetch(`/api/employees/${activeEmployee.employee_id}/okr-assignments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ okr_id: okrId }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      addToast(typeof err.detail === "string" ? err.detail : "Failed to assign OKR", "error");
      return;
    }
    addToast("OKR assigned to employee", "success");
    loadAll();
  };

  const removeAssignment = async (assignmentId: string) => {
    if (!activeEmployee) return;
    const res = await apiFetch(
      `/api/employees/${activeEmployee.employee_id}/okr-assignments/${assignmentId}`,
      { method: "DELETE" }
    );
    if (!res.ok) {
      addToast("Failed to remove OKR assignment", "error");
      return;
    }
    addToast("OKR assignment removed", "info");
    loadAll();
  };

  const draftGoalSuggestion = async () => {
    if (!activeEmployee) return;
    setDraftingSuggestion(true);
    try {
      const res = await apiFetch(
        `/api/employees/${activeEmployee.employee_id}/goals/draft-suggestion`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            linked_okr_id: linkedOkrId || null,
            manager_notes: suggestionText.trim(),
          }),
        }
      );
      if (res.status === 503) {
        const err = await res.json().catch(() => ({}));
        addToast(typeof err.detail === "string" ? err.detail : "AI unavailable", "error");
        return;
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        addToast(typeof err.detail === "string" ? err.detail : "Failed to draft goal", "error");
        return;
      }
      const data = await res.json();
      if (data.suggested_goal) {
        setSuggestionText(data.suggested_goal);
        addToast("Goal draft ready — review and send to employee", "success");
      }
    } finally {
      setDraftingSuggestion(false);
    }
  };

  const suggestGoal = async () => {
    if (!activeEmployee || !suggestionText.trim()) return;
    setLoading(true);
    try {
      const res = await apiFetch(`/api/employees/${activeEmployee.employee_id}/goals/suggest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          raw_goal: suggestionText.trim(),
          linked_okr_id: linkedOkrId || null,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        addToast(typeof err.detail === "string" ? err.detail : "Failed to suggest goal", "error");
        return;
      }
      addToast("Goal suggested to employee", "success");
      setSuggestionText("");
      setLinkedOkrId("");
      loadAll();
    } finally {
      setLoading(false);
    }
  };

  const deleteSuggestion = async (goalId: string) => {
    if (!activeEmployee || !confirm("Remove this goal suggestion?")) return;
    const res = await apiFetch(
      `/api/employees/${activeEmployee.employee_id}/goals/${goalId}`,
      { method: "DELETE" }
    );
    if (!res.ok) {
      addToast("Failed to delete suggestion", "error");
      return;
    }
    addToast("Suggestion removed", "info");
    loadAll();
  };

  const acceptGoal = async (goal: Milestone, useOriginal = false) => {
    if (!activeEmployee) return;
    const revised = useOriginal
      ? goal.manager_suggestion || goal.raw_goal
      : (drafts[goal.id] ?? goal.raw_goal).trim();
    if (!revised) {
      addToast("Goal text is empty", "error");
      return;
    }
    setLoading(true);
    try {
      const res = await apiFetch(
        `/api/employees/${activeEmployee.employee_id}/goals/${goal.id}/accept`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ revised_goal: revised }),
        }
      );
      if (res.status === 503) {
        const err = await res.json().catch(() => ({}));
        addToast(typeof err.detail === "string" ? err.detail : "AI unavailable", "error");
        return;
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        addToast(typeof err.detail === "string" ? err.detail : "Failed to accept goal", "error");
        return;
      }
      const data = await res.json();
      addToast(
        data.status === "calibrated" ? "Goal accepted and calibrated" : "Goal accepted — needs refinement",
        data.status === "calibrated" ? "success" : "warning"
      );
      loadAll();
    } finally {
      setLoading(false);
    }
  };

  const saveRevision = async (goal: Milestone) => {
    if (!activeEmployee) return;
    const text = (drafts[goal.id] ?? goal.raw_goal).trim();
    const res = await apiFetch(
      `/api/employees/${activeEmployee.employee_id}/goals/${goal.id}/revise`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ raw_goal: text }),
      }
    );
    if (!res.ok) {
      addToast("Failed to save revision", "error");
      return;
    }
    addToast("Revision saved — accept when ready", "success");
    loadAll();
  };

  const recalibrateGoal = async (goal: Milestone) => {
    if (!activeEmployee) return;
    const text = (drafts[goal.id] ?? goal.raw_goal).trim();
    if (!text) {
      addToast("Goal text is empty", "error");
      return;
    }
    setLoading(true);
    try {
      const res = await apiFetch("/api/calibrate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          goal: text,
          employee_id: activeEmployee.employee_id,
          milestone_id: goal.id,
        }),
      });
      if (res.status === 503) {
        const err = await res.json().catch(() => ({}));
        addToast(typeof err.detail === "string" ? err.detail : "AI unavailable", "error");
        return;
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        addToast(typeof err.detail === "string" ? err.detail : "Re-calibration failed", "error");
        return;
      }
      const data = await res.json();
      if (Array.isArray(data.gaps) && data.gaps.length > 0) {
        setCalibrationGaps((g) => ({ ...g, [goal.id]: data.gaps }));
      }
      addToast(
        data.status === "calibrated"
          ? goal.status === "calibrated"
            ? "Revision submitted — goal re-calibrated"
            : "Goal calibrated successfully"
          : "Still needs work — see feedback below",
        data.status === "calibrated" ? "success" : "warning"
      );
      if (data.status === "calibrated") {
        setEditingGoalId(null);
      }
      loadAll();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">OKRs & Goals</h1>
        {activeEmployee ? (
          <p className="text-sm text-gray-500 mt-1">
            {canManage ? (
              <>
                Manage <span className="font-medium text-gray-700">{activeEmployee.name}</span> — assign
                company OKRs, then suggest individual goals for them to accept.
              </>
            ) : isSelf ? (
              <>
                Review OKRs assigned by your manager, accept suggested goals, or propose revisions to
                calibrated goals when priorities shift.
              </>
            ) : (
              <>Viewing {activeEmployee.name}</>
            )}
          </p>
        ) : (
          <p className="text-sm text-amber-600 mt-1">Select an employee profile.</p>
        )}
      </div>

      {activeEmployee && (
        <div
          className={`rounded-xl border p-4 ${
            goalsComplete ? "bg-emerald-50 border-emerald-200" : "bg-amber-50 border-amber-200"
          }`}
        >
          <div className="flex flex-wrap gap-4 text-sm">
            <span>
              OKRs assigned: <strong>{assignments.length}</strong> / {REQUIRED_GOAL_COUNT}
            </span>
            <span>
              Goals calibrated: <strong>{calibratedCount}</strong> / {REQUIRED_GOAL_COUNT}
            </span>
            {suggestedGoals.length > 0 && (
              <span className="text-blue-700">
                {suggestedGoals.length} suggestion{suggestedGoals.length > 1 ? "s" : ""} pending
              </span>
            )}
          </div>
        </div>
      )}

      {/* ── Assigned OKRs (alignment) ── */}
      <div className="bg-white border border-gray-200 rounded-xl p-5">
        <h2 className="text-sm font-medium text-gray-700 mb-1">Assigned OKRs</h2>
        <p className="text-xs text-gray-500 mb-4">
          Strategic OKRs from the company catalog — set by {canManage ? "you" : "your manager"}. These define
          alignment; individual goals below translate them into action.
        </p>

        {assignments.length === 0 ? (
          <p className="text-sm text-gray-400">No OKRs assigned yet.</p>
        ) : (
          <div className="space-y-2 mb-4">
            {assignments.map((a) => (
              <div
                key={a.id}
                className="flex items-start justify-between gap-3 p-3 rounded-lg border border-gray-100"
              >
                <div>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full ${
                      categoryColors[a.category] ?? categoryColors.Other
                    }`}
                  >
                    {a.category}
                  </span>
                  <p className="text-sm font-medium text-gray-800 mt-1">{a.title}</p>
                  <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{a.description}</p>
                </div>
                {canManage && (
                  <button
                    onClick={() => removeAssignment(a.id)}
                    className="text-red-500 hover:text-red-700 p-1"
                    title="Remove assignment"
                  >
                    <X className="w-4 h-4" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {canManage && assignments.length < REQUIRED_GOAL_COUNT && (
          <div>
            <p className="text-xs font-medium text-gray-500 mb-2">Assign from company OKRs</p>
            {availableCompanyOkrs.length === 0 ? (
              <p className="text-xs text-gray-400">No more company OKRs available to assign.</p>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-48 overflow-y-auto">
                {availableCompanyOkrs.map((okr) => (
                  <button
                    key={okr.okr_id}
                    type="button"
                    onClick={() => assignOkr(okr.okr_id)}
                    className="text-left p-3 rounded-lg border border-gray-100 hover:border-brand-300 hover:bg-brand-50"
                  >
                    <span className="text-xs text-gray-400">{okr.category}</span>
                    <p className="text-sm font-medium text-gray-800">{okr.title}</p>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Manager: suggest goals ── */}
      {canManage && activeEmployee && goals.length < REQUIRED_GOAL_COUNT && (
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h2 className="text-sm font-medium text-gray-700 mb-1">Suggest a goal</h2>
          <p className="text-xs text-gray-500 mb-3">
            Propose an individual goal. Use AI to draft from assigned OKRs, or write your own. The
            employee will review, revise if needed, and accept it.
          </p>
          {assignments.length > 0 && (
            <select
              value={linkedOkrId}
              onChange={(e) => setLinkedOkrId(e.target.value)}
              className="w-full mb-2 text-sm border border-gray-200 rounded-lg px-3 py-2"
            >
              <option value="">Link to assigned OKR (optional)</option>
              {assignments.map((a) => (
                <option key={a.id} value={a.okr_id}>
                  {a.title}
                </option>
              ))}
            </select>
          )}
          <textarea
            value={suggestionText}
            onChange={(e) => setSuggestionText(e.target.value)}
            rows={3}
            placeholder="Optional: describe focus area, or leave blank and use Draft with AI from assigned OKRs…"
            className="w-full border border-gray-200 rounded-lg p-3 text-sm mb-3"
          />
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={draftGoalSuggestion}
              disabled={loading || draftingSuggestion}
              className="flex items-center gap-1.5 border border-brand-200 text-brand-700 px-4 py-2 rounded-lg text-sm hover:bg-brand-50 disabled:opacity-50"
            >
              <Sparkles className="w-3.5 h-3.5" />
              {draftingSuggestion ? "Drafting…" : "Draft with AI"}
            </button>
            <button
              type="button"
              onClick={suggestGoal}
              disabled={loading || draftingSuggestion || !suggestionText.trim()}
              className="bg-brand-400 text-white px-4 py-2 rounded-lg text-sm disabled:opacity-50"
            >
              Suggest goal to employee
            </button>
          </div>
        </div>
      )}

      {/* ── Pending suggestions (employee view) ── */}
      {isSelf && suggestedGoals.length > 0 && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-5">
          <h2 className="text-sm font-medium text-blue-900 mb-3">Goals suggested by your manager</h2>
          <div className="space-y-4">
            {suggestedGoals.map((g) => {
              const linked = assignments.find((a) => a.okr_id === g.linked_okr_id);
              return (
                <div key={g.id} className="bg-white rounded-lg border border-blue-100 p-4">
                  {linked && (
                    <p className="text-xs text-gray-500 mb-2">
                      Linked OKR: <span className="font-medium">{linked.title}</span>
                    </p>
                  )}
                  <p className="text-xs text-gray-400 mb-1">Manager&apos;s suggestion</p>
                  <p className="text-sm text-gray-600 mb-3 italic">
                    {g.manager_suggestion || g.raw_goal}
                  </p>
                  <label className="text-xs font-medium text-gray-700">Your version (edit if needed)</label>
                  <textarea
                    value={drafts[g.id] ?? g.raw_goal}
                    onChange={(e) => setDrafts((d) => ({ ...d, [g.id]: e.target.value }))}
                    rows={3}
                    className="w-full border border-gray-200 rounded-lg p-2 text-sm mt-1 mb-3"
                  />
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => acceptGoal(g, false)}
                      disabled={loading}
                      className="flex items-center gap-1 text-xs bg-brand-400 text-white px-3 py-1.5 rounded-lg disabled:opacity-50"
                    >
                      <Check className="w-3 h-3" />
                      Accept & calibrate
                    </button>
                    <button
                      onClick={() => acceptGoal(g, true)}
                      disabled={loading}
                      className="text-xs border border-brand-200 text-brand-700 px-3 py-1.5 rounded-lg disabled:opacity-50"
                    >
                      Use manager&apos;s wording
                    </button>
                    <button
                      onClick={() => saveRevision(g)}
                      disabled={loading}
                      className="flex items-center gap-1 text-xs border border-gray-200 px-3 py-1.5 rounded-lg"
                    >
                      <Pencil className="w-3 h-3" />
                      Save draft
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Manager: pending suggestions list ── */}
      {canManage && suggestedGoals.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h2 className="text-sm font-medium text-gray-500 mb-3">Pending suggestions</h2>
          {suggestedGoals.map((g) => (
            <div key={g.id} className="flex items-center justify-between py-2 border-b last:border-0">
              <p className="text-sm text-gray-700 truncate pr-4">{g.raw_goal}</p>
              <button
                onClick={() => deleteSuggestion(g.id)}
                className="text-xs text-red-500 flex items-center gap-1"
              >
                <Trash2 className="w-3 h-3" /> Remove
              </button>
            </div>
          ))}
        </div>
      )}

      {/* ── Accepted / calibrated goals ── */}
      {acceptedGoals.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h2 className="text-sm font-medium text-gray-500 mb-3">
            {isSelf ? "My goals" : "Employee goals"}
          </h2>
          <div className="space-y-3">
            {acceptedGoals.map((g) => {
              const isProposingRevision = isSelf && g.status === "calibrated" && editingGoalId === g.id;
              const isEditingNeedsWork = isSelf && g.status === "needs_work" && editingGoalId === g.id;
              const isEditing = isProposingRevision || isEditingNeedsWork;
              const gaps = calibrationGaps[g.id];

              if (isEditing) {
                return (
                  <div
                    key={g.id}
                    className={`rounded-lg border p-4 ${
                      isProposingRevision
                        ? "border-brand-200 bg-brand-50/40"
                        : "border-amber-200 bg-amber-50/50"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span
                        className={`text-xs font-medium ${
                          isProposingRevision ? "text-brand-800" : "text-amber-700"
                        }`}
                      >
                        {isProposingRevision ? "Propose revision" : "Revise & re-calibrate"}
                      </span>
                      <span className="text-xs text-gray-400">Score: {g.overall_score}</span>
                    </div>
                    {isProposingRevision && (
                      <p className="text-xs text-brand-700 mb-2">
                        Update the goal if scope or priorities changed. Your revision must pass SMART
                        calibration again — your manager will see the updated goal.
                      </p>
                    )}
                    {g.smart_goal?.trim() && (
                      <p className="text-xs text-gray-500 mb-2">
                        AI suggestion: <span className="italic">{g.smart_goal}</span>
                      </p>
                    )}
                    <textarea
                      value={drafts[g.id] ?? g.raw_goal}
                      onChange={(e) => setDrafts((d) => ({ ...d, [g.id]: e.target.value }))}
                      rows={3}
                      className="w-full border border-gray-200 rounded-lg p-2 text-sm mb-2 bg-white"
                    />
                    {gaps && gaps.length > 0 && (
                      <ul className="text-xs text-amber-800 mb-3 list-disc list-inside space-y-0.5">
                        {gaps.map((gap, i) => (
                          <li key={i}>{gap}</li>
                        ))}
                      </ul>
                    )}
                    <div className="flex flex-wrap gap-2">
                      <button
                        onClick={() => recalibrateGoal(g)}
                        disabled={loading}
                        className="flex items-center gap-1 text-xs bg-brand-400 text-white px-3 py-1.5 rounded-lg disabled:opacity-50"
                      >
                        <Check className="w-3 h-3" />
                        {isProposingRevision ? "Submit revision" : "Re-calibrate"}
                      </button>
                      <button
                        onClick={() => setEditingGoalId(null)}
                        disabled={loading}
                        className="text-xs border border-gray-200 px-3 py-1.5 rounded-lg"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                );
              }

              return (
                <div key={g.id} className="flex items-center justify-between p-3 rounded-lg border border-gray-100">
                  <div className="min-w-0 flex-1 pr-3">
                    <p className="text-sm text-gray-800 truncate">
                      {g.smart_goal?.trim() || g.raw_goal}
                    </p>
                    {g.overall_score > 0 && (
                      <p className="text-xs text-gray-400">Score: {g.overall_score}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {isSelf && g.status === "needs_work" && (
                      <button
                        onClick={() => {
                          setEditingGoalId(g.id);
                          setDrafts((d) => ({ ...d, [g.id]: g.raw_goal }));
                        }}
                        className="text-xs text-brand-600 hover:text-brand-700 px-2 py-0.5 rounded border border-brand-200 hover:bg-brand-50"
                      >
                        Revise
                      </button>
                    )}
                    {isSelf && g.status === "calibrated" && (
                      <button
                        onClick={() => {
                          setEditingGoalId(g.id);
                          setDrafts((d) => ({ ...d, [g.id]: g.raw_goal }));
                        }}
                        className="text-xs text-brand-600 hover:text-brand-700 px-2 py-0.5 rounded border border-brand-200 hover:bg-brand-50"
                      >
                        Propose revision
                      </button>
                    )}
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full ${
                        g.status === "calibrated"
                          ? "bg-brand-50 text-brand-600"
                          : "bg-amber-50 text-amber-600"
                      }`}
                    >
                      {statusLabel(g.status)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
