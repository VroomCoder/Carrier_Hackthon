import { useCallback, useEffect, useRef, useState } from "react";
import { FileText, Upload } from "lucide-react";
import { apiFetch } from "../hooks/api";
import type { PolicyDoc, PolicySearchResult, ToastType } from "../types";

interface Props {
  addToast: (message: string, type?: ToastType) => void;
  setActivePanel: (panel: string) => void;
}

type Tab = "loaded" | "upload" | "search";

function relativeDate(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const days = Math.floor(diff / 86400000);
  if (days === 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;
  return new Date(dateStr).toLocaleDateString();
}

export default function PolicyManager({ addToast }: Props) {
  const [tab, setTab] = useState<Tab>("loaded");
  const [docs, setDocs] = useState<PolicyDoc[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({ title: "", description: "" });
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [testSearchId, setTestSearchId] = useState<string | null>(null);
  const [testQuery, setTestQuery] = useState("");
  const [testResults, setTestResults] = useState<PolicySearchResult[]>([]);

  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<{ title: string; chunk_count: number } | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<PolicySearchResult[]>([]);
  const [searching, setSearching] = useState(false);

  const fetchDocs = useCallback(async () => {
    const res = await apiFetch("/api/policies");
    setDocs(await res.json());
  }, []);

  useEffect(() => {
    if (tab === "loaded") fetchDocs();
  }, [tab, fetchDocs]);

  const handleFileSelect = (f: File) => {
    if (!f.name.toLowerCase().endsWith(".docx")) {
      addToast("Only .docx files are supported", "error");
      return;
    }
    setFile(f);
    setTitle(f.name.replace(/\.docx$/i, ""));
    setUploadResult(null);
  };

  const upload = async () => {
    if (!file) return;
    setUploading(true);
    const form = new FormData();
    form.append("file", file);
    form.append("title", title);
    form.append("description", description);
    try {
      const res = await apiFetch("/api/policies/upload", { method: "POST", body: form });
      if (!res.ok) {
        const err = await res.json();
        addToast(err.detail?.error || err.detail || "Upload failed", "error");
        return;
      }
      const data = await res.json();
      setUploadResult({ title: data.title, chunk_count: data.chunk_count });
      addToast("Document indexed successfully", "success");
      setFile(null);
      setDescription("");
    } catch {
      addToast("Upload failed", "error");
    } finally {
      setUploading(false);
    }
  };

  const saveEdit = async (docId: string) => {
    await apiFetch(`/api/policies/${docId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(editForm),
    });
    setEditingId(null);
    fetchDocs();
    addToast("Document updated", "success");
  };

  const archiveDoc = async (docId: string) => {
    await apiFetch(`/api/policies/${docId}/archive`, { method: "POST" });
    fetchDocs();
    addToast("Document archived", "info");
  };

  const activateDoc = async (docId: string) => {
    await apiFetch(`/api/policies/${docId}/activate`, { method: "POST" });
    fetchDocs();
    addToast("Document reactivated", "success");
  };

  const deleteDoc = async (docId: string) => {
    await apiFetch(`/api/policies/${docId}`, { method: "DELETE" });
    setConfirmDeleteId(null);
    fetchDocs();
    addToast("Document removed", "success");
  };

  const runTestSearch = async (docId: string) => {
    if (!testQuery.trim()) return;
    const res = await apiFetch(
      `/api/policies/search?q=${encodeURIComponent(testQuery)}&doc_id=${docId}&n=5`
    );
    const data = await res.json();
    setTestResults(data.results ?? []);
  };

  const runGlobalSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    const res = await apiFetch(`/api/policies/search?q=${encodeURIComponent(searchQuery)}&n=5`);
    const data = await res.json();
    setSearchResults(data.results ?? []);
    setSearching(false);
  };

  const activeDocs = docs.filter((d) => d.status === "active");
  const archivedDocs = docs.filter((d) => d.status === "archived");

  return (
    <div className="space-y-6">
      <h1 className="page-title">Policy Documents</h1>

      <div className="flex gap-2 border-b border-gray-200">
        {(["loaded", "upload", "search"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px capitalize ${
              tab === t ? "border-brand-400 text-brand-600" : "border-transparent text-gray-500"
            }`}
          >
            {t === "loaded" ? "Loaded documents" : t === "upload" ? "Upload" : "Search policy"}
          </button>
        ))}
      </div>

      {tab === "loaded" && (
        <>
          {docs.length === 0 ? (
            <div className="bg-white border border-gray-200 rounded-xl p-12 text-center">
              <FileText className="w-12 h-12 text-gray-300 mx-auto mb-4" />
              <h2 className="font-medium text-gray-700 mb-2">No policy documents loaded</h2>
              <p className="text-sm text-gray-500 mb-4">
                Upload your performance management policy documents to enable policy-grounded coaching and calibration.
              </p>
              <button
                onClick={() => setTab("upload")}
                className="text-brand-400 text-sm hover:underline"
              >
                Upload your first document →
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              {[...activeDocs, ...archivedDocs].map((doc) => (
                <div
                  key={doc.doc_id}
                  className={`bg-white border border-gray-200 rounded-xl p-5 ${doc.status === "archived" ? "opacity-60" : ""}`}
                >
                  {editingId === doc.doc_id ? (
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
                        <button onClick={() => saveEdit(doc.doc_id)} className="text-xs bg-brand-400 text-white px-3 py-1 rounded-lg">Save</button>
                        <button onClick={() => setEditingId(null)} className="text-xs border border-gray-200 px-3 py-1 rounded-lg">Cancel</button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="flex items-start justify-between">
                        <div className="flex items-start gap-3">
                          <FileText className="w-5 h-5 text-gray-400 mt-0.5" />
                          <div>
                            <p className="font-medium">{doc.title}</p>
                            <p className="text-sm text-gray-500">{doc.filename}</p>
                            {doc.description && <p className="text-sm text-gray-400 mt-1">{doc.description}</p>}
                          </div>
                        </div>
                        <span className={`text-xs px-2 py-0.5 rounded-full ${doc.status === "active" ? "bg-brand-50 text-brand-600" : "bg-gray-100 text-gray-500"}`}>
                          {doc.status}
                        </span>
                      </div>
                      <p className="text-xs text-gray-400 mt-3 ml-8">
                        {doc.chunk_count} sections indexed · Uploaded {relativeDate(doc.uploaded_at)}
                      </p>
                      <div className="flex gap-3 mt-3 ml-8">
                        <button
                          onClick={() => {
                            setEditingId(doc.doc_id);
                            setEditForm({ title: doc.title, description: doc.description });
                          }}
                          className="text-xs text-brand-600 hover:underline"
                        >
                          Edit title
                        </button>
                        {doc.status === "active" ? (
                          <button onClick={() => archiveDoc(doc.doc_id)} className="text-xs text-gray-500 hover:underline">Archive</button>
                        ) : (
                          <button onClick={() => activateDoc(doc.doc_id)} className="text-xs text-brand-600 hover:underline">Reactivate</button>
                        )}
                        <button onClick={() => setConfirmDeleteId(doc.doc_id)} className="text-xs text-red-500 hover:underline">Delete</button>
                        <button
                          onClick={() => {
                            setTestSearchId(testSearchId === doc.doc_id ? null : doc.doc_id);
                            setTestResults([]);
                          }}
                          className="text-xs text-gray-500 hover:underline"
                        >
                          Test search
                        </button>
                      </div>
                      {confirmDeleteId === doc.doc_id && (
                        <div className="mt-3 ml-8 p-3 bg-red-50 border border-red-100 rounded-lg">
                          <p className="text-sm text-red-700">Remove this document and all indexed sections? This cannot be undone.</p>
                          <div className="flex gap-2 mt-2">
                            <button onClick={() => deleteDoc(doc.doc_id)} className="text-xs bg-red-500 text-white px-3 py-1 rounded-lg">Confirm delete</button>
                            <button onClick={() => setConfirmDeleteId(null)} className="text-xs border border-gray-200 px-3 py-1 rounded-lg">Cancel</button>
                          </div>
                        </div>
                      )}
                      {testSearchId === doc.doc_id && (
                        <div className="mt-3 ml-8 space-y-2">
                          <div className="flex gap-2">
                            <input
                              value={testQuery}
                              onChange={(e) => setTestQuery(e.target.value)}
                              placeholder="Test search query..."
                              className="flex-1 border border-gray-200 rounded-lg px-3 py-1 text-sm"
                            />
                            <button onClick={() => runTestSearch(doc.doc_id)} className="text-xs bg-brand-400 text-white px-3 py-1 rounded-lg">Search</button>
                          </div>
                          {testResults.map((r, i) => (
                            <div key={i} className="bg-gray-50 rounded-lg p-2 text-xs">
                              <span className="font-medium">{r.section_title}</span>
                              <p className="text-gray-600 mt-1">{r.text.slice(0, 200)}...</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {tab === "upload" && (
        <div className="max-w-lg space-y-4">
          <div>
            <h2 className="font-medium text-gray-700">Upload policy document</h2>
            <p className="text-sm text-gray-500 mt-1">
              Word documents (.docx) only. The document will be automatically chunked by section and indexed for semantic search.
            </p>
          </div>

          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              const f = e.dataTransfer.files[0];
              if (f) handleFileSelect(f);
            }}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors ${
              dragOver ? "border-brand-400 bg-brand-50" : "border-gray-200 hover:border-brand-300"
            }`}
          >
            <Upload className="w-8 h-8 text-gray-400 mx-auto mb-3" />
            <p className="text-sm text-gray-600">Drag & drop your .docx file here, or click to browse</p>
            <input
              ref={fileInputRef}
              type="file"
              accept=".docx"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && handleFileSelect(e.target.files[0])}
            />
          </div>

          {file && (
            <p className="text-sm text-gray-600">
              {file.name} ({(file.size / 1024).toFixed(1)} KB)
            </p>
          )}

          {file && (
            <div className="space-y-3">
              <div>
                <label className="text-xs text-gray-500 mb-1 block">Title</label>
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1 block">Description (optional)</label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={2}
                  placeholder="e.g. Annual performance review process, rating scales, and SMART goal standards"
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                />
              </div>
            </div>
          )}

          <button
            onClick={upload}
            disabled={!file || uploading}
            className="bg-brand-400 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-brand-600 disabled:opacity-50"
          >
            {uploading ? "Processing document..." : "Upload & index"}
          </button>

          {uploadResult && (
            <div className="bg-brand-50 border border-brand-100 rounded-xl p-4">
              <p className="text-brand-700 font-medium">✓ {uploadResult.title} indexed successfully</p>
              <p className="text-sm text-brand-600 mt-1">{uploadResult.chunk_count} sections found and indexed</p>
              <p className="text-sm text-gray-600 mt-1">The document is now available to all agents.</p>
              <button onClick={() => setTab("loaded")} className="text-brand-400 text-sm mt-2 hover:underline">
                Switch to Loaded Documents →
              </button>
            </div>
          )}
        </div>
      )}

      {tab === "search" && (
        <div className="space-y-4">
          <div>
            <h2 className="font-medium text-gray-700">Test policy search</h2>
            <p className="text-sm text-gray-500 mt-1">
              Type any query to see which policy sections the agents would retrieve. Useful for verifying your documents were indexed correctly.
            </p>
          </div>
          <div className="flex gap-2">
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="e.g. SMART goal criteria, rating definitions..."
              className="flex-1 border border-gray-200 rounded-lg px-4 py-2 text-sm"
              onKeyDown={(e) => e.key === "Enter" && runGlobalSearch()}
            />
            <button
              onClick={runGlobalSearch}
              disabled={searching}
              className="bg-brand-400 text-white px-5 py-2 rounded-lg text-sm"
            >
              Search
            </button>
          </div>
          {searchResults.length === 0 && searchQuery && !searching && (
            <p className="text-sm text-gray-500">
              No matching policy sections found. Try different search terms or check that your documents are loaded.
            </p>
          )}
          <div className="space-y-3">
            {searchResults.map((r, i) => (
              <div key={i} className="bg-white border border-gray-200 rounded-xl p-4">
                <div className="flex justify-between mb-2">
                  <span className="text-sm font-medium">{r.section_title}</span>
                  <span className="text-xs text-gray-400">{r.doc_title}</span>
                </div>
                <p className="text-sm text-gray-600">{r.text.slice(0, 200)}{r.text.length > 200 ? "..." : ""}</p>
                <p className="text-xs text-gray-400 mt-2 text-right">Chunk {r.chunk_index}</p>
              </div>
            ))}
          </div>
          <p className="text-xs text-gray-400">
            This is the same search the agents run before every calibration and coaching session.
          </p>
        </div>
      )}
    </div>
  );
}
