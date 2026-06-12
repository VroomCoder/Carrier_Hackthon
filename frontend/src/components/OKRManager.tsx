import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../hooks/api";
import type { Employee, OKRDoc, ToastType } from "../types";
import { OKR_CATEGORIES } from "../data/seedData";

interface Props {
  activeEmployee: Employee | null;
  addToast: (message: string, type?: ToastType) => void;
}

const categoryColors: Record<string, string> = {
  Engineering: "bg-brand-100 text-brand-700",
  Sales: "bg-blue-100 text-blue-700",
  People: "bg-purple-100 text-purple-700",
  Product: "bg-amber-100 text-amber-700",
  Security: "bg-red-100 text-red-700",
  "Customer Success": "bg-orange-100 text-orange-700",
  Finance: "bg-green-100 text-green-700",
  Other: "bg-gray-100 text-gray-700",
};

type Tab = "active" | "archived" | "add";

export default function OKRManager({ activeEmployee, addToast }: Props) {
  const [tab, setTab] = useState<Tab>("active");
  const [okrs, setOkrs] = useState<OKRDoc[]>([]);
  const [relevantOnly, setRelevantOnly] = useState(true);
  const [cycleFilter, setCycleFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [textFilter, setTextFilter] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({ title: "", description: "", category: "", owner: "", cycle: "" });
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Array<Record<string, string>>>([]);

  const [newOkr, setNewOkr] = useState({ title: "", description: "", category: "Engineering", owner: "", cycle: "FY2025" });
  const [bulkText, setBulkText] = useState("");
  const [replaceExisting, setReplaceExisting] = useState(false);

  const fetchOkrs = useCallback(async () => {
    const status = tab === "archived" ? "archived" : "active";
    let url = `/api/okrs?status=${status}`;
    if (relevantOnly && activeEmployee && tab === "active") {
      url += `&department=${encodeURIComponent(activeEmployee.department)}`;
    }
    const res = await apiFetch(url);
    setOkrs(await res.json());
  }, [tab, relevantOnly, activeEmployee]);

  useEffect(() => {
    if (tab !== "add") fetchOkrs();
  }, [tab, fetchOkrs]);

  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults([]);
      return;
    }
    const timer = setTimeout(() => {
      apiFetch(`/api/okrs/search?q=${encodeURIComponent(searchQuery)}&n=3`)
        .then((r) => r.json())
        .then((d) => setSearchResults(d.results ?? []))
        .catch(() => setSearchResults([]));
    }, 400);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const filtered = okrs.filter((o) => {
    if (cycleFilter && o.cycle !== cycleFilter) return false;
    if (categoryFilter && o.category !== categoryFilter) return false;
    if (textFilter && !o.title.toLowerCase().includes(textFilter.toLowerCase())) return false;
    return true;
  });

  const cycles = [...new Set(okrs.map((o) => o.cycle))];

  const createOkr = async () => {
    const res = await apiFetch("/api/okrs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(newOkr),
    });
    if (res.ok) {
      addToast("OKR created", "success");
      setNewOkr({ title: "", description: "", category: "Engineering", owner: "", cycle: "FY2025" });
      setTab("active");
    } else {
      addToast("Failed to create OKR", "error");
    }
  };

  const bulkImport = async () => {
    const lines = bulkText.trim().split("\n").filter(Boolean);
    const okrsData = lines.map((line) => {
      const [title, description, category] = line.split("|").map((s) => s.trim());
      return { title, description, category: category || "Other", owner: "", cycle: "FY2025" };
    });
    const res = await apiFetch("/api/okrs/bulk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ okrs: okrsData, replace_existing: replaceExisting }),
    });
    const data = await res.json();
    addToast(`Imported ${data.imported} OKRs`, "success");
    setBulkText("");
    setTab("active");
  };

  const saveEdit = async (okrId: string) => {
    await apiFetch(`/api/okrs/${okrId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(editForm),
    });
    setEditingId(null);
    fetchOkrs();
    addToast("OKR updated", "success");
  };

  const archiveOkr = async (okrId: string) => {
    await apiFetch(`/api/okrs/${okrId}/archive`, { method: "POST" });
    fetchOkrs();
    addToast("OKR archived", "info");
  };

  const activateOkr = async (okrId: string) => {
    await apiFetch(`/api/okrs/${okrId}/activate`, { method: "POST" });
    fetchOkrs();
    addToast("OKR reactivated", "success");
  };

  const deleteOkr = async (okrId: string) => {
    if (!confirm("Delete this OKR permanently?")) return;
    await apiFetch(`/api/okrs/${okrId}`, { method: "DELETE" });
    fetchOkrs();
    addToast("OKR deleted", "info");
  };

  const renderCard = (okr: OKRDoc) => (
    <div
      key={okr.okr_id}
      className={`bg-white border border-gray-200 rounded-xl p-4 ${tab === "archived" ? "opacity-60" : ""}`}
    >
      {editingId === okr.okr_id ? (
        <div className="space-y-2">
          <input
            value={editForm.title}
            onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
            className="w-full border border-gray-200 rounded-lg px-3 py-1 text-sm"
          />
          <textarea
            value={editForm.description}
            onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
            rows={2}
            className="w-full border border-gray-200 rounded-lg px-3 py-1 text-sm"
          />
          <div className="flex gap-2">
            <button onClick={() => saveEdit(okr.okr_id)} className="text-xs bg-brand-400 text-white px-3 py-1 rounded-lg">Save</button>
            <button onClick={() => setEditingId(null)} className="text-xs border border-gray-200 px-3 py-1 rounded-lg">Cancel</button>
          </div>
        </div>
      ) : (
        <>
          <div className="flex items-start gap-2 mb-2">
            <span className={`text-xs px-2 py-0.5 rounded-full ${categoryColors[okr.category] ?? categoryColors.Other}`}>
              {okr.category}
            </span>
            <span className="text-xs text-gray-400">{okr.cycle}</span>
          </div>
          <h3 className="font-medium text-sm">{okr.title}</h3>
          <p className="text-xs text-gray-500 mt-1 line-clamp-2">{okr.description}</p>
          <p className="text-xs text-gray-400 mt-2">{okr.owner}</p>
          <div className="flex gap-2 mt-3">
            {tab === "active" ? (
              <>
                <button
                  onClick={() => {
                    setEditingId(okr.okr_id);
                    setEditForm({ title: okr.title, description: okr.description, category: okr.category, owner: okr.owner, cycle: okr.cycle });
                  }}
                  className="text-xs text-brand-600 hover:underline"
                >
                  Edit
                </button>
                <button onClick={() => archiveOkr(okr.okr_id)} className="text-xs text-gray-500 hover:underline">Archive</button>
                <button onClick={() => deleteOkr(okr.okr_id)} className="text-xs text-red-500 hover:underline">Delete</button>
              </>
            ) : (
              <>
                <button onClick={() => activateOkr(okr.okr_id)} className="text-xs text-brand-600 hover:underline">Reactivate</button>
                <button onClick={() => deleteOkr(okr.okr_id)} className="text-xs text-red-500 hover:underline">Delete</button>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );

  return (
    <div className="space-y-6">
      <h1 className="page-title">Company OKRs</h1>

      <div className="flex gap-2 border-b border-gray-200">
        {(["active", "archived", "add"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
              tab === t ? "border-brand-400 text-brand-600" : "border-transparent text-gray-500"
            }`}
          >
            {t === "add" ? "Add / Import" : t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {tab === "active" && (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={() => setRelevantOnly(!relevantOnly)}
              className={`text-xs px-3 py-1 rounded-full ${relevantOnly ? "bg-brand-400 text-white" : "bg-gray-100 text-gray-600"}`}
            >
              {relevantOnly ? "Relevant only" : "Show all"}
            </button>
            <select
              value={cycleFilter}
              onChange={(e) => setCycleFilter(e.target.value)}
              className="text-xs border border-gray-200 rounded-lg px-2 py-1"
            >
              <option value="">All cycles</option>
              {cycles.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <div className="flex gap-1 flex-wrap">
              {OKR_CATEGORIES.map((cat) => (
                <button
                  key={cat}
                  onClick={() => setCategoryFilter(categoryFilter === cat ? "" : cat)}
                  className={`text-xs px-2 py-0.5 rounded-full ${
                    categoryFilter === cat ? "bg-brand-400 text-white" : "bg-gray-100 text-gray-600"
                  }`}
                >
                  {cat}
                </button>
              ))}
            </div>
            <input
              value={textFilter}
              onChange={(e) => setTextFilter(e.target.value)}
              placeholder="Search titles..."
              className="text-xs border border-gray-200 rounded-lg px-3 py-1 ml-auto"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            {filtered.map(renderCard)}
          </div>
        </>
      )}

      {tab === "archived" && (
        <div className="grid grid-cols-2 gap-4">
          {filtered.map(renderCard)}
        </div>
      )}

      {tab === "add" && (
        <div className="grid grid-cols-2 gap-6">
          <div className="space-y-3">
            <h2 className="text-sm font-medium text-gray-500">Add Single OKR</h2>
            <input
              value={newOkr.title}
              onChange={(e) => setNewOkr({ ...newOkr, title: e.target.value })}
              placeholder="Title"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
            />
            <textarea
              value={newOkr.description}
              onChange={(e) => setNewOkr({ ...newOkr, description: e.target.value })}
              placeholder="Description"
              rows={3}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
            />
            <select
              value={newOkr.category}
              onChange={(e) => setNewOkr({ ...newOkr, category: e.target.value })}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
            >
              {OKR_CATEGORIES.map((c) => <option key={c}>{c}</option>)}
            </select>
            <input
              value={newOkr.owner}
              onChange={(e) => setNewOkr({ ...newOkr, owner: e.target.value })}
              placeholder="Owner"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
            />
            <button onClick={createOkr} className="bg-brand-400 text-white px-4 py-2 rounded-lg text-sm">
              Create OKR
            </button>
          </div>
          <div className="space-y-3">
            <h2 className="text-sm font-medium text-gray-500">Bulk Import</h2>
            <textarea
              value={bulkText}
              onChange={(e) => setBulkText(e.target.value)}
              placeholder="Title | Description | Category (one per line)"
              rows={8}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono"
            />
            <label className="flex items-center gap-2 text-sm text-amber-600">
              <input type="checkbox" checked={replaceExisting} onChange={(e) => setReplaceExisting(e.target.checked)} />
              Replace all existing OKRs
            </label>
            <button onClick={bulkImport} className="bg-brand-400 text-white px-4 py-2 rounded-lg text-sm">
              Import OKRs
            </button>
          </div>
        </div>
      )}

      <div className="bg-white border border-gray-200 rounded-xl p-4">
        <h2 className="text-sm font-medium text-gray-500 mb-3">Test OKR Alignment</h2>
        <input
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Type a goal to test semantic matching..."
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm mb-3"
        />
        <div className="grid grid-cols-3 gap-3">
          {searchResults.map((r, i) => (
            <div key={i} className="border border-gray-100 rounded-lg p-3">
              <span className="text-xs text-brand-600 font-medium">#{i + 1}</span>
              <p className="text-sm font-medium mt-1">{r.title}</p>
              <span className="text-xs text-gray-400">{r.category}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
