import { useCallback, useEffect, useState } from "react";
import { Award, Sparkles } from "lucide-react";
import { apiFetch } from "../hooks/api";
import type { EmployeeAchievement } from "../types";

const TYPE_LABELS: Record<string, string> = {
  certification: "Certification",
  accomplishment: "Accomplishment",
  training: "Training",
  award: "Award",
  project: "Project",
  other: "Other",
};

interface Props {
  employeeId: string;
  canEdit: boolean;
  scope: "goal" | "overall";
  milestoneId?: string;
  onApply: (text: string) => void;
  onError?: (message: string) => void;
}

export default function AchievementsPanel({
  employeeId,
  canEdit,
  scope,
  milestoneId,
  onApply,
  onError,
}: Props) {
  const [achievements, setAchievements] = useState<EmployeeAchievement[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [suggesting, setSuggesting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiFetch(`/api/employees/${employeeId}/achievements`);
      if (res.ok) {
        setAchievements(await res.json());
      } else {
        setAchievements([]);
      }
    } catch {
      setAchievements([]);
    } finally {
      setLoading(false);
    }
  }, [employeeId]);

  useEffect(() => {
    load();
  }, [load]);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const insertSelected = () => {
    const lines = achievements
      .filter((a) => selected.has(a.achievement_id))
      .map((a) => {
        const label = TYPE_LABELS[a.type] ?? a.type;
        let line = `• [${label}] ${a.title}`;
        if (a.description) line += ` — ${a.description}`;
        if (a.issuer_or_context) line += ` (${a.issuer_or_context})`;
        return line;
      });
    if (lines.length === 0) {
      onError?.("Select at least one achievement to insert");
      return;
    }
    onApply(lines.join("\n"));
  };

  const suggestDraft = async () => {
    setSuggesting(true);
    try {
      const res = await apiFetch(`/api/employees/${employeeId}/self-assessment/suggest`, {
        method: "POST",
        body: JSON.stringify({
          scope,
          milestone_id: scope === "goal" ? milestoneId : null,
          achievement_ids: Array.from(selected),
        }),
      });
      if (res.status === 503) {
        onError?.("AI suggestion unavailable — check LLM is running");
        return;
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        onError?.(typeof err.detail === "string" ? err.detail : "Suggestion failed");
        return;
      }
      const data = await res.json();
      if (data.suggested_text) {
        onApply(data.suggested_text);
      }
    } catch {
      onError?.("Suggestion failed");
    } finally {
      setSuggesting(false);
    }
  };

  if (loading) {
    return <p className="text-xs text-gray-400">Loading accomplishments…</p>;
  }

  if (achievements.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50/50 p-3">
        <p className="text-xs text-gray-500">
          No certifications or accomplishments on file yet for this cycle.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-brand-100 bg-brand-50/40 p-3 space-y-2">
      <div className="flex items-center gap-2">
        <Award className="w-3.5 h-3.5 text-brand-500" />
        <p className="text-xs font-medium text-brand-800">
          Evidence from your profile ({achievements.length})
        </p>
      </div>
      <ul className="space-y-1.5 max-h-40 overflow-y-auto">
        {achievements.map((a) => (
          <li key={a.achievement_id}>
            <label className="flex items-start gap-2 text-xs cursor-pointer hover:bg-white/60 rounded p-1">
              {canEdit ? (
                <input
                  type="checkbox"
                  checked={selected.has(a.achievement_id)}
                  onChange={() => toggle(a.achievement_id)}
                  className="mt-0.5"
                />
              ) : null}
              <span>
                <span className="font-medium text-gray-800">{a.title}</span>
                <span className="text-gray-500 ml-1">
                  · {TYPE_LABELS[a.type] ?? a.type}
                  {a.achieved_at ? ` · ${a.achieved_at.slice(0, 10)}` : ""}
                </span>
                {a.description && (
                  <span className="block text-gray-600 mt-0.5">{a.description}</span>
                )}
              </span>
            </label>
          </li>
        ))}
      </ul>
      {canEdit && (
        <div className="flex flex-wrap gap-2 pt-1">
          <button
            type="button"
            onClick={insertSelected}
            disabled={selected.size === 0}
            className="text-xs border border-brand-200 text-brand-700 px-2 py-1 rounded-lg hover:bg-brand-50 disabled:opacity-50"
          >
            Insert selected
          </button>
          <button
            type="button"
            onClick={suggestDraft}
            disabled={suggesting}
            className="text-xs flex items-center gap-1 bg-brand-400 text-white px-2 py-1 rounded-lg hover:bg-brand-600 disabled:opacity-50"
          >
            <Sparkles className="w-3 h-3" />
            {suggesting ? "Drafting…" : "Suggest draft with AI"}
          </button>
        </div>
      )}
    </div>
  );
}
