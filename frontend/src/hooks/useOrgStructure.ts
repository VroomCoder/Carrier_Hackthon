import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "./api";
import type { RoleContext } from "../types";

export function useOrgStructure() {
  const [departments, setDepartments] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const cache = useRef(new Map<string, string[]>());

  useEffect(() => {
    apiFetch("/api/org/departments")
      .then((r) => r.json())
      .then((data: string[]) => {
        setDepartments(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const getBusinessUnits = useCallback(async (department: string): Promise<string[]> => {
    const key = `bu:${department}`;
    if (cache.current.has(key)) return cache.current.get(key)!;
    const res = await apiFetch(`/api/org/business-units?department=${encodeURIComponent(department)}`);
    const data: string[] = await res.json();
    cache.current.set(key, data);
    return data;
  }, []);

  const getDesignations = useCallback(
    async (department: string, businessUnit: string): Promise<string[]> => {
      const key = `des:${department}:${businessUnit}`;
      if (cache.current.has(key)) return cache.current.get(key)!;
      const res = await apiFetch(
        `/api/org/designations?department=${encodeURIComponent(department)}&business_unit=${encodeURIComponent(businessUnit)}`
      );
      const data: string[] = await res.json();
      cache.current.set(key, data);
      return data;
    },
    []
  );

  const validateRole = useCallback(
    async (department: string, businessUnit: string, designation: string): Promise<boolean> => {
      const res = await apiFetch(
        `/api/org/validate?department=${encodeURIComponent(department)}&business_unit=${encodeURIComponent(businessUnit)}&designation=${encodeURIComponent(designation)}`
      );
      const data: { valid: boolean } = await res.json();
      return data.valid;
    },
    []
  );

  const getRoleContext = useCallback(
    async (department: string, businessUnit: string, designation: string): Promise<RoleContext> => {
      const res = await apiFetch(
        `/api/org/role-context?department=${encodeURIComponent(department)}&business_unit=${encodeURIComponent(businessUnit)}&designation=${encodeURIComponent(designation)}`
      );
      return res.json();
    },
    []
  );

  return { departments, getBusinessUnits, getDesignations, validateRole, getRoleContext, loading };
}
