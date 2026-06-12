const STORAGE_KEY = "pm_coach_workflow_id";

function newWorkflowId(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return `wf_${crypto.randomUUID()}`;
  }
  return `wf_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

export function getWorkflowId(): string {
  let id = sessionStorage.getItem(STORAGE_KEY);
  if (!id) {
    id = newWorkflowId();
    sessionStorage.setItem(STORAGE_KEY, id);
  }
  return id;
}

export function resetWorkflowId(): string {
  const id = newWorkflowId();
  sessionStorage.setItem(STORAGE_KEY, id);
  return id;
}
