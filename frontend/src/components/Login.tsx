import { useEffect, useMemo, useRef, useState } from "react";
import { User, Shield, ChevronLeft, ChevronDown, Search } from "lucide-react";

interface EmployeeLoginOption {
  employee_id: string;
  name: string;
  job_title: string;
  department: string;
  sub_department: string;
  is_manager: boolean;
}

interface Props {
  onLogin: (loginType: "admin" | "employee", pin: string, employeeId?: string) => Promise<void>;
}

type Step = "type" | "employee";

export default function Login({ onLogin }: Props) {
  const [step, setStep] = useState<Step>("type");
  const [employees, setEmployees] = useState<EmployeeLoginOption[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [search, setSearch] = useState("");
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch("/api/auth/employees-for-login")
      .then((r) => r.json())
      .then(setEmployees)
      .catch(() => setEmployees([]));
  }, []);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return employees;
    return employees.filter(
      (e) =>
        e.name.toLowerCase().includes(q) ||
        e.employee_id.toLowerCase().includes(q) ||
        e.department.toLowerCase().includes(q) ||
        e.job_title.toLowerCase().includes(q) ||
        e.sub_department.toLowerCase().includes(q)
    );
  }, [employees, search]);

  const selected = employees.find((e) => e.employee_id === selectedId) ?? null;

  const handleAdmin = async () => {
    setError("");
    setLoading("admin");
    try {
      await onLogin("admin", "admin");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Login failed");
    } finally {
      setLoading(null);
    }
  };

  const handleEmployeeSignIn = async () => {
    if (!selected) {
      setError("Please select an employee from the list");
      return;
    }
    setError("");
    setLoading(selected.employee_id);
    try {
      await onLogin("employee", "employee", selected.employee_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Login failed");
    } finally {
      setLoading(null);
    }
  };

  const selectEmployee = (emp: EmployeeLoginOption) => {
    setSelectedId(emp.employee_id);
    setDropdownOpen(false);
    setSearch("");
    setError("");
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-brand-50 via-white to-[#f8fafc] flex items-center justify-center p-6">
      <div className="w-full max-w-lg">
        <div className="text-center mb-8">
          <div className="w-14 h-14 bg-brand-500 rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-lg shadow-brand-900/20">
            <svg viewBox="0 0 24 24" className="w-8 h-8 text-white" fill="currentColor">
              <path d="M17 8C8 10 5.9 16.17 3.82 21.34L5.71 22l1-2.3c.48.17.98.3 1.5.3C19 20.3 20 16 20 12c0-1.09-.22-2.12-.6-3.06C19.5 8.5 18.3 8 17 8z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-brand-500 tracking-tight">NexaCore Growth Coach</h1>
          <p className="text-gray-500 mt-2">
            {step === "type" ? "Sign in as HR or Employee" : "Choose your employee profile"}
          </p>
          {step === "type" && (
            <p className="mt-4">
              <span className="tagline-pill">Innovate. Automate. Elevate performance.</span>
            </p>
          )}
        </div>

        {step === "type" && (
          <div className="space-y-3">
            <button
              onClick={() => setStep("employee")}
              disabled={!!loading}
              className="w-full bg-white border border-gray-200 rounded-xl p-4 flex items-center gap-4 hover:border-brand-300 hover:shadow-card transition-all text-left disabled:opacity-60"
            >
              <div className="w-10 h-10 bg-brand-50 rounded-lg flex items-center justify-center">
                <User className="w-5 h-5 text-brand-600" />
              </div>
              <div className="flex-1">
                <p className="font-medium text-slate-900">Employee</p>
                <p className="text-sm text-gray-500">
                  {employees.length > 0
                    ? `Choose from ${employees.length} employees. Managers are employees with a team.`
                    : "Sign in with your employee profile."}
                </p>
              </div>
              <span className="text-xs text-brand-600 font-medium">Continue</span>
            </button>

            <button
              onClick={handleAdmin}
              disabled={!!loading}
              className="w-full bg-white border border-gray-200 rounded-xl p-4 flex items-center gap-4 hover:border-brand-300 hover:shadow-card transition-all text-left disabled:opacity-60"
            >
              <div className="w-10 h-10 bg-brand-500 rounded-full flex items-center justify-center">
                <Shield className="w-5 h-5 text-white" />
              </div>
              <div className="flex-1">
                <p className="font-medium text-slate-900">HR</p>
                <p className="text-sm text-gray-500">Full access to OKRs, org structure, and all employees</p>
              </div>
              <span className="text-xs text-brand-600 font-medium">
                {loading === "admin" ? "Signing in…" : "Sign in"}
              </span>
            </button>
          </div>
        )}

        {step === "employee" && (
          <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-card">
            <button
              onClick={() => {
                setStep("type");
                setSearch("");
                setSelectedId("");
                setDropdownOpen(false);
              }}
              className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 mb-4"
            >
              <ChevronLeft className="w-4 h-4" />
              Back
            </button>

            <label className="text-sm font-medium text-gray-700 mb-2 block">Employee</label>

            <div className="relative" ref={dropdownRef}>
              <button
                type="button"
                onClick={() => setDropdownOpen((open) => !open)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm text-left flex items-center justify-between bg-white hover:border-brand-300 focus:ring-2 focus:ring-brand-400 focus:outline-none"
              >
                <span className={selected ? "text-slate-900" : "text-gray-400"}>
                  {selected
                    ? `${selected.name} (${selected.employee_id})`
                    : "Select an employee…"}
                </span>
                <ChevronDown
                  className={`w-4 h-4 text-gray-400 transition-transform ${dropdownOpen ? "rotate-180" : ""}`}
                />
              </button>

              {dropdownOpen && (
                <div className="absolute z-10 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg">
                  <div className="p-2 border-b border-gray-100">
                    <div className="relative">
                      <Search className="w-4 h-4 text-gray-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
                      <input
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search employees…"
                        className="w-full border border-gray-200 rounded-md pl-8 pr-3 py-1.5 text-sm focus:ring-2 focus:ring-brand-400 focus:outline-none"
                        autoFocus
                      />
                    </div>
                    <p className="text-xs text-gray-400 mt-1.5 px-1">
                      {filtered.length} of {employees.length} employees
                    </p>
                  </div>

                  <ul className="max-h-60 overflow-y-auto py-1">
                    {filtered.map((emp) => (
                      <li key={emp.employee_id}>
                        <button
                          type="button"
                          onClick={() => selectEmployee(emp)}
                          className={`w-full text-left px-3 py-2 text-sm hover:bg-brand-50 ${
                            selectedId === emp.employee_id ? "bg-brand-50 text-brand-700" : "text-gray-700"
                          }`}
                        >
                          <span className="font-medium">{emp.name}</span>
                          {emp.is_manager && (
                            <span className="ml-2 text-xs bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded">
                              Manager
                            </span>
                          )}
                          <span className="block text-xs text-gray-500 truncate">
                            {emp.job_title} · {emp.department} · {emp.employee_id}
                          </span>
                        </button>
                      </li>
                    ))}
                    {filtered.length === 0 && (
                      <li className="px-3 py-4 text-sm text-gray-400 text-center">No matches</li>
                    )}
                  </ul>
                </div>
              )}
            </div>

            {selected && (
              <div className="mt-3 p-3 bg-gray-50 rounded-lg text-sm text-gray-600">
                <p className="font-medium text-slate-900">{selected.name}</p>
                <p>{selected.job_title}</p>
                <p>{selected.department} / {selected.sub_department}</p>
                <p className="text-xs text-gray-400 mt-1">{selected.employee_id}</p>
              </div>
            )}

            <button
              onClick={handleEmployeeSignIn}
              disabled={!!loading || !selected}
              className="w-full mt-4 btn-primary py-2.5 text-sm disabled:opacity-50"
            >
              {loading && selected ? "Signing in…" : "Sign in as employee"}
            </button>
          </div>
        )}

        {error && <p className="mt-4 text-sm text-red-600 text-center">{error}</p>}

        <p className="mt-6 text-xs text-gray-400 text-center">
          Demo PINs: employee (employees) · admin (HR)
        </p>
      </div>
    </div>
  );
}
