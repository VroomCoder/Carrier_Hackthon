import { useEffect, useState } from "react";
import { apiFetch } from "../hooks/api";
import type { AuthUser, Employee, ToastType } from "../types";
import { useOrgStructure } from "../hooks/useOrgStructure";

interface Props {
  activeEmployee: Employee | null;
  setActiveEmployee: (emp: Employee | null) => void;
  addToast: (message: string, type?: ToastType) => void;
  user: AuthUser;
  selfEmployee: Employee | null;
  directReports: Employee[];
}

export default function EmployeeSearch({
  activeEmployee,
  setActiveEmployee,
  addToast,
  user,
  selfEmployee,
  directReports: _directReports,
}: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Employee[]>([]);
  const { departments, getBusinessUnits, getDesignations, validateRole } = useOrgStructure();

  const [department, setDepartment] = useState("");
  const [businessUnit, setBusinessUnit] = useState("");
  const [designation, setDesignation] = useState("");
  const [businessUnits, setBusinessUnits] = useState<string[]>([]);
  const [designations, setDesignations] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [location, setLocation] = useState("");
  const [workMode, setWorkMode] = useState("Office");

  useEffect(() => {
    const timer = setTimeout(() => {
      const url = query.trim()
        ? `/api/employees?q=${encodeURIComponent(query)}`
        : "/api/employees";
      apiFetch(url)
        .then((r) => r.json())
        .then(setResults)
        .catch(() => setResults([]));
    }, query.trim() ? 400 : 0);
    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    if (department) {
      getBusinessUnits(department).then(setBusinessUnits);
    } else {
      setBusinessUnits([]);
    }
    setBusinessUnit("");
    setDesignation("");
    setDesignations([]);
  }, [department, getBusinessUnits]);

  useEffect(() => {
    if (department && businessUnit) {
      getDesignations(department, businessUnit).then(setDesignations);
    } else {
      setDesignations([]);
    }
    setDesignation("");
  }, [department, businessUnit, getDesignations]);

  const handleManualSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !department || !businessUnit || !designation) {
      addToast("Please fill all required fields", "warning");
      return;
    }
    const valid = await validateRole(department, businessUnit, designation);
    if (!valid) {
      addToast("Role combination not found in org structure", "warning");
    }
    const emp: Employee = {
      employee_id: `MANUAL-${Date.now()}`,
      name: name.trim(),
      email: email || undefined,
      department,
      sub_department: businessUnit,
      job_title: designation,
      location: location || undefined,
      work_mode: workMode,
    };
    setActiveEmployee(emp);
    addToast(`${emp.name} set as active employee`, "success");
  };

  const displayList = query.trim() ? results : results;
  const showTeamHint = user.is_manager && !query.trim();

  return (
    <div className="space-y-8">
      <h1 className="page-title">
        {user.is_manager ? "My Team" : "Employee Lookup"}
      </h1>

      <section className="bg-white border border-gray-200 rounded-xl p-5">
        <h2 className="text-sm font-medium text-gray-500 mb-4">
          {user.is_manager ? "Search your team" : "Search all employees"}
        </h2>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={
            user.is_manager
              ? "Search by name, department, or role within your team..."
              : "Search by name, department, role, or employee ID..."
          }
          className="w-full border border-gray-200 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-brand-400 focus:outline-none mb-4"
        />

        {showTeamHint && displayList.length > 0 && (
          <p className="text-xs text-gray-400 mb-3">
            You and your direct reports ({displayList.length})
          </p>
        )}
        {user.role === "admin" && !query.trim() && displayList.length > 0 && (
          <p className="text-xs text-gray-400 mb-3">All employees ({displayList.length})</p>
        )}

        {displayList.length > 0 && (
          <div className="space-y-2">
            {displayList.map((emp) => {
              const isSelf =
                user.is_manager && emp.employee_id === selfEmployee?.employee_id;
              return (
              <div
                key={emp.employee_id}
                className="flex items-center justify-between p-3 border border-gray-100 rounded-lg hover:bg-gray-50"
              >
                <div>
                  <p className="font-medium text-sm">
                    {emp.name}
                    {isSelf && (
                      <span className="ml-2 text-xs bg-brand-100 text-brand-700 px-2 py-0.5 rounded-full">
                        Me
                      </span>
                    )}
                  </p>
                  <p className="text-xs text-gray-500">
                    {emp.job_title} · {emp.department} / {emp.sub_department}
                  </p>
                  <p className="text-xs text-gray-400">
                    {emp.location} · {emp.work_mode}
                  </p>
                </div>
                <button
                  onClick={() => {
                    setActiveEmployee(emp);
                    addToast(`${emp.name} set as active employee`, "success");
                  }}
                  className={`text-xs px-3 py-1 rounded-lg ${
                    activeEmployee?.employee_id === emp.employee_id
                      ? "bg-brand-400 text-white"
                      : "border border-brand-400 text-brand-600"
                  }`}
                >
                  {activeEmployee?.employee_id === emp.employee_id
                    ? isSelf
                      ? "My goals"
                      : "Active"
                    : isSelf
                      ? "Set my goals"
                      : "Set as active"}
                </button>
              </div>
            );
            })}
          </div>
        )}

        {!query.trim() && displayList.length === 0 && user.role === "admin" && (
          <p className="text-sm text-gray-400">Search to find any employee in the organisation.</p>
        )}
      </section>

      {user.role === "admin" && (
        <section className="bg-white border border-gray-200 rounded-xl p-5">
          <h2 className="text-sm font-medium text-gray-500 mb-4">Create Manual Profile</h2>
          <form onSubmit={handleManualSubmit} className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Department *</label>
              <select
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-brand-400 focus:outline-none"
              >
                <option value="">Select department</option>
                {departments.map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Business Unit *</label>
              <select
                value={businessUnit}
                onChange={(e) => setBusinessUnit(e.target.value)}
                disabled={!department}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-brand-400 focus:outline-none disabled:opacity-50"
              >
                <option value="">Select business unit</option>
                {businessUnits.map((bu) => (
                  <option key={bu} value={bu}>{bu}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Designation *</label>
              <select
                value={designation}
                onChange={(e) => setDesignation(e.target.value)}
                disabled={!businessUnit}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-brand-400 focus:outline-none disabled:opacity-50"
              >
                <option value="">Select designation</option>
                {designations.map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Name *</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-brand-400 focus:outline-none"
              />
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Email</label>
              <input
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                type="email"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-brand-400 focus:outline-none"
              />
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Location</label>
              <input
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-brand-400 focus:outline-none"
              />
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Work Mode</label>
              <select
                value={workMode}
                onChange={(e) => setWorkMode(e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-brand-400 focus:outline-none"
              >
                <option>Office</option>
                <option>Hybrid</option>
                <option>Remote</option>
              </select>
            </div>
            <div className="col-span-2">
              <button
                type="submit"
                className="bg-brand-400 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-brand-600"
              >
                Set as active employee
              </button>
            </div>
          </form>
        </section>
      )}
    </div>
  );
}
