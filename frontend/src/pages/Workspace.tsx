import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useSharedChat } from '../context/ChatContext';
import api, { API_URL } from '../services/api';
import { Link, useNavigate } from 'react-router-dom';
import { AlertTriangle, FolderGit, Trash2, Eye, Loader2, BookOpen, Link2, X, ExternalLink, GitCompare } from 'lucide-react';

interface Paper {
  id: number;
  title: string;
  authors: string;
  abstract: string;
  published_date: string;
  source?: string;
  doi?: string;
  doi_url?: string;
  pdf_url?: string;
  source_url?: string;
  publisher_url?: string;
  ieee_url?: string;
  preferred_access_url?: string;
  preferred_access_type?: string;
  file_path?: string;
  indexed_status: boolean;
  created_at: string;
}

interface AccessResolution {
  access_url?: string;
  access_type: string;
  fallback_used: boolean;
  response_status?: number;
  message?: string;
}

type DeleteMode = 'selected' | 'all';
type ToastType = 'success' | 'error';

interface Toast {
  type: ToastType;
  message: string;
}

const Workspace: React.FC = () => {
  const { activeWorkspace } = useAuth();
  const navigate = useNavigate();
  const { sendMessage, setAssistantOpen } = useSharedChat();
  const [papers, setPapers] = useState<Paper[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(false);
  const [selectedPaper, setSelectedPaper] = useState<Paper | null>(null);
  const [deleteMode, setDeleteMode] = useState<DeleteMode | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [openingId, setOpeningId] = useState<number | null>(null);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [toast, setToast] = useState<Toast | null>(null);
  const [error, setError] = useState('');

  const selectedCount = selectedIds.size;
  const allSelected = papers.length > 0 && selectedCount === papers.length;
  const confirmCount = deleteMode === 'all' ? papers.length : selectedCount;

  const showToast = (type: ToastType, message: string) => {
    setToast({ type, message });
    setTimeout(() => setToast(null), 3200);
  };

  const getStoredAccessType = (paper: Paper) => {
    if (paper.file_path) return 'Local PDF';
    if (paper.preferred_access_type) return paper.preferred_access_type;
    if (paper.pdf_url) return 'Open PDF';
    if (paper.doi_url || paper.doi) return 'DOI';
    if (paper.publisher_url || paper.source_url) return 'Publisher Page';
    if (paper.ieee_url) return 'IEEE Page';
    return 'Unavailable';
  };

  const getDoiUrl = (paper: Paper) =>
    paper.doi_url || (paper.doi ? `https://doi.org/${paper.doi}` : '');

  const getSourcePageUrl = (paper: Paper) =>
    paper.source_url || paper.publisher_url || paper.ieee_url || '';

  const getFinalOpenUrl = (paper: Paper) =>
    paper.pdf_url || getDoiUrl(paper) || paper.source_url || paper.publisher_url || paper.ieee_url || paper.preferred_access_url || '';

  const urlRow = (label: string, value?: string) => (
    <div className="flex items-center gap-1.5 bg-slate-950 border border-slate-750/70 p-3 rounded-xl hover:border-slate-700 transition-colors duration-150">
      <Link2 size={14} className="text-slate-500 shrink-0" />
      <span className="text-xs text-slate-400 shrink-0">{label}:</span>
      {value ? (
        <a href={value} target="_blank" rel="noopener noreferrer" className="text-xs text-brand-400 hover:underline truncate ml-1">
          {value}
        </a>
      ) : (
        <span className="text-xs text-slate-600 ml-1">Unavailable</span>
      )}
    </div>
  );

  useEffect(() => {
    papers.forEach((paper) => {
      console.info('ResearchPilot workspace paper access URLs', {
        paper_id: paper.id,
        title: paper.title,
        source: paper.source || '',
        pdf_url: paper.pdf_url || '',
        doi_url: getDoiUrl(paper),
        source_url: paper.source_url || '',
        publisher_url: paper.publisher_url || '',
        ieee_url: paper.ieee_url || '',
        final_open_url: getFinalOpenUrl(paper),
      });
    });
  }, [papers]);

  const openResolvedPaper = async (paper: Paper) => {
    if (!activeWorkspace) return;
    setOpeningId(paper.id);
    setError('');
    try {
      const response = await api.get<AccessResolution>(
        `/papers/workspace/${activeWorkspace.id}/paper/${paper.id}/access`
      );
      const resolution = response.data;
      if (!resolution.access_url) {
        const message = resolution.message || 'Publisher temporarily unavailable. Please use PDF or DOI access.';
        setError(message);
        showToast('error', message);
        return;
      }

      if (resolution.access_type === 'Local PDF') {
        const localPath = resolution.access_url.replace(/^\/api\/v1/, '');
        const pdfResponse = await api.get(localPath, { responseType: 'blob' });
        const blobUrl = URL.createObjectURL(new Blob([pdfResponse.data], { type: 'application/pdf' }));
        window.open(blobUrl, '_blank', 'noopener,noreferrer');
        setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
      } else {
        const url = resolution.access_url.startsWith('http')
          ? resolution.access_url
          : `${new URL(API_URL).origin}${resolution.access_url}`;
        window.open(url, '_blank', 'noopener,noreferrer');
      }

      if (resolution.fallback_used) {
        showToast('success', `Opened via fallback: ${resolution.access_type}.`);
      }
    } catch (err: any) {
      console.error(err);
      const message = err.response?.data?.detail || 'Publisher temporarily unavailable. Please use PDF or DOI access.';
      setError(message);
      showToast('error', message);
    } finally {
      setOpeningId(null);
    }
  };

  const fetchPapers = async () => {
    if (!activeWorkspace) return;
    setLoading(true);
    setError('');
    try {
      const response = await api.get(`/papers/workspace/${activeWorkspace.id}`);
      setPapers(response.data);
      setSelectedIds((previous) => {
        const available = new Set(response.data.map((paper: Paper) => paper.id));
        return new Set([...previous].filter((id) => available.has(id)));
      });
    } catch (err) {
      console.error(err);
      setError('Failed to load papers. Verify workspace connection.');
      showToast('error', 'Failed to load workspace library.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPapers();
    setSelectedIds(new Set());
  }, [activeWorkspace]);

  const toggleSelected = (paperId: number) => {
    setSelectedIds((previous) => {
      const next = new Set(previous);
      if (next.has(paperId)) {
        next.delete(paperId);
      } else {
        next.add(paperId);
      }
      return next;
    });
  };

  const toggleSelectAll = () => {
    setSelectedIds(allSelected ? new Set() : new Set(papers.map((paper) => paper.id)));
  };

  const compareSelectedPapers = () => {
    const selectedPapers = papers.filter((paper) => selectedIds.has(paper.id));
    if (selectedPapers.length < 2) return;
    const titles = selectedPapers.map((paper) => `"${paper.title}"`).join(', ');
    setAssistantOpen(false);
    navigate('/chat');
    void sendMessage(
      `Compare the selected papers ${titles}. Cover objectives, methodology, results, limitations, and future work using workspace evidence.`,
      { paperIds: selectedPapers.map((paper) => paper.id) },
    );
  };

  const handleDelete = async (paperId: number) => {
    if (!activeWorkspace) return;
    setDeletingId(paperId);
    setError('');
    try {
      await api.delete(`/papers/workspace/${activeWorkspace.id}/paper/${paperId}`);
      setPapers((prev) => prev.filter((paper) => paper.id !== paperId));
      setSelectedIds((previous) => {
        const next = new Set(previous);
        next.delete(paperId);
        return next;
      });
      if (selectedPaper?.id === paperId) {
        setSelectedPaper(null);
      }
      showToast('success', 'Document deleted from workspace.');
    } catch (err) {
      console.error(err);
      setError('Failed to delete paper.');
      showToast('error', 'Failed to delete document.');
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
          : { delete_all: false, paper_ids: [...selectedIds] };
      const response = await api.post(`/papers/workspace/${activeWorkspace.id}/bulk-delete`, payload);
      const idsToDelete = deleteMode === 'all' ? new Set(papers.map((paper) => paper.id)) : selectedIds;
      if (selectedPaper && idsToDelete.has(selectedPaper.id)) {
        setSelectedPaper(null);
      }
      await fetchPapers();
      setSelectedIds(new Set());
      setDeleteMode(null);
      showToast('success', `${response.data.deleted_count || confirmCount} document(s) removed from workspace.`);
    } catch (err: any) {
      console.error(err);
      const message = err.response?.data?.detail || 'Failed to delete workspace documents.';
      setError(message);
      showToast('error', message);
    } finally {
      setBulkDeleting(false);
    }
  };

  if (!activeWorkspace) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center space-y-4">
        <FolderGit size={48} className="text-slate-700" />
        <h2 className="text-xl font-bold text-slate-300">No Active Workspace Selected</h2>
        <p className="text-slate-500 max-w-sm text-sm">
          Please create a new workspace in the header or select an existing one to manage research.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-8 p-1">
      {toast && (
        <div
          className={`fixed top-5 right-5 z-[70] rounded-xl border px-4 py-3 text-sm font-semibold shadow-md ${
            toast.type === 'success'
              ? 'bg-slate-950 text-emerald-400 border-emerald-900/60'
              : 'bg-slate-950 text-red-400 border-red-900/60'
          }`}
        >
          {toast.message}
        </div>
      )}

      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight">Workspace Library</h1>
          <p className="text-slate-400 text-sm">
            Manage your imported preprints and uploaded PDFs inside <strong>{activeWorkspace.name}</strong>.
          </p>
        </div>
        {papers.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-xl border border-slate-750 bg-slate-955 px-3 py-2 text-xs font-semibold text-slate-400">
              {selectedCount} selected
            </span>
            <button
              onClick={compareSelectedPapers}
              disabled={selectedCount < 2 || bulkDeleting}
              className="btn-secondary py-2 px-3 text-xs border-slate-750 hover:border-brand-500 hover:text-brand-400 disabled:opacity-40"
            >
              <GitCompare size={14} />
              <span>Compare Selected Papers</span>
            </button>
            <button
              onClick={() => setDeleteMode('selected')}
              disabled={selectedCount === 0 || bulkDeleting}
              className="btn-danger py-2 px-3 text-xs disabled:opacity-40"
            >
              <Trash2 size={14} />
              <span>Delete Selected</span>
            </button>
            <button
              onClick={() => setDeleteMode('all')}
              disabled={bulkDeleting}
              className="btn-danger py-2 px-3 text-xs"
            >
              <Trash2 size={14} />
              <span>Clear Workspace</span>
            </button>
          </div>
        )}
      </div>

      {error && (
        <div className="bg-red-950 bg-opacity-40 border border-red-900 border-opacity-50 text-red-300 text-sm px-4 py-3 rounded-xl">
          {error}
        </div>
      )}

      {loading ? (
        <div className="py-20 flex justify-center">
          <Loader2 size={32} className="animate-spin text-brand-500" />
        </div>
      ) : papers.length === 0 ? (
        <div className="glass-panel p-12 text-center border border-slate-750 max-w-2xl mx-auto space-y-6">
          <BookOpen size={40} className="text-slate-650 mx-auto" />
          <div className="space-y-1">
            <h3 className="font-bold text-base text-slate-300">Workspace Library Empty</h3>
            <p className="text-slate-500 text-xs max-w-sm mx-auto leading-relaxed">
              To index academic literature in this workspace, search academic sources or upload a PDF.
            </p>
          </div>
          <div className="flex justify-center gap-3">
            <Link to="/search" className="btn-primary py-2 px-4">
              Search papers
            </Link>
            <Link to="/upload" className="btn-secondary py-2 px-4">
              Upload PDF
            </Link>
          </div>
        </div>
      ) : (
        <div className="glass-panel border border-slate-750 overflow-hidden shadow-md">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-750 bg-slate-950 text-slate-400 text-xs font-semibold uppercase tracking-wider">
                  <th className="py-4 px-6 w-12">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      onChange={toggleSelectAll}
                      disabled={bulkDeleting}
                      className="accent-brand-500"
                      aria-label="Select all workspace documents"
                    />
                  </th>
                  <th className="py-4 px-6">Document Title</th>
                  <th className="py-4 px-6">Source / Author</th>
                  <th className="py-4 px-6">Publish Date</th>
                  <th className="py-4 px-6 text-center">Status</th>
                  <th className="py-4 px-6 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800 text-sm">
                {papers.map((paper) => (
                  <tr key={paper.id} className="hover:bg-slate-800/40 transition-colors duration-200">
                    <td className="py-4.5 px-6">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(paper.id)}
                        onChange={() => toggleSelected(paper.id)}
                        disabled={bulkDeleting || deletingId === paper.id}
                        className="accent-brand-500"
                        aria-label={`Select ${paper.title}`}
                      />
                    </td>
                    <td className="py-4.5 px-6 font-semibold text-slate-200 max-w-xs truncate" title={paper.title}>
                      {paper.title}
                    </td>
                    <td className="py-4.5 px-6 text-brand-300 max-w-xs truncate font-medium">
                      {paper.authors}
                    </td>
                    <td className="py-4.5 px-6 text-slate-400 font-medium">
                      {paper.published_date}
                    </td>
                    <td className="py-4.5 px-6 text-center">
                      {paper.indexed_status ? (
                        <span className="inline-flex items-center gap-1.5 bg-emerald-950/30 text-emerald-400 border border-emerald-900 px-2.5 py-0.5 rounded-full text-[11px] font-semibold">
                          {paper.file_path ? 'Vectorized (Full PDF)' : 'Vectorized (Metadata Only)'}
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 bg-amber-950/30 text-amber-400 border border-amber-900 px-2.5 py-0.5 rounded-full text-[11px] font-semibold">
                          <Loader2 size={12} className="animate-spin text-amber-500" />
                          <span>Queue</span>
                        </span>
                      )}
                    </td>
                    <td className="py-4.5 px-6 text-right">
                      <div className="flex justify-end gap-2">
                        <button
                          onClick={() => setSelectedPaper(paper)}
                          disabled={bulkDeleting}
                          className="p-2 bg-slate-800 hover:bg-slate-750 text-slate-300 hover:text-white rounded-xl transition-colors cursor-pointer border border-slate-750 disabled:opacity-50"
                          title="View abstract details"
                        >
                          <Eye size={15} />
                        </button>
                        <button
                          onClick={() => openResolvedPaper(paper)}
                          disabled={openingId === paper.id || bulkDeleting}
                          className="p-2 bg-slate-800 hover:bg-slate-750 text-slate-300 hover:text-white rounded-xl transition-colors cursor-pointer border border-slate-750 disabled:opacity-50"
                          title={`Open paper (${getStoredAccessType(paper)})`}
                        >
                          {openingId === paper.id ? (
                            <Loader2 size={15} className="animate-spin" />
                          ) : (
                            <ExternalLink size={15} />
                          )}
                        </button>
                        <button
                          onClick={() => handleDelete(paper.id)}
                          disabled={deletingId === paper.id || bulkDeleting}
                          className="p-2 bg-red-950 bg-opacity-20 hover:bg-red-900 hover:text-white text-red-400 rounded-xl transition-colors border border-red-900/35 cursor-pointer disabled:opacity-50"
                          title="Delete paper and vectors"
                        >
                          {deletingId === paper.id ? (
                            <Loader2 size={15} className="animate-spin" />
                          ) : (
                            <Trash2 size={15} />
                          )}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {deleteMode && (
        <div className="fixed inset-0 bg-black bg-opacity-70 backdrop-blur-sm flex items-center justify-center z-[60] p-4">
          <div className="glass-panel max-w-md w-full p-6 border border-red-900/50 shadow-2xl animate-fadeIn">
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-xl bg-red-950 text-red-300 border border-red-900/40">
                <AlertTriangle size={20} />
              </div>
              <div>
                <h2 className="text-xl font-bold text-white">
                  {deleteMode === 'all' ? 'Clear Workspace?' : 'Delete Selected Documents?'}
                </h2>
                <p className="text-sm text-slate-400 mt-1">
                  Documents to remove: <span className="font-bold text-white">{confirmCount}</span>
                </p>
              </div>
            </div>
            <div className="rounded-xl border border-red-900/40 bg-red-950/45 p-4 mt-5 text-sm text-red-100 space-y-2">
              <p>This action removes database records, stored PDFs, vector embeddings, and workspace mappings.</p>
              <p>The workspace itself will remain intact.</p>
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
                className="btn-danger py-2 px-5"
              >
                {bulkDeleting && <Loader2 size={14} className="animate-spin" />}
                <span>{deleteMode === 'all' ? 'Clear Workspace' : 'Delete Selected'}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {selectedPaper && (
        <div className="fixed inset-0 bg-black bg-opacity-65 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="glass-panel max-w-2xl w-full p-6 relative shadow-2xl animate-fadeIn max-h-[85vh] flex flex-col">
            <button
              onClick={() => setSelectedPaper(null)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white cursor-pointer"
            >
              <X size={20} />
            </button>
            <div className="overflow-y-auto pr-1 space-y-4">
              <div>
                <span className="text-[10px] font-bold text-brand-400 uppercase tracking-wider">Indexed Document</span>
                <h2 className="text-xl font-bold text-white leading-tight mt-1">{selectedPaper.title}</h2>
                <p className="text-xs text-brand-300 font-semibold mt-1">{selectedPaper.authors}</p>
                <p className="text-xs text-slate-500 mt-0.5">Published on: {selectedPaper.published_date}</p>
                <p className="text-xs text-slate-500 mt-0.5">Access type: {getStoredAccessType(selectedPaper)}</p>
                {selectedPaper.source === 'IEEE' && (
                  <p className="text-xs text-amber-300 mt-2">IEEE access may depend on browser restrictions</p>
                )}
              </div>
              <hr className="border-slate-750" />

              <div className="space-y-1.5">
                <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Abstract / Preview</h4>
                <p className="text-sm text-slate-300 leading-relaxed bg-slate-955 border border-slate-750 p-5 rounded-xl font-normal">
                  {selectedPaper.abstract}
                </p>
              </div>

              <div className="space-y-2">
                {urlRow('PDF URL', selectedPaper.pdf_url)}
                {urlRow('DOI URL', getDoiUrl(selectedPaper))}
                {urlRow('Source URL', getSourcePageUrl(selectedPaper))}
                {urlRow('Final Open URL', getFinalOpenUrl(selectedPaper))}
              </div>

              <div className="flex justify-end gap-3 pt-2">
                {selectedPaper.pdf_url && (
                  <a
                    href={selectedPaper.pdf_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-secondary py-2 px-4"
                  >
                    <ExternalLink size={14} />
                    <span>Open PDF</span>
                  </a>
                )}
                {getSourcePageUrl(selectedPaper) && (
                  <a
                    href={getSourcePageUrl(selectedPaper)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-secondary py-2 px-4"
                  >
                    <ExternalLink size={14} />
                    <span>Open Source Page</span>
                  </a>
                )}
                <button
                  onClick={() => openResolvedPaper(selectedPaper)}
                  disabled={openingId === selectedPaper.id}
                  className="btn-secondary py-2 px-4"
                >
                  {openingId === selectedPaper.id ? <Loader2 size={14} className="animate-spin" /> : <ExternalLink size={14} />}
                  <span>Open Paper</span>
                </button>
                <button
                  onClick={() => setSelectedPaper(null)}
                  className="btn-primary py-2 px-5"
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

export default Workspace;
