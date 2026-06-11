import React, { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import {
  BriefcaseBusiness,
  ChevronDown,
  Copy,
  Download,
  FolderGit,
  Loader2,
  Pencil,
  Plus,
  Search,
  Settings2,
  Trash2,
  X,
} from 'lucide-react';

interface WorkspaceStats {
  paper_count: number;
  report_count: number;
  chat_count?: number;
  uploaded_pdf_count?: number;
  vector_chunk_count?: number;
  last_activity_at?: string | null;
}

interface WorkspaceSummary {
  id: number;
  name: string;
  description?: string;
  created_at: string;
  stats: WorkspaceStats;
}

const formatLastActive = (value?: string | null) => {
  if (!value) return 'No activity';
  const date = new Date(value);
  const now = new Date();
  const diffDays = Math.floor((now.getTime() - date.getTime()) / 86400000);
  if (diffDays <= 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays} days ago`;
  return date.toLocaleDateString();
};

const Header: React.FC = () => {
  const {
    workspaces,
    activeWorkspace,
    selectWorkspace,
    createWorkspace,
    renameWorkspace,
    duplicateWorkspace,
    deleteWorkspace,
    refreshWorkspaces,
  } = useAuth();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showManageModal, setShowManageModal] = useState(false);
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [summaries, setSummaries] = useState<WorkspaceSummary[]>([]);
  const [newWsName, setNewWsName] = useState('');
  const [newWsDesc, setNewWsDesc] = useState('');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<WorkspaceSummary | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const loadSummaries = async () => {
    try {
      const response = await api.get('/workspaces/summary');
      setSummaries(response.data.workspaces);
    } catch (err) {
      console.error('Failed to load workspace summaries:', err);
    }
  };

  useEffect(() => {
    if (workspaces.length > 0) {
      loadSummaries();
    } else {
      setSummaries([]);
    }
  }, [workspaces.length, activeWorkspace?.id]);

  const enrichedWorkspaces = useMemo(() => {
    return workspaces.map((workspace) => {
      const summary = summaries.find((item) => item.id === workspace.id);
      return {
        ...workspace,
        stats: summary?.stats || {
          paper_count: 0,
          report_count: 0,
          chat_count: 0,
          uploaded_pdf_count: 0,
          vector_chunk_count: 0,
          last_activity_at: workspace.created_at,
        },
      };
    });
  }, [workspaces, summaries]);

  const recentWorkspaces = [...enrichedWorkspaces]
    .filter((workspace) => workspace.id !== activeWorkspace?.id)
    .sort((a, b) => {
      const aTime = new Date(a.stats.last_activity_at || a.created_at).getTime();
      const bTime = new Date(b.stats.last_activity_at || b.created_at).getTime();
      return bTime - aTime;
    })
    .slice(0, 3);

  const recentIds = new Set(recentWorkspaces.map((workspace) => workspace.id));
  const listedWorkspaces = enrichedWorkspaces.filter((workspace) => {
    const text = `${workspace.name} ${workspace.description || ''}`.toLowerCase();
    const matches = text.includes(query.toLowerCase());
    if (!matches) return false;
    if (!query && (workspace.id === activeWorkspace?.id || recentIds.has(workspace.id))) return false;
    return true;
  });

  const activeSummary = enrichedWorkspaces.find((workspace) => workspace.id === activeWorkspace?.id);

  const resetForm = () => {
    setNewWsName('');
    setNewWsDesc('');
    setEditingId(null);
    setError('');
  };

  const syncWorkspaces = async () => {
    await refreshWorkspaces();
    await loadSummaries();
  };

  const handleCreateWorkspace = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newWsName.trim()) {
      setError('Workspace name is required');
      return;
    }

    setLoading(true);
    setError('');
    try {
      await createWorkspace(newWsName.trim(), newWsDesc.trim());
      await syncWorkspaces();
      resetForm();
      setShowCreateModal(false);
      setSwitcherOpen(false);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create workspace');
    } finally {
      setLoading(false);
    }
  };

  const handleRenameWorkspace = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingId || !newWsName.trim()) return;
    setLoading(true);
    setError('');
    try {
      await renameWorkspace(editingId, newWsName.trim(), newWsDesc.trim());
      await syncWorkspaces();
      resetForm();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to rename workspace');
    } finally {
      setLoading(false);
    }
  };

  const handleDuplicateWorkspace = async (workspaceId: number) => {
    setLoading(true);
    setError('');
    try {
      await duplicateWorkspace(workspaceId);
      await syncWorkspaces();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to duplicate workspace');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteWorkspace = async () => {
    if (!deleteTarget) return;
    setLoading(true);
    setError('');
    try {
      await deleteWorkspace(deleteTarget.id);
      await syncWorkspaces();
      setDeleteTarget(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete workspace');
    } finally {
      setLoading(false);
    }
  };

  const startRename = (workspace: WorkspaceSummary) => {
    setEditingId(workspace.id);
    setNewWsName(workspace.name);
    setNewWsDesc(workspace.description || '');
    setError('');
  };

  const exportWorkspace = (workspace: WorkspaceSummary) => {
    const payload = {
      exported_at: new Date().toISOString(),
      workspace,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${workspace.name.toLowerCase().replace(/[^a-z0-9]+/g, '-') || 'workspace'}-export.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const workspaceRow = (workspace: WorkspaceSummary, prefix = 'workspace') => (
    <button
      key={`${prefix}-${workspace.id}`}
      onClick={() => {
        selectWorkspace(workspace);
        setSwitcherOpen(false);
      }}
      className="w-full flex items-center justify-between gap-3 rounded-xl border border-transparent px-3 py-2.5 text-left transition-all duration-200 hover:border-slate-750 hover:bg-slate-800/80 cursor-pointer"
    >
      <div className="min-w-0">
        <p className="text-sm font-bold text-slate-100 truncate">{workspace.name}</p>
        <p className="text-xs text-slate-500 truncate">{workspace.stats.paper_count} papers / {workspace.stats.report_count} reports</p>
      </div>
      <span className="text-[11px] text-slate-500 shrink-0">{formatLastActive(workspace.stats.last_activity_at)}</span>
    </button>
  );

  return (
    <header className="h-20 bg-slate-850 border-b border-slate-750 px-8 flex items-center justify-between z-30 shrink-0 relative shadow-md">
      <div className="relative">
        <button
          onClick={() => setSwitcherOpen((value) => !value)}
          className="flex items-center gap-3 rounded-xl border border-slate-750 bg-slate-900 bg-opacity-45 px-4 py-3 text-left transition-all duration-200 hover:border-slate-700 hover:bg-slate-800/50 cursor-pointer min-w-[320px]"
        >
          <div className="p-2 rounded-lg bg-brand-500 bg-opacity-10 text-brand-400">
            <FolderGit size={18} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Current Workspace</p>
            <p className="text-sm font-bold text-slate-100 truncate">
              {activeWorkspace?.name || 'No workspaces yet'}
            </p>
            {activeSummary && (
              <p className="text-[11px] text-slate-500">
                {activeSummary.stats.paper_count} papers / {activeSummary.stats.report_count} reports / {formatLastActive(activeSummary.stats.last_activity_at)}
              </p>
            )}
          </div>
          <ChevronDown size={16} className={`text-slate-500 transition-transform duration-200 ${switcherOpen ? 'rotate-180' : ''}`} />
        </button>
 
        {switcherOpen && (
          <div className="absolute top-[calc(100%+10px)] left-0 w-[420px] glass-panel border border-slate-750 p-3 z-50 shadow-2xl animate-fadeIn">
            <div className="flex items-center gap-2 rounded-xl border border-slate-750 bg-slate-950 px-3 py-2 mb-3">
              <Search size={15} className="text-slate-500" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search workspaces"
                className="w-full bg-transparent text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none"
              />
            </div>
 
            {!query && recentWorkspaces.length > 0 && (
              <div className="mb-3">
                <p className="px-2 pb-1 text-[10px] uppercase tracking-wider text-slate-500 font-bold">Recent Workspaces</p>
                <div className="space-y-1">{recentWorkspaces.map((workspace) => workspaceRow(workspace, 'recent'))}</div>
              </div>
            )}
 
            <div>
              <p className="px-2 pb-1 text-[10px] uppercase tracking-wider text-slate-500 font-bold">
                {query ? 'Search Results' : 'All Workspaces'}
              </p>
              <div className="max-h-60 overflow-y-auto space-y-1">
                {listedWorkspaces.length === 0 ? (
                  <div className="py-6 text-center text-sm text-slate-500">
                    {query ? 'No matching workspaces' : 'No additional workspaces'}
                  </div>
                ) : (
                  listedWorkspaces.map((workspace) => workspaceRow(workspace))
                )}
              </div>
            </div>
 
            <div className="mt-3 grid grid-cols-2 gap-2 border-t border-slate-750 pt-3">
              <button
                onClick={() => setShowCreateModal(true)}
                className="btn-primary py-2 px-3 text-xs"
              >
                <Plus size={15} />
                <span>Create</span>
              </button>
              <button
                onClick={() => {
                  setShowManageModal(true);
                  setSwitcherOpen(false);
                }}
                className="btn-secondary py-2 px-3 text-xs"
              >
                <Settings2 size={15} />
                <span>Manage</span>
              </button>
            </div>
          </div>
        )}
      </div>
 
      <div className="flex items-center gap-3">
        <div className="hidden md:flex items-center gap-2 px-3 py-2 rounded-xl border border-slate-750 bg-slate-900 bg-opacity-40 text-xs font-semibold text-slate-400">
          <BriefcaseBusiness size={15} className="text-emerald-400" />
          <span>{workspaces.length} research workspaces</span>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="btn-primary py-2 px-4"
        >
          <Plus size={16} />
          <span>New Workspace</span>
        </button>
      </div>

      {showCreateModal && (
        <div className="fixed inset-0 bg-black bg-opacity-60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="glass-panel max-w-md w-full p-6 relative animate-fadeIn border border-slate-700">
            <button onClick={() => setShowCreateModal(false)} className="absolute top-4 right-4 text-slate-400 hover:text-white cursor-pointer">
              <X size={20} />
            </button>
            <h2 className="text-xl font-bold mb-4 text-white">Create Research Workspace</h2>
            {error && <div className="bg-red-950 bg-opacity-40 border border-red-900 border-opacity-50 text-red-300 text-sm px-4 py-2.5 rounded-xl mb-4">{error}</div>}
            <form onSubmit={handleCreateWorkspace} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wider">Workspace Name</label>
                <input type="text" value={newWsName} onChange={(e) => setNewWsName(e.target.value)} placeholder="e.g. Agentic AI Research" className="w-full glass-input" required />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wider">Description</label>
                <textarea value={newWsDesc} onChange={(e) => setNewWsDesc(e.target.value)} placeholder="Scope, questions, datasets, or methods for this research track." className="w-full glass-input h-24 resize-none" />
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button type="button" onClick={() => setShowCreateModal(false)} className="px-4 py-2 text-sm font-semibold text-slate-400 hover:text-white cursor-pointer">Cancel</button>
                <button type="submit" disabled={loading} className="bg-brand-600 hover:bg-brand-500 text-white font-semibold py-2 px-5 rounded-xl text-sm transition-all duration-250 cursor-pointer disabled:opacity-50">
                  {loading ? 'Creating...' : 'Create Workspace'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showManageModal && (
        <div className="fixed inset-0 bg-black bg-opacity-65 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="glass-panel max-w-4xl w-full border border-slate-700 animate-fadeIn max-h-[86vh] overflow-hidden">
            <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
              <div>
                <h2 className="text-lg font-bold text-white">Manage Workspaces</h2>
                <p className="text-xs text-slate-500">Rename, duplicate, delete, or export workspace metadata.</p>
              </div>
              <button onClick={() => { setShowManageModal(false); resetForm(); }} className="text-slate-400 hover:text-white cursor-pointer">
                <X size={20} />
              </button>
            </div>
            <div className="p-5 overflow-y-auto max-h-[70vh] space-y-3">
              {error && <div className="bg-red-950 bg-opacity-40 border border-red-900 border-opacity-50 text-red-300 text-sm px-4 py-2.5 rounded-xl">{error}</div>}
              {enrichedWorkspaces.map((workspace) => (
                <div key={workspace.id} className="rounded-xl border border-slate-800 bg-slate-900 bg-opacity-35 p-4">
                  {editingId === workspace.id ? (
                    <form onSubmit={handleRenameWorkspace} className="grid grid-cols-1 md:grid-cols-[1fr_1fr_auto] gap-3 items-end">
                      <div>
                        <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">Name</label>
                        <input value={newWsName} onChange={(event) => setNewWsName(event.target.value)} className="w-full glass-input" required />
                      </div>
                      <div>
                        <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">Description</label>
                        <input value={newWsDesc} onChange={(event) => setNewWsDesc(event.target.value)} className="w-full glass-input" />
                      </div>
                      <div className="flex gap-2">
                        <button disabled={loading} type="submit" className="rounded-xl bg-brand-600 hover:bg-brand-500 px-4 py-2 text-sm font-bold text-white disabled:opacity-50 cursor-pointer">Save</button>
                        <button type="button" onClick={resetForm} className="rounded-xl border border-slate-700 px-4 py-2 text-sm font-bold text-slate-300 hover:text-white cursor-pointer">Cancel</button>
                      </div>
                    </form>
                  ) : (
                    <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                      <div className="min-w-0">
                        <p className="text-sm font-bold text-white truncate">{workspace.name}</p>
                        <p className="text-xs text-slate-500 truncate">{workspace.description || 'No description'}</p>
                        <p className="text-[11px] text-slate-600 mt-1">
                          {workspace.stats.paper_count} papers / {workspace.stats.report_count} reports / {workspace.stats.chat_count || 0} chats
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <button onClick={() => startRename(workspace)} className="flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-bold text-slate-200 hover:bg-slate-750 cursor-pointer"><Pencil size={13} />Rename</button>
                        <button disabled={loading} onClick={() => handleDuplicateWorkspace(workspace.id)} className="flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-bold text-slate-200 hover:bg-slate-750 disabled:opacity-50 cursor-pointer"><Copy size={13} />Duplicate</button>
                        <button onClick={() => exportWorkspace(workspace)} className="flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-bold text-slate-200 hover:bg-slate-750 cursor-pointer"><Download size={13} />Export</button>
                        <button onClick={() => setDeleteTarget(workspace)} className="flex items-center gap-1.5 rounded-xl border border-red-900 border-opacity-45 bg-red-950 bg-opacity-20 px-3 py-2 text-xs font-bold text-red-300 hover:bg-red-900 hover:text-white cursor-pointer"><Trash2 size={13} />Delete</button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {deleteTarget && (
        <div className="fixed inset-0 bg-black bg-opacity-70 backdrop-blur-sm flex items-center justify-center z-[60] p-4">
          <div className="glass-panel max-w-md w-full p-6 border border-red-900 border-opacity-50 animate-fadeIn">
            <h2 className="text-xl font-bold text-white mb-2">Delete Workspace?</h2>
            <p className="text-sm text-slate-400 mb-4">Workspace: <span className="font-bold text-white">"{deleteTarget.name}"</span></p>
            <div className="rounded-xl border border-red-900 border-opacity-35 bg-red-950 bg-opacity-20 p-4 text-sm text-red-100 space-y-1">
              <p>{deleteTarget.stats.paper_count} papers</p>
              <p>{deleteTarget.stats.report_count} reports</p>
              <p>all vector embeddings</p>
              <p>all chat history</p>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => setDeleteTarget(null)} className="px-4 py-2 text-sm font-semibold text-slate-400 hover:text-white cursor-pointer">Cancel</button>
              <button disabled={loading} onClick={handleDeleteWorkspace} className="inline-flex items-center gap-2 rounded-xl bg-red-700 hover:bg-red-600 px-5 py-2 text-sm font-bold text-white disabled:opacity-50 cursor-pointer">
                {loading && <Loader2 size={14} className="animate-spin" />}
                <span>Delete Workspace</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </header>
  );
};

export default Header;
