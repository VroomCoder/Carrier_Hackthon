import { useCallback, useEffect, useState } from "react";
import type { AuthUser, Employee } from "../types";
import { apiFetch, clearAuthToken, getAuthToken, setAuthToken } from "./api";

export interface AuthState {
  user: AuthUser | null;
  employee: Employee | null;
  directReports: Employee[];
  accessibleEmployeeIds: string[] | null;
  loading: boolean;
}

export function useAuth() {
  const [state, setState] = useState<AuthState>({
    user: null,
    employee: null,
    directReports: [],
    accessibleEmployeeIds: null,
    loading: true,
  });

  const applySession = useCallback((data: {
    user: AuthUser;
    employee?: Employee | null;
    direct_reports?: Employee[];
    accessible_employee_ids?: string[] | null;
  }) => {
    const user: AuthUser = {
      ...data.user,
      is_manager: data.user.is_manager ?? false,
    };
    setState({
      user,
      employee: data.employee ?? null,
      directReports: data.direct_reports ?? [],
      accessibleEmployeeIds: data.accessible_employee_ids ?? null,
      loading: false,
    });
  }, []);

  const loadSession = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setState({
        user: null,
        employee: null,
        directReports: [],
        accessibleEmployeeIds: null,
        loading: false,
      });
      return;
    }
    try {
      const res = await apiFetch("/api/auth/me");
      if (!res.ok) {
        clearAuthToken();
        setState({
          user: null,
          employee: null,
          directReports: [],
          accessibleEmployeeIds: null,
          loading: false,
        });
        return;
      }
      applySession(await res.json());
    } catch {
      clearAuthToken();
      setState({
        user: null,
        employee: null,
        directReports: [],
        accessibleEmployeeIds: null,
        loading: false,
      });
    }
  }, [applySession]);

  useEffect(() => {
    loadSession();
  }, [loadSession]);

  const login = useCallback(
    async (loginType: "admin" | "employee", pin: string, employeeId?: string) => {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          login_type: loginType,
          pin,
          employee_id: employeeId ?? null,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Login failed");
      }
      const data = await res.json();
      setAuthToken(data.token);
      applySession(data);
      return data;
    },
    [applySession]
  );

  const logout = useCallback(async () => {
    try {
      await apiFetch("/api/auth/logout", { method: "POST" });
    } catch {
      /* ignore */
    }
    clearAuthToken();
    setState({
      user: null,
      employee: null,
      directReports: [],
      accessibleEmployeeIds: null,
      loading: false,
    });
  }, []);

  return { ...state, login, logout, reload: loadSession };
}
