import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import {
  Activity,
  BarChart3,
  Bot,
  CheckCircle2,
  Copy,
  FileArchive,
  FileText,
  FolderGit,
  Loader2,
  Pencil,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';

interface WorkspaceStats {
  paper_count: number;
  uploaded_pdf_count: number;
  report_count: number;
  chat_count: number;
  vectorized_document_count: number;
  vector_chunk_count: number;
  last_activity_at?: string | null;
}

interface WorkspaceSummary {
  id: number;
  name: string;
  description?: string;
  user_id: number;
  created_at: string;
  stats: WorkspaceStats;
}

interface Analytics {
  total_workspaces: number;
  total_papers: number;
  total_uploaded_pdfs: number;
  total_ai_reports: number;
  total_research_chats: number;
  total_vectorized_documents: number;
  total_vector_chunks: number;
}

interface ActivityEvent {
  id: string;
  workspace_id: number;
  workspace_name: string;
  type: string;
  title: string;
  detail: string;
  timestamp: string;
}

const emptyAnalytics: Analytics = {
  total_workspaces: 0,
  total_papers: 0,
  total_uploaded_pdfs: 0,
  total_ai_reports: 0,
  total_research_chats: 0,
  total_vectorized_documents: 0,
  total_vector_chunks: 0,
};

const formatDate = (value?: string | null) => {
  if (!value) return 'No activity yet';
  return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
};

const formatLastActive = (value?: string | null) => {
  if (!value) return 'No activity';
  const date = new Date(value);
  const now = new Date();
  const diffDays = Math.floor((now.getTime() - date.getTime()) / 86400000);
  if (diffDays <= 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays} days ago`;
  return formatDate(value);
};

const Dashboard: React.FC = () => {
  const {
    workspaces,
    activeWorkspace,
    selectWorkspace,
    createWorkspace,
    deleteWorkspace,
    renameWorkspace,
    duplicateWorkspace,
    refreshWorkspaces,
  } = useAuth();
  const navigate = useNavigate();
  const [analytics, setAnalytics] = useState<Analytics>(emptyAnalytics);
  const [workspaceSummaries, setWorkspaceSummaries] = useState<WorkspaceSummary[]>([]);
  const [activities, setActivities] = useState<ActivityEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState('');
  const [renameTarget, setRenameTarget] = useState<WorkspaceSummary | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<WorkspaceSummary | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [workspaceName, setWorkspaceName] = useState('');
  const [workspaceDescription, setWorkspaceDescription] = useState('');
  const [searchTerm, setSearchTerm] = useState('');

  const activeSummary = useMemo(
    () => workspaceSummaries.find((workspace) => workspace.id === activeWorkspace?.id) || null,
    [activeWorkspace?.id, workspaceSummaries]
  );

  const visibleWorkspaces = workspaceSummaries.filter((workspace) => {
    const text = `${workspace.name} ${workspace.description || ''}`.toLowerCase();
    return text.includes(searchTerm.toLowerCase());
  });

  const activeWorkspaceEmpty = Boolean(
    activeSummary && activeSummary.stats.paper_count === 0 && activeSummary.stats.report_count === 0
  );

  const loadDashboard = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await api.get('/workspaces/summary');
      setAnalytics(response.data.analytics);
      setWorkspaceSummaries(response.data.workspaces);
      setActivities(response.data.recent_activity);
    } catch (err) {
      console.error('Error loading workspace dashboard:', err);
      setError('Failed to load workspace dashboard.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboard();
  }, [workspaces.length, activeWorkspace?.id]);

  const syncAfterAction = async () => {
    await refreshWorkspaces();
    await loadDashboard();
  };

  const openWorkspace = (workspace: WorkspaceSummary) => {
    selectWorkspace(workspace);
    navigate('/workspace');
  };

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!workspaceName.trim()) return;
    setActionLoading(true);
    setError('');
    try {
      await createWorkspace(workspaceName.trim(), workspaceDescription.trim());
      setWorkspaceName('');
      setWorkspaceDescription('');
      setShowCreateModal(false);
      await syncAfterAction();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create workspace.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleRename = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!renameTarget || !workspaceName.trim()) return;
    setActionLoading(true);
    setError('');
    try {
      await renameWorkspace(renameTarget.id, workspaceName.trim(), workspaceDescription.trim());
      setRenameTarget(null);
      setWorkspaceName('');
      setWorkspaceDescription('');
      await syncAfterAction();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to rename workspace.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleDuplicate = async (workspace: WorkspaceSummary) => {
    setActionLoading(true);
    setError('');
    try {
      await duplicateWorkspace(workspace.id);
      await syncAfterAction();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to duplicate workspace.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setActionLoading(true);
    setError('');
    try {
      await deleteWorkspace(deleteTarget.id);
      setDeleteTarget(null);
      await syncAfterAction();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete workspace.');
    } finally {
      setActionLoading(false);
    }
  };

  const startRename = (workspace: WorkspaceSummary) => {
    setWorkspaceName(workspace.name);
    setWorkspaceDescription(workspace.description || '');
    setRenameTarget(workspace);
  };

  const startCreate = () => {
    setWorkspaceName('');
    setWorkspaceDescription('');
    setShowCreateModal(true);
  };

  const metricCards = [
    { title: 'Total Workspaces', value: analytics.total_workspaces, icon: FolderGit, tone: 'text-brand-300 bg-brand-600' },
    { title: 'Total Papers', value: analytics.total_papers, icon: FileText, tone: 'text-emerald-300 bg-emerald-600' },
    { title: 'Uploaded PDFs', value: analytics.total_uploaded_pdfs, icon: FileArchive, tone: 'text-cyan-300 bg-cyan-600' },
    { title: 'AI Reports', value: analytics.total_ai_reports, icon: Sparkles, tone: 'text-violet-300 bg-violet-600' },
  ];

  const assets = [
    { label: 'Imported Papers', value: activeSummary?.stats.paper_count || 0 },
    { label: 'Uploaded PDFs', value: activeSummary?.stats.uploaded_pdf_count || 0 },
    { label: 'Generated Reports', value: activeSummary?.stats.report_count || 0 },
    { label: 'Vector Chunks', value: activeSummary?.stats.vector_chunk_count || 0 },
  ];

  const healthItems = [
    'Vector Database Ready',
    'Papers Indexed',
    'AI Agent Online',
    'RAG Enabled',
    'Embeddings Available',
  ];

  return (
    <div className="space-y-5 p-1">
      <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Workspace Management Center</h1>
          <p className="text-slate-400 text-sm">
            Manage research workspaces, assets, activity, and readiness from one dashboard.
          </p>
        </div>
        <button
          onClick={startCreate}
          className="btn-primary py-2 px-4"
        >
          <Plus size={17} />
          <span>Create Workspace</span>
        </button>
      </div>

      {error && (
        <div className="bg-red-950 bg-opacity-40 border border-red-900 border-opacity-50 text-red-300 text-sm px-4 py-3 rounded-xl">
          {error}
        </div>
      )}

      {loading ? (
        <div className="py-24 flex justify-center">
          <Loader2 size={34} className="animate-spin text-brand-500" />
        </div>
      ) : workspaceSummaries.length === 0 ? (
        <div className="glass-panel border border-slate-750 p-12 text-center max-w-2xl mx-auto space-y-5">
          <FolderGit size={46} className="mx-auto text-slate-600" />
          <div>
            <h2 className="text-xl font-bold text-white">Create your first research workspace</h2>
            <p className="text-sm text-slate-500 mt-1">
              Start a dedicated space for papers, PDFs, reports, vectors, and research chat.
            </p>
          </div>
          <button
            onClick={startCreate}
            className="btn-primary py-2.5 px-5 mx-auto"
          >
            <Plus size={16} />
            <span>Create Workspace</span>
          </button>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
            {metricCards.map((metric) => (
              <div key={metric.title} className="glass-panel glass-panel-hover px-4 py-3 flex items-center gap-3 min-h-[74px]">
                <div className={`w-9 h-9 rounded-lg ${metric.tone} bg-opacity-15 flex items-center justify-center shrink-0`}>
                  <metric.icon size={19} className={metric.tone.split(' ')[0]} />
                </div>
                <div className="min-w-0">
                  <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500 truncate">{metric.title}</p>
                  <p className="text-xl font-extrabold text-white leading-tight">{metric.value}</p>
                </div>
              </div>
            ))}
          </div>

          {activeWorkspaceEmpty && (
            <div className="glass-panel border border-slate-750 px-5 py-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <h2 className="text-lg font-bold text-white">Your workspace is empty</h2>
                <p className="text-sm text-slate-500">
                  Add papers or PDFs to turn {activeSummary?.name} into an active research space.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Link to="/search" className="btn-primary py-2 px-4 text-xs">
                  Search Papers
                </Link>
                <Link to="/upload" className="btn-secondary py-2 px-4 text-xs">
                  Upload PDF
                </Link>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 xl:grid-cols-4 gap-5">
            <div className={`${activeWorkspaceEmpty ? 'xl:col-span-4' : 'xl:col-span-3'} space-y-5`}>
              <div className="space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <h2 className="text-lg font-bold text-white flex items-center gap-2">
                    <BarChart3 size={19} className="text-brand-400" />
                    <span>Workspace Management</span>
                  </h2>
                  <div className="flex items-center gap-2 rounded-xl border border-slate-750 bg-slate-950 px-3 py-2">
                    <Search size={15} className="text-slate-500" />
                    <input
                      value={searchTerm}
                      onChange={(event) => setSearchTerm(event.target.value)}
                      placeholder="Search workspaces"
                      className="bg-transparent text-sm text-slate-200 placeholder:text-slate-650 focus:outline-none"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {visibleWorkspaces.map((workspace) => (
                    <div
                      key={workspace.id}
                      className={`glass-panel p-5 ${
                        activeWorkspace?.id === workspace.id ? 'border-brand-500/80 shadow-glow' : 'border-slate-750 hover:border-slate-700'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <p className="text-xs font-bold text-brand-400 uppercase tracking-wider">Workspace Name</p>
                          <h3 className="text-xl font-extrabold text-white truncate mt-1">{workspace.name}</h3>
                          <p className="text-sm text-slate-500 mt-1 line-clamp-2 min-h-[40px]">
                            {workspace.description || 'No description added yet.'}
                          </p>
                        </div>
                        <div className="rounded-xl bg-slate-950 border border-slate-750 px-3 py-2 text-right shrink-0">
                          <p className="text-[10px] uppercase text-slate-500 font-bold">Last Active</p>
                          <p className="text-xs font-semibold text-slate-300">{formatLastActive(workspace.stats.last_activity_at)}</p>
                        </div>
                      </div>

                      <div className="grid grid-cols-3 gap-2 my-4">
                        <div className="rounded-xl border border-slate-750 bg-slate-950 p-2.5">
                          <p className="text-xl font-black text-white">{workspace.stats.paper_count}</p>
                          <p className="text-xs text-slate-500 font-semibold">Papers</p>
                        </div>
                        <div className="rounded-xl border border-slate-750 bg-slate-950 p-2.5">
                          <p className="text-xl font-black text-white">{workspace.stats.report_count}</p>
                          <p className="text-xs text-slate-500 font-semibold">Reports</p>
                        </div>
                        <div className="rounded-xl border border-slate-750 bg-slate-950 p-2.5">
                          <p className="text-xl font-black text-white">{workspace.stats.chat_count}</p>
                          <p className="text-xs text-slate-500 font-semibold">Chats</p>
                        </div>
                      </div>

                      <div className="flex items-center justify-between text-xs text-slate-500 mb-4">
                        <span>Created: {formatDate(workspace.created_at)}</span>
                        <span>{workspace.stats.vector_chunk_count} vector chunks</span>
                      </div>

                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                        <button onClick={() => openWorkspace(workspace)} className="btn-primary py-1.5 text-xs">
                          Open
                        </button>
                        <button onClick={() => startRename(workspace)} className="btn-secondary py-1.5 text-xs">
                          <Pencil size={13} />
                          <span>Rename</span>
                        </button>
                        <button disabled={actionLoading} onClick={() => handleDuplicate(workspace)} className="btn-secondary py-1.5 text-xs">
                          <Copy size={13} />
                          <span>Duplicate</span>
                        </button>
                        <button onClick={() => setDeleteTarget(workspace)} className="btn-danger py-1.5 text-xs">
                          <Trash2 size={13} />
                          <span>Delete</span>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {!activeWorkspaceEmpty && (
              <div className="glass-panel border border-slate-750 p-5">
                <h2 className="text-lg font-bold text-white flex items-center gap-2 mb-5">
                  <Activity size={19} className="text-brand-400" />
                  <span>Recent Activity</span>
                </h2>
                <div className="space-y-3">
                  {activities.length === 0 ? (
                    <div className="py-8 text-center text-sm text-slate-500">No activity logged yet.</div>
                  ) : (
                    activities.map((event) => (
                      <div key={event.id} className="flex items-start gap-3 rounded-xl border border-slate-750 bg-slate-950/45 p-3 hover:border-slate-700 transition-colors duration-150">
                        <div className="mt-0.5 h-8 w-8 rounded-full bg-brand-500 bg-opacity-10 text-brand-400 flex items-center justify-center shrink-0 border border-brand-500/15">
                          <Activity size={15} />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1">
                            <p className="text-sm font-bold text-slate-200">{event.type}</p>
                            <p className="text-xs text-slate-500">{formatLastActive(event.timestamp)}</p>
                          </div>
                          <p className="text-sm text-slate-400 truncate">{event.title}</p>
                          <p className="text-xs text-slate-500 truncate">{event.workspace_name} · {event.detail}</p>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
              )}
            </div>

            {!activeWorkspaceEmpty && (
            <div className="space-y-5">
              <div className="glass-panel border border-slate-750 p-5">
                <h2 className="text-base font-bold text-white mb-4">Research Assets</h2>
                <div className="space-y-3">
                  {assets.map((asset) => (
                    <div key={asset.label} className="flex items-center justify-between rounded-xl bg-slate-950 border border-slate-750 px-3.5 py-2.5 hover:border-slate-700 transition-colors duration-150">
                      <span className="text-sm text-slate-400">{asset.label}</span>
                      <span className="text-sm font-black text-white">{asset.value}</span>
                    </div>
                  ))}
                </div>
                {activeSummary && (
                  <Link to="/doc-space" className="mt-4 inline-flex text-xs font-bold text-brand-300 hover:text-brand-200">
                    View generated reports
                  </Link>
                )}
              </div>

              <div className="glass-panel border border-slate-750 p-5">
                <h2 className="text-base font-bold text-white flex items-center gap-2 mb-4">
                  <ShieldCheck size={18} className="text-emerald-400" />
                  <span>Workspace Health</span>
                </h2>
                <div className="space-y-3">
                  {healthItems.map((item) => (
                    <div key={item} className="flex items-center gap-2 text-sm text-slate-300">
                      <CheckCircle2 size={16} className="text-emerald-400 shrink-0" />
                      <span>{item}</span>
                    </div>
                  ))}
                </div>
                <div className="mt-5 rounded-xl border border-emerald-900/40 bg-emerald-950/45 p-3">
                  <p className="text-[10px] uppercase tracking-wider font-bold text-emerald-300">Last Sync Timestamp</p>
                  <p className="text-xs text-slate-400 mt-1">{activeSummary ? formatDate(activeSummary.stats.last_activity_at) : 'No active workspace'}</p>
                </div>
                <div className="mt-4 flex items-center gap-2 text-xs text-slate-500">
                  <Bot size={14} className="text-brand-400" />
                  <span>Agent status is scoped to the active workspace.</span>
                </div>
              </div>
            </div>
            )}
          </div>
        </>
      )}

      {(showCreateModal || renameTarget) && (
        <div className="fixed inset-0 bg-black bg-opacity-65 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="glass-panel max-w-md w-full p-6 relative shadow-2xl animate-fadeIn">
            <button
              onClick={() => {
                setShowCreateModal(false);
                setRenameTarget(null);
              }}
              className="absolute top-4 right-4 text-slate-400 hover:text-white cursor-pointer"
            >
              <X size={20} />
            </button>
            <h2 className="text-xl font-bold text-white mb-4">{renameTarget ? 'Rename Workspace' : 'Create Research Workspace'}</h2>
            <form onSubmit={renameTarget ? handleRename : handleCreate} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wider">Workspace Name</label>
                <input value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} className="w-full glass-input" required />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wider">Description</label>
                <textarea value={workspaceDescription} onChange={(event) => setWorkspaceDescription(event.target.value)} className="w-full glass-input h-24 resize-none" />
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button type="button" onClick={() => { setShowCreateModal(false); setRenameTarget(null); }} className="px-4 py-2 text-sm font-semibold text-slate-400 hover:text-white cursor-pointer">
                  Cancel
                </button>
                <button disabled={actionLoading} type="submit" className="btn-primary px-5 py-2 font-bold disabled:opacity-50">
                  {actionLoading ? 'Saving...' : renameTarget ? 'Save Changes' : 'Create Workspace'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {deleteTarget && (
        <div className="fixed inset-0 bg-black bg-opacity-70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="glass-panel max-w-lg w-full p-6 border border-red-900/50 shadow-2xl animate-fadeIn">
            <h2 className="text-xl font-bold text-white mb-2">Delete Workspace?</h2>
            <p className="text-sm text-slate-400 mb-5">
              Workspace: <span className="font-bold text-white">"{deleteTarget.name}"</span>
            </p>
            <div className="rounded-xl border border-red-900 border-opacity-35 bg-red-950 bg-opacity-20 p-4 space-y-2 text-sm text-red-100">
              <p className="font-bold text-red-200">This action will permanently remove:</p>
              <p>{deleteTarget.stats.paper_count} papers</p>
              <p>{deleteTarget.stats.report_count} reports</p>
              <p>all vector embeddings</p>
              <p>all chat history</p>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => setDeleteTarget(null)} className="px-4 py-2 text-sm font-semibold text-slate-400 hover:text-white cursor-pointer">
                Cancel
              </button>
              <button disabled={actionLoading} onClick={handleDelete} className="btn-danger px-5 py-2 font-bold">
                {actionLoading ? 'Deleting...' : 'Delete Workspace'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
