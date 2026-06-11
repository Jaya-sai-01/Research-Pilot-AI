import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useSharedChat } from '../context/ChatContext';
import api from '../services/api';
import { useNavigate } from 'react-router-dom';
import {
  FileText,
  Search,
  Trash2,
  Eye,
  Loader2,
  Copy,
  Check,
  X,
  Database,
  AlertTriangle,
  GitCompare,
  MessageSquare,
} from 'lucide-react';

interface Document {
  id: number;
  title: string;
  doc_type: string;
  content: string;
  created_at: string;
}

interface SemanticMatch {
  content: string;
  metadata: {
    paper_id: number;
    title: string;
    chunk_index: number;
  };
  score: number;
}

type DeleteMode = 'selected' | 'all';
type ToastType = 'success' | 'error';

interface Toast {
  type: ToastType;
  message: string;
}

const reportLabels: Record<string, string> = {
  summary: 'Summary',
  insights: 'Insights',
  lit_review: 'Literature Review',
  comparison: 'Comparison',
  review: 'Research Paper Review',
};

const DocSpace: React.FC = () => {
  const { activeWorkspace } = useAuth();
  const navigate = useNavigate();
  const { sendMessage, setAssistantOpen } = useSharedChat();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [semanticQuery, setSemanticQuery] = useState('');
  const [semanticResults, setSemanticResults] = useState<SemanticMatch[]>([]);
  const [searching, setSearching] = useState(false);
  const [loading, setLoading] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState<Document | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [deleteMode, setDeleteMode] = useState<DeleteMode | null>(null);
  const [copied, setCopied] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [toast, setToast] = useState<Toast | null>(null);
  const [error, setError] = useState('');

  const selectedCount = selectedIds.size;
  const allSelected = documents.length > 0 && selectedCount === documents.length;
  const confirmCount = deleteMode === 'all' ? documents.length : selectedCount;

  const showToast = (type: ToastType, message: string) => {
    setToast({ type, message });
    setTimeout(() => setToast(null), 3200);
  };

  const fetchDocuments = async () => {
    if (!activeWorkspace) return;
    setLoading(true);
    setError('');
    try {
      const response = await api.get(`/tools/workspace/${activeWorkspace.id}/documents`);
      setDocuments(response.data);
      setSelectedIds((previous) => {
        const available = new Set(response.data.map((doc: Document) => doc.id));
        return new Set([...previous].filter((id) => available.has(id)));
      });
    } catch (err) {
      console.error(err);
      setError('Failed to load workspace reports.');
      showToast('error', 'Failed to load workspace reports.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
    setSemanticResults([]);
    setSemanticQuery('');
    setSelectedIds(new Set());
  }, [activeWorkspace]);

  const handleSemanticSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!semanticQuery.trim() || !activeWorkspace) return;

    setSearching(true);
    setError('');
    try {
      const response = await api.post(`/tools/workspace/${activeWorkspace.id}/documents/search`, {
        query: semanticQuery,
      });
      setSemanticResults(response.data);
    } catch (err) {
      console.error(err);
      setError('Semantic vector query failed. Verify vector database status.');
      showToast('error', 'Semantic vector query failed.');
    } finally {
      setSearching(false);
    }
  };

  const toggleSelected = (docId: number) => {
    setSelectedIds((previous) => {
      const next = new Set(previous);
      if (next.has(docId)) {
        next.delete(docId);
      } else {
        next.add(docId);
      }
      return next;
    });
  };

  const toggleSelectAll = () => {
    setSelectedIds(allSelected ? new Set() : new Set(documents.map((doc) => doc.id)));
  };

  const handleDelete = async (docId: number) => {
    if (!activeWorkspace) return;
    setDeletingId(docId);
    setError('');
    try {
      await api.delete(`/tools/workspace/${activeWorkspace.id}/documents/${docId}`);
      setDocuments((prev) => prev.filter((doc) => doc.id !== docId));
      setSelectedIds((previous) => {
        const next = new Set(previous);
        next.delete(docId);
        return next;
      });
      if (selectedDoc?.id === docId) {
        setSelectedDoc(null);
      }
      showToast('success', 'Report deleted.');
    } catch (err) {
      console.error(err);
      setError('Failed to delete report document.');
      showToast('error', 'Failed to delete report.');
    } finally {
      setDeletingId(null);
    }
  };

  const handleBulkDelete = async () => {
    if (!activeWorkspace || !deleteMode) return;
    setBulkDeleting(true);
    setError('');
    try {
      const payload =
        deleteMode === 'all'
          ? { delete_all: true }
          : { delete_all: false, document_ids: [...selectedIds] };
      const response = await api.post(`/tools/workspace/${activeWorkspace.id}/documents/bulk-delete`, payload);
      await fetchDocuments();
      if (selectedDoc && (deleteMode === 'all' || selectedIds.has(selectedDoc.id))) {
        setSelectedDoc(null);
      }
      setSelectedIds(new Set());
      setDeleteMode(null);
      showToast('success', `${response.data.deleted_count || confirmCount} report(s) deleted.`);
    } catch (err: any) {
      console.error(err);
      const message = err.response?.data?.detail || 'Failed to delete reports.';
      setError(message);
      showToast('error', message);
    } finally {
      setBulkDeleting(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const askAboutReport = (doc: Document, explain = false) => {
    const reportType = reportLabels[doc.doc_type] || 'report';
    const prompt = explain
      ? `Explain the ${reportType.toLowerCase()} "${doc.title}". Clarify its main findings, evidence, and practical implications.`
      : `Answer questions about the ${reportType.toLowerCase()} "${doc.title}". Start with the most important findings and identify any evidence limitations.`;
    setSelectedDoc(null);
    setAssistantOpen(false);
    navigate('/chat');
    void sendMessage(prompt, { documentIds: [doc.id] });
  };

  const compareSelectedReports = () => {
    const selectedDocuments = documents.filter((doc) => selectedIds.has(doc.id));
    if (selectedDocuments.length < 2) return;
    const titles = selectedDocuments.map((doc) => `"${doc.title}"`).join(', ');
    setAssistantOpen(false);
    navigate('/chat');
    void sendMessage(
      `Compare these selected research reports: ${titles}. Contrast their findings, evidence, limitations, and recommendations.`,
      { documentIds: selectedDocuments.map((doc) => doc.id) },
    );
  };

  if (!activeWorkspace) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center space-y-4">
        <FileText size={48} className="text-slate-700" />
        <h2 className="text-xl font-bold text-slate-300">No Active Workspace Selected</h2>
        <p className="text-slate-500 max-w-sm text-sm">
          Please select or create an active workspace first to view document archives.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-8 p-1">
      {toast && (
        <div
          className={`fixed top-5 right-5 z-[70] rounded-xl border px-4 py-3 text-sm font-semibold shadow-glass backdrop-blur-md ${
            toast.type === 'success'
              ? 'bg-emerald-950/90 text-emerald-300 border-emerald-800/60'
              : 'bg-red-950/90 text-red-300 border-red-800/60'
          }`}
        >
          {toast.message}
        </div>
      )}

      <div>
        <h1 className="text-3xl font-bold text-white tracking-tight">Document Space</h1>
        <p className="text-slate-400 text-sm">
          Explore AI reports and run semantic searches across vector-indexed papers.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-6">
          <div className="glass-panel p-6 space-y-4">
            <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
              <h3 className="font-bold text-base text-white flex items-center gap-2">
                <FileText size={18} className="text-brand-400" />
                <span>Generated AI Reports</span>
                <span className="text-xs text-slate-500 font-semibold">({documents.length})</span>
              </h3>
              {documents.length > 0 && (
                <div className="flex flex-wrap items-center gap-2">
                  <label className="flex items-center gap-2 rounded-xl border border-slate-750 hover:border-slate-700 bg-slate-800/40 hover:bg-slate-800/80 px-3 py-2 text-xs font-semibold text-slate-300 cursor-pointer transition-colors duration-150">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      onChange={toggleSelectAll}
                      disabled={bulkDeleting}
                      className="accent-brand-500"
                    />
                    <span>Select All</span>
                  </label>
                  <button
                    onClick={compareSelectedReports}
                    disabled={selectedCount < 2 || bulkDeleting}
                    className="flex items-center gap-1.5 rounded-xl border border-brand-500/30 hover:border-brand-500/60 bg-brand-950/20 hover:bg-brand-950/50 px-3 py-2 text-xs font-bold text-brand-300 hover:text-brand-200 disabled:opacity-45 transition-colors duration-150 cursor-pointer"
                  >
                    <GitCompare size={14} />
                    <span>Compare Selected</span>
                  </button>
                  <button
                    onClick={() => setDeleteMode('selected')}
                    disabled={selectedCount === 0 || bulkDeleting}
                    className="flex items-center gap-1.5 rounded-xl border border-red-900/40 hover:border-red-800/60 bg-red-950/20 hover:bg-red-950/50 px-3 py-2 text-xs font-bold text-red-400 hover:text-red-350 disabled:opacity-40 transition-colors duration-150 cursor-pointer"
                  >
                    <Trash2 size={14} />
                    <span>Delete Selected ({selectedCount})</span>
                  </button>
                  <button
                    onClick={() => setDeleteMode('all')}
                    disabled={bulkDeleting}
                    className="flex items-center gap-1.5 rounded-xl border border-red-900/50 hover:border-red-800 bg-red-950 bg-opacity-30 hover:bg-red-900 text-red-200 hover:text-white px-3 py-2 text-xs font-bold transition-all duration-150 cursor-pointer disabled:opacity-50"
                  >
                    <Trash2 size={14} />
                    <span>Clear All Reports</span>
                  </button>
                </div>
              )}
            </div>

            {error && (
              <div className="bg-red-950 bg-opacity-40 border border-red-900 border-opacity-50 text-red-300 text-xs p-3.5 rounded-xl">
                {error}
              </div>
            )}

            {loading ? (
              <div className="py-16 flex justify-center">
                <Loader2 size={24} className="animate-spin text-brand-500" />
              </div>
            ) : documents.length === 0 ? (
              <div className="py-16 text-center text-slate-500 text-sm">
                No reports compiled yet. Use the AI Tools Hub to generate literature reviews or summaries.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {documents.map((doc) => (
                  <div key={doc.id} className="p-5 bg-slate-850 hover:bg-slate-800 border border-slate-750 hover:border-slate-700 rounded-2xl flex flex-col justify-between space-y-4 transition-all duration-150 shadow-sm">
                    <div className="space-y-2">
                      <div className="flex items-start gap-3">
                        <input
                          type="checkbox"
                          checked={selectedIds.has(doc.id)}
                          onChange={() => toggleSelected(doc.id)}
                          disabled={bulkDeleting || deletingId === doc.id}
                          className="mt-1 accent-brand-500"
                          aria-label={`Select ${doc.title}`}
                        />
                        <div className="min-w-0">
                          <span className="inline-block text-[9px] font-bold bg-brand-950/40 text-brand-400 border border-brand-500/20 px-2 py-0.5 rounded-md uppercase tracking-wider">
                            {reportLabels[doc.doc_type] || 'AI Report'}
                          </span>
                          <h4 className="font-bold text-sm text-slate-200 line-clamp-1 mt-2" title={doc.title}>
                            {doc.title}
                          </h4>
                          <p className="text-[10px] text-slate-500 font-medium">
                            Created: {new Date(doc.created_at).toLocaleDateString()}
                          </p>
                        </div>
                      </div>
                    </div>

                    <div className="flex justify-end gap-2 border-t border-slate-750/50 pt-3">
                      <button
                        onClick={() => askAboutReport(doc)}
                        disabled={bulkDeleting}
                        className="flex items-center gap-1.5 rounded-lg bg-brand-950/40 hover:bg-brand-900/50 border border-brand-500/20 hover:border-brand-500/40 px-2.5 py-1.5 text-xs font-semibold text-brand-300 hover:text-brand-200 transition-all duration-150 disabled:opacity-50 cursor-pointer"
                        title="Ask AI about this report"
                      >
                        <MessageSquare size={14} />
                        <span>Ask AI</span>
                      </button>
                      <button
                        onClick={() => setSelectedDoc(doc)}
                        disabled={bulkDeleting}
                        className="p-1.5 bg-slate-800 hover:bg-slate-750 border border-slate-750 hover:border-slate-700 text-slate-300 hover:text-white rounded-lg transition-all duration-150 cursor-pointer disabled:opacity-50"
                        title="View report content"
                      >
                        <Eye size={14} />
                      </button>
                      <button
                        onClick={() => handleDelete(doc.id)}
                        disabled={deletingId === doc.id || bulkDeleting}
                        className="p-1.5 bg-red-950 bg-opacity-30 hover:bg-red-900 text-red-300 hover:text-white rounded-lg border border-red-900/30 hover:border-red-900/60 transition-all duration-150 cursor-pointer disabled:opacity-50"
                        title="Delete report"
                      >
                        {deletingId === doc.id ? (
                          <Loader2 size={14} className="animate-spin" />
                        ) : (
                          <Trash2 size={14} />
                        )}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="space-y-6">
          <div className="glass-panel p-6 flex flex-col h-full space-y-4">
            <div>
              <h3 className="font-bold text-base text-white flex items-center gap-2">
                <Database size={18} className="text-emerald-400" />
                <span>Semantic Vector Search</span>
              </h3>
              <p className="text-slate-500 text-xs mt-1">
                Query the ChromaDB collection directly using natural language to retrieve highly relevant paper snippets.
              </p>
            </div>

            <form onSubmit={handleSemanticSearch} className="flex gap-2">
              <input
                type="text"
                value={semanticQuery}
                onChange={(e) => setSemanticQuery(e.target.value)}
                placeholder="Type semantic query (e.g. attention layers)..."
                className="flex-1 glass-input py-2 px-3 text-xs"
                required
              />
              <button
                type="submit"
                disabled={searching || !semanticQuery.trim()}
                className="bg-brand-500 hover:bg-brand-600 text-white p-2.5 rounded-xl cursor-pointer shadow-sm hover:shadow-glow active:scale-[0.98] transition-all duration-150 disabled:opacity-50 disabled:hover:bg-brand-500"
              >
                {searching ? <Loader2 size={15} className="animate-spin" /> : <Search size={15} />}
              </button>
            </form>

            <div className="flex-1 overflow-y-auto max-h-[380px] space-y-3.5 pr-1">
              {searching ? (
                <div className="py-12 flex justify-center">
                  <Loader2 size={20} className="animate-spin text-brand-500" />
                </div>
              ) : semanticResults.length === 0 ? (
                <div className="py-12 text-center text-xs text-slate-500 font-medium">
                  Submit query to scan ChromaDB index chunks.
                </div>
              ) : (
                semanticResults.map((match, i) => (
                  <div key={i} className="p-4 bg-slate-850 hover:bg-slate-800 border border-slate-750 hover:border-slate-700 rounded-xl space-y-2 text-left transition-all duration-150 shadow-sm">
                    <div className="flex justify-between items-center text-[10px] font-bold">
                      <span className="text-emerald-400/90 font-semibold tracking-wide uppercase">
                        Match Score: {(match.score * 100).toFixed(1)}%
                      </span>
                      <span className="text-slate-500 truncate max-w-[120px]" title={match.metadata.title}>
                        {match.metadata.title}
                      </span>
                    </div>
                    <p className="text-slate-300 text-xs leading-relaxed line-clamp-5 font-normal">
                      "{match.content}"
                    </p>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      {deleteMode && (
        <div className="fixed inset-0 bg-black bg-opacity-70 backdrop-blur-sm flex items-center justify-center z-[60] p-4">
          <div className="glass-panel max-w-md w-full p-6 border border-red-900/50 shadow-2xl animate-fadeIn">
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-xl bg-red-950 text-red-300 border border-red-900 border-opacity-45">
                <AlertTriangle size={20} />
              </div>
              <div>
                <h2 className="text-xl font-bold text-white">Delete Reports?</h2>
                <p className="text-sm text-slate-400 mt-1">
                  Total reports selected: <span className="font-bold text-white">{confirmCount}</span>
                </p>
              </div>
            </div>
            <div className="rounded-xl border border-red-900 border-opacity-35 bg-red-950 bg-opacity-20 p-4 mt-5 text-sm text-red-100">
              This deletion is irreversible. The selected report records will be permanently removed from the database.
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setDeleteMode(null)}
                disabled={bulkDeleting}
                className="px-4 py-2 text-sm font-semibold text-slate-400 hover:text-white cursor-pointer disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleBulkDelete}
                disabled={bulkDeleting || confirmCount === 0}
                className="inline-flex items-center gap-2 rounded-xl bg-red-700 hover:bg-red-600 px-5 py-2 text-sm font-bold text-white transition-colors disabled:opacity-50 cursor-pointer"
              >
                {bulkDeleting && <Loader2 size={14} className="animate-spin" />}
                <span>Delete All</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {selectedDoc && (
        <div className="fixed inset-0 bg-black bg-opacity-65 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="glass-panel max-w-2xl w-full p-6 relative shadow-2xl animate-fadeIn max-h-[85vh] flex flex-col">
            <button
              onClick={() => setSelectedDoc(null)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white cursor-pointer"
            >
              <X size={20} />
            </button>
            <div className="overflow-y-auto pr-1 space-y-4">
              <div className="flex justify-between items-start mr-6">
                <div>
                  <span className="text-[10px] font-bold text-brand-400 uppercase tracking-wider">
                    {reportLabels[selectedDoc.doc_type] || 'AI Report'}
                  </span>
                  <h2 className="text-xl font-bold text-white mt-1 leading-tight">{selectedDoc.title}</h2>
                </div>
                <button
                  onClick={() => copyToClipboard(selectedDoc.content)}
                  className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-all duration-150 py-1.5 px-3 bg-slate-800 hover:bg-slate-750 border border-slate-750 hover:border-slate-700 rounded-xl cursor-pointer"
                >
                  {copied ? (
                    <>
                      <Check size={12} className="text-emerald-400" />
                      <span className="text-emerald-400 font-semibold">Copied</span>
                    </>
                  ) : (
                    <>
                      <Copy size={12} />
                      <span>Copy</span>
                    </>
                  )}
                </button>
              </div>
              <hr className="border-slate-800" />
              <div className="space-y-1">
                <div className="bg-slate-950 border border-slate-750 p-6 rounded-2xl text-slate-200 text-sm leading-relaxed whitespace-pre-wrap max-h-[480px] overflow-y-auto pr-1 text-left font-normal select-text font-sans">
                  {selectedDoc.content}
                </div>
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button
                  onClick={() => askAboutReport(selectedDoc, true)}
                  className="inline-flex items-center gap-2 rounded-xl border border-brand-500/35 hover:border-brand-500/60 bg-brand-950/20 hover:bg-brand-900 px-4 py-2.5 text-sm font-semibold text-brand-300 hover:text-white transition-all duration-150 cursor-pointer"
                >
                  <MessageSquare size={15} />
                  <span>{selectedDoc.doc_type === 'summary' ? 'Explain This Summary' : 'Explain This Report'}</span>
                </button>
                <button
                  onClick={() => setSelectedDoc(null)}
                  className="btn-primary py-2.5 px-5"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default DocSpace;
