import type { HealthData } from "../types";

export function aiUnavailableMessage(health: HealthData | null): string {
  if (!health) return "AI service is unavailable.";
  const provider = health.llm_provider ?? "ollama";
  if (health.llm_detail) {
    if (
      health.llm_detail.includes("quota") ||
      health.llm_detail.includes("credit") ||
      health.llm_detail.includes("depleted")
    ) {
      return health.llm_detail;
    }
  }
  if (provider === "gemini") {
    if (health.llm_detail?.includes("GEMINI_API_KEY") || health.llm_detail?.includes("API key")) {
      return health.llm_detail;
    }
    return (
      health.llm_detail ??
      "Gemini API is unavailable. Check GOOGLE_API_KEY or GEMINI_API_KEY in backend/.env."
    );
  }
  return "Ollama is not running. Install from ollama.com/download, then run: ollama serve";
}

export function aiNotReady(health: HealthData | null): boolean {
  if (!health) return true;
  const ready = health.llm_model_ready ?? health.ollama_model_ready;
  if (!(health.llm_ok ?? health.ollama_ok)) return true;
  return !ready;
}
