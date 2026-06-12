import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { apiFetch } from "../hooks/api";
import type { BiasFlag, SynthesisResult } from "../types";

interface Props {
  employeeId: string;
  rawText: string;
  onFinalised: (result: SynthesisResult) => void;
  onError: (message: string) => void;
  onApplyRewrite?: (text: string) => void;
}

function flagBorder(severity: BiasFlag["severity"]): string {
  if (severity === "high") return "border-l-4 border-red-500";
  if (severity === "medium") return "border-l-4 border-amber-500";
  return "border-l-4 border-gray-400";
}

export default function FeedbackSynthesiser({
  employeeId,
  rawText,
  onFinalised,
  onError,
  onApplyRewrite,
}: Props) {
  const [synthesising, setSynthesising] = useState(false);
  const [finalising, setFinalising] = useState(false);
  const [result, setResult] = useState<SynthesisResult | null>(null);
  const [finalised, setFinalised] = useState(false);
  const [acknowledged, setAcknowledged] = useState<Record<string, boolean>>({});

  const highFlags = useMemo(
    () => (result?.flags ?? []).filter((f) => f.severity === "high"),
    [result]
  );

  const allHighAcknowledged =
    highFlags.length === 0 || highFlags.every((f) => acknowledged[f.passage]);

  const runSynthesise = async () => {
    if (!rawText.trim()) return;
    setSynthesising(true);
    setFinalised(false);
    setAcknowledged({});
    setResult(null);
    try {
      const res = await apiFetch("/api/synthesise", {
        method: "POST",
        body: JSON.stringify({ feedback: rawText, employee_id: employeeId }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        onError(typeof err.detail === "string" ? err.detail : "Synthesis failed");
        return;
      }
      const data: SynthesisResult = await res.json();
      setResult(data);
    } catch {
      onError("Synthesis failed");
    } finally {
      setSynthesising(false);
    }
  };

  const runFinalise = async () => {
    if (!result?.synthesis_id) return;
    setFinalising(true);
    try {
      const ackList = Object.entries(acknowledged)
        .filter(([, v]) => v)
        .map(([k]) => k);
      const res = await apiFetch("/api/synthesise/finalise", {
        method: "POST",
        body: JSON.stringify({
          synthesis_id: result.synthesis_id,
          acknowledged_flags: ackList,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const msg =
          typeof err.detail === "object" && err.detail?.message
            ? err.detail.message
            : typeof err.detail === "string"
              ? err.detail
              : "Could not finalise";
        onError(msg);
        return;
      }
      setFinalised(true);
      onFinalised({ ...result, finalised_at: new Date().toISOString() });
    } catch {
      onError("Finalise failed");
    } finally {
      setFinalising(false);
    }
  };

  return (
    <div className="space-y-4 border-t border-gray-100 pt-4">
      <button
        type="button"
        onClick={runSynthesise}
        disabled={synthesising || !rawText.trim()}
        className="bg-brand-400 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-brand-600 disabled:opacity-50"
      >
        {synthesising ? "Synthesising…" : "Synthesise commentary"}
      </button>

      {result && (
        <div className="space-y-3">
          <div className="bg-gray-50 rounded-lg p-3 text-sm text-gray-700">
            <p className="text-xs text-gray-500 mb-1">Objectivity score: {result.score}/100</p>
            <p className="whitespace-pre-wrap">{result.commentary}</p>
          </div>

          {result.flags.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-medium text-gray-500">Bias flags</p>
              {result.flags.map((flag, i) => (
                <div
                  key={`${flag.passage}-${i}`}
                  className={`bg-white border border-gray-100 rounded-lg p-3 ${flagBorder(flag.severity)}`}
                >
                  <p className="text-xs font-medium text-gray-700">
                    {flag.type}{" "}
                    <span className="text-gray-400 font-normal">· {flag.severity}</span>
                  </p>
                  <p className="text-xs text-gray-600 mt-1 italic">&quot;{flag.passage}&quot;</p>
                  <p className="text-xs text-gray-500 mt-1">→ {flag.suggestion}</p>
                </div>
              ))}
            </div>
          )}

          {result.gate_blocked && !finalised && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-sm text-amber-900">
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                <div>
                  <p className="font-medium">Review required before finalising</p>
                  <p className="mt-1 text-amber-800">
                    {highFlags.length} high-severity bias flag(s) must be acknowledged.
                  </p>
                  {result.gate_reason && (
                    <p className="mt-1 text-xs text-amber-700">{result.gate_reason}</p>
                  )}
                </div>
              </div>
              <div className="mt-3 space-y-3">
                {highFlags.map((flag) => (
                  <label
                    key={flag.passage}
                    className="flex items-start gap-2 text-xs cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={!!acknowledged[flag.passage]}
                      onChange={(e) =>
                        setAcknowledged((prev) => ({
                          ...prev,
                          [flag.passage]: e.target.checked,
                        }))
                      }
                      className="mt-0.5"
                    />
                    <span>
                      <span className="font-medium">{flag.type}:</span> &quot;{flag.passage}&quot;
                      <span className="block text-gray-600 mt-0.5">
                        Suggested rewrite: {flag.suggestion}
                      </span>
                      {onApplyRewrite && (
                        <button
                          type="button"
                          onClick={() => onApplyRewrite(flag.suggestion)}
                          className="text-brand-600 hover:underline mt-1"
                        >
                          Use suggested rewrite
                        </button>
                      )}
                    </span>
                  </label>
                ))}
              </div>
            </div>
          )}

          {finalised && (
            <div className="flex items-center gap-2 text-sm text-emerald-700 bg-emerald-50 border border-emerald-100 rounded-lg px-3 py-2">
              <CheckCircle2 className="w-4 h-4" />
              Commentary finalised — you can save feedback below.
            </div>
          )}

          {!finalised && (
            <button
              type="button"
              onClick={runFinalise}
              disabled={
                finalising ||
                !result.synthesis_id ||
                (result.gate_blocked && !allHighAcknowledged)
              }
              className="bg-brand-500 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-brand-600 disabled:opacity-50"
            >
              {finalising ? "Finalising…" : "Finalise commentary"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
