import { useCallback, useEffect, useState } from "react";
import Layout from "./components/Layout";
import Login from "./components/Login";
import ToastContainer from "./components/Toast";
import ManagerHealthDashboard from "./components/ManagerHealthDashboard";
import ContinuousFeedback from "./components/ContinuousFeedback";
import Dashboard from "./components/Dashboard";
import SmartCalibrator from "./components/SmartCalibrator";
import FeedbackReviews from "./components/FeedbackReviews";
import CoachChat from "./components/CoachChat";
import EmployeeSearch from "./components/EmployeeSearch";
import OKRManager from "./components/OKRManager";
import OrgManager from "./components/OrgManager";
import { useAuth } from "./hooks/useAuth";
import { useToast } from "./hooks/useToast";
import type { Employee, Milestone } from "./types";
import {
  defaultPanelForUser,
  isPanelAllowedForUser,
} from "./utils/nav";

export default function App() {
  const { user, employee, directReports, loading, login, logout } = useAuth();
  const [activePanel, setActivePanel] = useState("team_health");
  const [activeEmployee, setActiveEmployee] = useState<Employee | null>(null);
  const [editMilestone, setEditMilestone] = useState<Milestone | null>(null);
  const [selectedManagerId, setSelectedManagerId] = useState<string | null>(null);
  const { toasts, addToast, removeToast } = useToast();

  useEffect(() => {
    if (!user) {
      setActiveEmployee(null);
      setEditMilestone(null);
      setActivePanel("dashboard");
      return;
    }
    if (!isPanelAllowedForUser(user, activePanel)) {
      setActivePanel(defaultPanelForUser(user));
    }
  }, [user, activePanel]);

  const handleLogin = async (
    loginType: "admin" | "employee",
    pin: string,
    employeeId?: string
  ) => {
    const data = await login(loginType, pin, employeeId);
    setActivePanel(defaultPanelForUser(data.user ?? {}));
    if (data.employee) {
      setActiveEmployee(data.employee);
    } else {
      setActiveEmployee(null);
    }
  };

  const handleLogout = async () => {
    await logout();
    setActiveEmployee(null);
    setEditMilestone(null);
    setActivePanel("dashboard");
  };

  const clearEditMilestone = useCallback(() => setEditMilestone(null), []);

  const reviseMilestone = (milestone: Milestone) => {
    setEditMilestone(milestone);
    setActivePanel("calibrator");
  };

  useEffect(() => {
    if (activePanel !== "calibrator") {
      setEditMilestone(null);
    }
  }, [activePanel]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-gray-500">
        Loading…
      </div>
    );
  }

  if (!user) {
    return <Login onLogin={handleLogin} />;
  }

  const coachingEmployee = activeEmployee ?? employee ?? null;

  const renderPanel = () => {
    const props = {
      activeEmployee: coachingEmployee,
      setActiveEmployee,
      addToast,
      setActivePanel,
      user,
      selfEmployee: employee,
      directReports,
      reviseMilestone,
      editMilestone,
      clearEditMilestone,
      selectedManagerId,
      setSelectedManagerId,
    };
    switch (activePanel) {
      case "team_health":
        return <ManagerHealthDashboard {...props} />;
      case "dashboard":
        return <Dashboard {...props} />;
      case "continuous_feedback":
        return <ContinuousFeedback {...props} />;
      case "calibrator":
        return <SmartCalibrator {...props} />;
      case "feedback":
        return <FeedbackReviews {...props} />;
      case "coach":
        return (
          <CoachChat
            selfEmployee={employee}
            user={user}
            addToast={addToast}
          />
        );
      case "employees":
        return <EmployeeSearch {...props} />;
      case "okrs":
        return <OKRManager {...props} />;
      case "org":
        return <OrgManager {...props} />;
      default:
        return user.role === "admin" ? (
          <ManagerHealthDashboard {...props} />
        ) : (
          <Dashboard {...props} />
        );
    }
  };

  return (
    <>
      <Layout
        activePanel={activePanel}
        setActivePanel={setActivePanel}
        activeEmployee={coachingEmployee}
        selfEmployee={employee}
        setActiveEmployee={setActiveEmployee}
        user={user}
        onLogout={handleLogout}
        addToast={addToast}
      >
        {renderPanel()}
      </Layout>
      <ToastContainer toasts={toasts} onRemove={removeToast} />
    </>
  );
}
