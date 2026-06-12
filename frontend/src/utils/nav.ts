/** Employee/manager workflow panels hidden from HR in the main nav. */
export const HR_RESTRICTED_PANELS = new Set([
  "dashboard",
  "calibrator",
  "feedback",
  "continuous_feedback",
  "coach",
]);

export function defaultPanelForUser(user: {
  role?: string;
  is_manager?: boolean;
}): string {
  if (user.role === "admin" || user.is_manager) return "team_health";
  return "dashboard";
}

export function isPanelAllowedForUser(
  user: { role?: string; is_manager?: boolean },
  panel: string
): boolean {
  if (user.role === "admin" && HR_RESTRICTED_PANELS.has(panel)) return false;
  return true;
}
