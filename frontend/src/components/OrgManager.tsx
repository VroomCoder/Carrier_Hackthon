import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../hooks/api";
import type { OrgNode, RoleContext, ToastType } from "../types";

interface Props {
  addToast: (message: string, type?: ToastType) => void;
}

type Tab = "browse" | "add" | "bulk" | "archived";

const tierColors: Record<string, string> = {
  junior: "bg-gray-100 text-gray-700 border-gray-200",
  mid: "bg-blue-50 text-blue-700 border-blue-200",
  senior: "bg-brand-50 text-brand-700 border-brand-200",
  lead: "bg-purple-50 text-purple-700 border-purple-200",
  director: "bg-amber-50 text-amber-700 border-amber-200",
};

export default function OrgManager({ addToast }: Props) {
  const [tab, setTab] = useState<Tab>("browse");
  const [nodes, setNodes] = useState<OrgNode[]>([]);
  const [departments, setDepartments] = useState<string[]>([]);

  const [department, setDepartment] = useState("");
  const [businessUnit, setBusinessUnit] = useState("");
  const [designation, setDesignation] = useState("");
  const [preview, setPreview] = useState<RoleContext | null>(null);
  const [bulkText, setBulkText] = useState("");
  const [replaceExisting, setReplaceExisting] = useState(false);

  const fetchNodes = useCallback(async () => {
    const status = tab === "archived" ? "archived" : "active";
    const res = await apiFetch(`/api/org/nodes?status=${status}`);
    setNodes(await res.json());
  }, [tab]);

  useEffect(() => {
    apiFetch("/api/org/departments")
      .then((r) => r.json())
      .then(setDepartments)
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (tab !== "add") fetchNodes();
  }, [tab, fetchNodes]);

  useEffect(() => {
    if (!department || !businessUnit || !designation) {
      setPreview(null);
      return;
    }
    const timer = setTimeout(() => {
      apiFetch(
        `/api/org/role-context?department=${encodeURIComponent(department)}&business_unit=${encodeURIComponent(businessUnit)}&designation=${encodeURIComponent(designation)}`
      )
        .then((r) => r.json())
        .then(setPreview)
        .catch(() => {});
    }, 800);
    return () => clearTimeout(timer);
  }, [department, businessUnit, designation]);

  const grouped = nodes.reduce<Record<string, Record<string, OrgNode[]>>>((acc, node) => {
    if (!acc[node.department]) acc[node.department] = {};
    if (!acc[node.department][node.business_unit]) acc[node.department][node.business_unit] = [];
    acc[node.department][node.business_unit].push(node);
    return acc;
  }, {});

  const addNode = async () => {
    const res = await apiFetch("/api/org/nodes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ department, business_unit: businessUnit, designation }),
    });
    if (res.ok) {
      addToast("Org node added", "success");
      setDepartment("");
      setBusinessUnit("");
      setDesignation("");
      setTab("browse");
      fetchNodes();
    } else {
      addToast("Failed to add node", "error");
    }
  };

  const bulkImport = async () => {
    const lines = bulkText.trim().split("\n").filter(Boolean);
    const nodeData = lines.map((line) => {
      const [dept, bu, des] = line.split("|").map((s) => s.trim());
      return { department: dept, business_unit: bu, designation: des };
    });
    const res = await apiFetch("/api/org/nodes/bulk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nodes: nodeData, replace_existing: replaceExisting }),
    });
    const data = await res.json();
    addToast(`Imported ${data.imported} nodes`, "success");
    setBulkText("");
    setTab("browse");
  };

  const archiveNode = async (nodeId: string) => {
    if (!confirm("Archive this org node?")) return;
    await apiFetch(`/api/org/nodes/${nodeId}/archive`, { method: "POST" });
    fetchNodes();
    addToast("Node archived", "info");
  };

  const activateNode = async (nodeId: string) => {
    await apiFetch(`/api/org/nodes/${nodeId}/activate`, { method: "POST" });
    fetchNodes();
    addToast("Node reactivated", "success");
  };

  const deleteNode = async (nodeId: string) => {
    if (!confirm("Delete this node permanently?")) return;
    await apiFetch(`/api/org/nodes/${nodeId}`, { method: "DELETE" });
    fetchNodes();
    addToast("Node deleted", "info");
  };

  const renderTree = (archived = false) => (
    <div className="space-y-6">
      {Object.entries(grouped).map(([dept, bus]) => (
        <div key={dept}>
          <h3 className="font-semibold text-slate-900 mb-2">{dept}</h3>
          {Object.entries(bus).map(([bu, desNodes]) => (
            <div key={bu} className="ml-4 mb-3">
              <p className="text-sm text-gray-500 mb-2">{bu}</p>
              <div className="flex flex-wrap gap-2 ml-4">
                {desNodes.map((node) => (
                  <div key={node.node_id} className="group relative">
                    <span
                      title={`${node.seniority_tier}: ${node.focus_description}`}
                      className={`text-xs px-3 py-1 rounded-full border cursor-default ${tierColors[node.seniority_tier] ?? tierColors.mid}`}
                    >
                      {node.designation}
                    </span>
                    <div className="hidden group-hover:flex absolute top-full left-0 mt-1 gap-1 z-10">
                      {archived ? (
                        <>
                          <button onClick={() => activateNode(node.node_id)} className="text-xs bg-brand-400 text-white px-2 py-0.5 rounded">Reactivate</button>
                          <button onClick={() => deleteNode(node.node_id)} className="text-xs bg-red-500 text-white px-2 py-0.5 rounded">Delete</button>
                        </>
                      ) : (
                        <button onClick={() => archiveNode(node.node_id)} className="text-xs bg-gray-500 text-white px-2 py-0.5 rounded">Archive</button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  );

  return (
    <div className="space-y-6">
      <h1 className="page-title">Org Structure</h1>

      <div className="flex gap-2 border-b border-gray-200">
        {(["browse", "add", "bulk", "archived"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px capitalize ${
              tab === t ? "border-brand-400 text-brand-600" : "border-transparent text-gray-500"
            }`}
          >
            {t === "bulk" ? "Bulk Import" : t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {tab === "browse" && renderTree()}
      {tab === "archived" && renderTree(true)}

      {tab === "add" && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 max-w-lg space-y-4">
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Department</label>
            <input
              list="dept-list"
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
            />
            <datalist id="dept-list">
              {departments.map((d) => <option key={d} value={d} />)}
            </datalist>
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Business Unit</label>
            <input
              value={businessUnit}
              onChange={(e) => setBusinessUnit(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Designation</label>
            <input
              value={designation}
              onChange={(e) => setDesignation(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
            />
          </div>
          {preview && (
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500">Preview</p>
              <span className={`text-xs px-2 py-0.5 rounded-full ${tierColors[preview.seniority_tier]}`}>
                {preview.seniority_tier}
              </span>
              <p className="text-sm text-gray-600 mt-1">{preview.focus_description}</p>
            </div>
          )}
          <button onClick={addNode} className="bg-brand-400 text-white px-4 py-2 rounded-lg text-sm">
            Add node
          </button>
        </div>
      )}

      {tab === "bulk" && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 max-w-lg space-y-4">
          <textarea
            value={bulkText}
            onChange={(e) => setBulkText(e.target.value)}
            placeholder="Department | Business Unit | Designation (one per line)"
            rows={10}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono"
          />
          <label className="flex items-center gap-2 text-sm text-amber-600">
            <input type="checkbox" checked={replaceExisting} onChange={(e) => setReplaceExisting(e.target.checked)} />
            Replace all existing nodes
          </label>
          <button onClick={bulkImport} className="bg-brand-400 text-white px-4 py-2 rounded-lg text-sm">
            Import nodes
          </button>
        </div>
      )}
    </div>
  );
}
