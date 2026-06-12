import {
  LayoutGrid,
  Target,
  MessageSquare,
  MessageSquarePlus,
  HeartHandshake,
  HeartPulse,
  Users,
  GitBranch,
  TrendingUp,
  LogOut,
} from "lucide-react";
import AgentActivityPanel from "./AgentActivityPanel";
import type { AuthUser, Employee, ToastType } from "../types";

interface LayoutProps {
  activePanel: string;
  setActivePanel: (panel: string) => void;
  activeEmployee: Employee | null;
  selfEmployee: Employee | null;
  setActiveEmployee: (emp: Employee | null) => void;
  user: AuthUser;
  onLogout: () => void;
  addToast: (message: string, type?: ToastType) => void;
  children: React.ReactNode;
}

const ALL_NAV_ITEMS = [
  { id: "team_health", label: "Team health", icon: HeartPulse, employee: false, admin: true, manager: true },
  { id: "dashboard", label: "Dashboard", icon: LayoutGrid, employee: true, admin: false, manager: true },
  { id: "calibrator", label: "OKRs & Goals", icon: Target, employee: true, admin: false, manager: true },
  { id: "feedback", label: "Feedback & Reviews", icon: MessageSquare, employee: true, admin: false, manager: true },
  { id: "continuous_feedback", label: "Continuous Feedback", icon: MessageSquarePlus, employee: false, admin: false, manager: true },
  { id: "coach", label: "Growth Coach", icon: HeartHandshake, employee: true, admin: false, manager: true },
  { id: "employees", label: "Employee Lookup", icon: Users, manager: true, admin: true, employee: false },
  { id: "okrs", label: "Company OKRs", icon: TrendingUp, admin: true, manager: false, employee: false },
  { id: "org", label: "Org Structure", icon: GitBranch, admin: true, manager: false, employee: false },
];

function roleBadge(user: AuthUser): string {
  if (user.role === "admin") return "HR";
  if (user.is_manager ?? false) return "Manager";
  return "Employee";
}

export default function Layout({
  activePanel,
  setActivePanel,
  activeEmployee,
  selfEmployee,
  setActiveEmployee,
  user,
  onLogout,
  addToast,
  children,
}: LayoutProps) {
  const isManager = user.is_manager ?? false;
  const navItems = ALL_NAV_ITEMS.filter((item) => {
    if (user.role === "admin") return item.admin;
    if (isManager) return item.employee || item.manager;
    return item.employee;
  });
  const managingReport =
    isManager &&
    selfEmployee &&
    activeEmployee &&
    activeEmployee.employee_id !== selfEmployee.employee_id;

  return (
    <div className="min-h-screen flex flex-col bg-[#f8fafc]">
      <header className="bg-white border-b border-brand-100 px-6 py-3 flex items-center justify-between shadow-sm shadow-brand-900/5">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-brand-500 rounded-lg flex items-center justify-center shadow-md shadow-brand-900/20">
            <svg viewBox="0 0 24 24" className="w-5 h-5 text-white" fill="currentColor">
              <path d="M17 8C8 10 5.9 16.17 3.82 21.34L5.71 22l1-2.3c.48.17.98.3 1.5.3C19 20.3 20 16 20 12c0-1.09-.22-2.12-.6-3.06C19.5 8.5 18.3 8 17 8z" />
            </svg>
          </div>
          <div>
            <span className="font-bold text-brand-500 text-lg tracking-tight">NexaCore Growth Coach</span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {activeEmployee ? (
            <span className="bg-brand-50 text-brand-600 text-sm px-3 py-1 rounded-full border border-brand-100">
              {user.role === "admin"
                ? `Viewing: ${activeEmployee.name}`
                : managingReport
                  ? `Managing: ${activeEmployee.name}`
                  : `My goals: ${activeEmployee.name}`}
            </span>
          ) : user.role === "admin" ? (
            <span className="bg-amber-50 text-amber-700 text-sm px-3 py-1 rounded-full border border-amber-100">
              HR overview
            </span>
          ) : null}
          {managingReport && selfEmployee && (
            <button
              onClick={() => {
                setActiveEmployee(selfEmployee);
                addToast("Switched to your profile", "info");
              }}
              className="text-sm text-brand-600 hover:text-brand-700 px-3 py-1 rounded-lg border border-brand-200 hover:bg-brand-50"
            >
              Switch to my goals
            </button>
          )}
          <span className="text-sm text-gray-600">
            {user.display_name}
            <span className="ml-2 text-xs bg-brand-900 text-white px-2 py-0.5 rounded-full">
              {roleBadge(user)}
            </span>
          </span>
          <button
            onClick={onLogout}
            className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 px-2 py-1 rounded-lg hover:bg-gray-100"
            title="Sign out"
          >
            <LogOut className="w-4 h-4" />
            Sign out
          </button>
        </div>
      </header>

      <div className="flex flex-1 min-h-0">
        <aside className="w-56 bg-brand-900 py-5 flex-shrink-0">
          <nav className="flex flex-col gap-1 px-3">
            {navItems.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setActivePanel(id)}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                  activePanel === id
                    ? "bg-brand-400 text-white shadow-lg shadow-accent-400/20"
                    : "text-brand-100/80 hover:bg-white/10 hover:text-white"
                }`}
              >
                <span
                  className={`flex h-7 w-7 items-center justify-center rounded-full ${
                    activePanel === id ? "bg-white/20" : "bg-brand-500/40"
                  }`}
                >
                  <Icon className="w-4 h-4" />
                </span>
                {label}
              </button>
            ))}
          </nav>
        </aside>

        <main className="flex-1 flex min-h-0 overflow-hidden">
          <div className="flex-1 p-6 overflow-auto min-w-0">{children}</div>
          <div className="hidden xl:flex w-80 shrink-0 border-l border-brand-100 bg-white/60 p-4 overflow-y-auto">
            <AgentActivityPanel
              employeeId={
                activeEmployee?.employee_id ?? selfEmployee?.employee_id ?? null
              }
              className="w-full border-0 shadow-none bg-transparent p-0 rounded-none"
            />
          </div>
        </main>
      </div>
    </div>
  );
}
