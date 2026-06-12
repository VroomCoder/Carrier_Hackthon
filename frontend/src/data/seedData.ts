import type { Employee } from "../types";

export const SEED_EMPLOYEE: Employee = {
  employee_id: "NX01007",
  name: "Siddhant Muller",
  job_title: "Senior Product Manager",
  department: "Product",
  sub_department: "Core Product",
  grade: "P3",
  manager_name: "Shreya Patel",
  location: "Singapore, Singapore",
  work_mode: "Office",
  employment_type: "Full-Time",
};

export const SEED_MILESTONES = [
  {
    id: "m1",
    raw: "Launch the redesigned onboarding flow",
    smart:
      "Launch redesigned onboarding flow achieving ≥78% step-completion rate measured via Mixpanel by 30 September 2025, reducing support tickets by 20%.",
    scores: { S: 92, M: 88, A: 85, R: 95, T: 90 },
    status: "calibrated",
  },
  {
    id: "m2",
    raw: "Run quarterly business reviews better",
    smart:
      "Deliver 4 structured QBRs with executive stakeholders by 31 December 2025, each with a pre-distributed agenda and post-meeting action log published within 48 hours.",
    scores: { S: 88, M: 82, A: 90, R: 87, T: 91 },
    status: "calibrated",
  },
  {
    id: "m3",
    raw: "Get better at stakeholder management",
    smart: null,
    scores: { S: 28, M: 10, A: 60, R: 72, T: 15 },
    status: "needs_work",
  },
  {
    id: "m4",
    raw: "Improve the team's delivery velocity",
    smart: null,
    scores: { S: 45, M: 30, A: 70, R: 80, T: 35 },
    status: "needs_work",
  },
];

export const SEED_FEEDBACK_SAMPLES = [
  {
    label: "Peer — Engineering lead",
    raw: `Siddhant is great to work with. Always comes prepared. He really stepped up during the platform migration in Q1. Not sure he always pushes back on scope creep from senior stakeholders but he's getting better. Would love to see him take on more cross-functional initiatives.`,
  },
  {
    label: "Stakeholder — Head of Marketing",
    raw: `Very responsive and collaborative. Siddhant made the onboarding project much smoother. He listens well and incorporates feedback quickly. He handled the last-minute scope change in March really professionally.`,
  },
  {
    label: "Direct report",
    raw: `Siddhant gives good feedback and is always available when I'm stuck. He advocates well for the team in leadership meetings. Could delegate a bit more. The way he ran the sprint retrospectives this quarter was really effective.`,
  },
];

export const SEED_MANAGER_NOTES = `Siddhant delivered the onboarding redesign on time and above target. Good quarter overall. Handled the platform migration well despite the chaos. Needs to work on executive presence — sometimes loses the room in senior stakeholder meetings. Great with the team, maybe delegates too little. Solid performer, on track for Exceeds in most areas.`;

export const COACH_QUICK_PROMPTS = [
  "Help me prepare for my mid-year review conversation",
  "My milestone scores are low — how do I make them more SMART?",
  "What does the company policy say about the review process?",
  "What should I focus on for the second half of the year?",
];

export const FEEDBACK_TYPE_CONFIG: Record<
  string,
  { label: string; color: string }
> = {
  strength: { label: "Strength", color: "teal" },
  development: { label: "Development", color: "amber" },
  project: { label: "Project", color: "blue" },
  behaviour: { label: "Behaviour", color: "purple" },
  general: { label: "General", color: "gray" },
};

export const FEEDBACK_TAGS_SUGGESTED = [
  "delivery",
  "leadership",
  "communication",
  "technical depth",
  "stakeholder management",
  "collaboration",
  "initiative",
  "executive presence",
  "delegation",
  "ownership",
  "cross-functional",
  "risk management",
  "preparation",
  "empowerment",
];

export const TYPE_BADGE_CLASS: Record<string, string> = {
  strength: "bg-brand-100 text-brand-700",
  development: "bg-amber-100 text-amber-700",
  project: "bg-blue-100 text-blue-700",
  behaviour: "bg-purple-100 text-purple-700",
  general: "bg-gray-100 text-gray-700",
};

export const OKR_CATEGORIES = [
  "Engineering",
  "Sales",
  "People",
  "Product",
  "Security",
  "Customer Success",
  "Finance",
  "Other",
];
