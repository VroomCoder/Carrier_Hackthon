/** Managers may log feedback for direct reports only; HR for any employee. */
export function canLogFeedbackForEmployee(
  user:
    | { role?: string; is_manager?: boolean; employee_id?: string | null }
    | undefined,
  activeEmployee: { employee_id: string } | null,
  directReports: Array<{ employee_id: string }> = []
): boolean {
  if (!user || !activeEmployee) return false;
  if (user.role === "admin") return true;
  if (!user.is_manager || !user.employee_id) return false;
  if (activeEmployee.employee_id === user.employee_id) return false;
  return directReports.some((r) => r.employee_id === activeEmployee.employee_id);
}
