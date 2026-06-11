import React, { useEffect, useState, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { useSharedChat, type ChatSessionBrief } from '../context/ChatContext';
import api from '../services/api';
import { 
  MessageSquare, 
  Send, 
  Trash2, 
  Loader2, 
  BookOpen, 
  AlertTriangle, 
  Plus, 
  Search, 
  Pin, 
  PinOff, 
  Edit3, 
  X, 
  Menu
} from 'lucide-react';

interface Paper {
  id: number;
  title: string;
}

interface GroupedSessions {
  pinned: ChatSessionBrief[];
  today: ChatSessionBrief[];
  yesterday: ChatSessionBrief[];
  last7days: ChatSessionBrief[];
  older: ChatSessionBrief[];
}

const ResearchChat: React.FC = () => {
  const { activeWorkspace } = useAuth();
  const {
    sessionId,
    messages,
    historyLoading,
    sending,
    error,
    sendMessage,
    sessions,
    sessionsLoading,
    selectSession,
    startNewChat,
    deleteSession,
    renameSession,
    togglePinSession,
  } = useSharedChat();

  const [papers, setPapers] = useState<Paper[]>([]);
  const [input, setInput] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  
  // Sidebar states
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameTitle, setRenameTitle] = useState('');
  
  const chatBottomRef = useRef<HTMLDivElement>(null);
  const renameInputRef = useRef<HTMLInputElement>(null);

  const fetchWorkspaceInfo = async () => {
    if (!activeWorkspace) return;
    try {
      const papersResponse = await api.get(`/papers/workspace/${activeWorkspace.id}`);
      setPapers(papersResponse.data.filter((p: any) => p.indexed_status));
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchWorkspaceInfo();
  }, [activeWorkspace]);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (renamingId !== null && renameInputRef.current) {
      renameInputRef.current.focus();
      renameInputRef.current.select();
    }
  }, [renamingId]);

  const scrollToBottom = () => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || !activeWorkspace || sending) return;

    const userQuery = input.trim();
    setInput('');
    await sendMessage(userQuery);
  };

  // Group chat sessions by dates
  const groupSessions = (sessionsList: ChatSessionBrief[]): GroupedSessions => {
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const yesterdayStart = todayStart - 24 * 60 * 60 * 1000;
    const sevenDaysAgoStart = todayStart - 7 * 24 * 60 * 60 * 1000;

    const groups: GroupedSessions = {
      pinned: [],
      today: [],
      yesterday: [],
      last7days: [],
      older: [],
    };

    sessionsList.forEach((s) => {
      if (s.is_pinned) {
        groups.pinned.push(s);
      } else {
        const updateTime = new Date(s.updated_at).getTime();
        if (updateTime >= todayStart) {
          groups.today.push(s);
        } else if (updateTime >= yesterdayStart) {
          groups.yesterday.push(s);
        } else if (updateTime >= sevenDaysAgoStart) {
          groups.last7days.push(s);
        } else {
          groups.older.push(s);
        }
      }
    });

    return groups;
  };

  const filteredSessions = sessions.filter((s) =>
    (s.title || '').toLowerCase().includes(searchQuery.toLowerCase())
  );

  const grouped = groupSessions(filteredSessions);

  const handleStartRename = (session: ChatSessionBrief, e: React.MouseEvent) => {
    e.stopPropagation();
    setRenamingId(session.id);
    setRenameTitle(session.title || 'Untitled Chat');
  };

  const handleSaveRename = async (id: number) => {
    if (renameTitle.trim()) {
      await renameSession(id, renameTitle.trim());
    }
    setRenamingId(null);
  };

  const handleRenameKeyDown = (e: React.KeyboardEvent, id: number) => {
    if (e.key === 'Enter') {
      handleSaveRename(id);
    } else if (e.key === 'Escape') {
      setRenamingId(null);
    }
  };

  const handleDeleteClick = (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setDeletingId(id);
  };

  const handlePinClick = async (session: ChatSessionBrief, e: React.MouseEvent) => {
    e.stopPropagation();
    await togglePinSession(session.id, !session.is_pinned);
  };

  if (!activeWorkspace) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center space-y-4">
        <MessageSquare size={48} className="text-slate-700" />
        <h2 className="text-xl font-bold text-slate-300">No Active Workspace Selected</h2>
        <p className="text-slate-500 max-w-sm text-sm">
          Please select or create an active workspace first to start a chat session.
        </p>
      </div>
    );
  }

  const renderSessionItem = (s: ChatSessionBrief) => {
    const isActive = sessionId === s.id;
    const isEditing = renamingId === s.id;

    return (
      <div
        key={s.id}
        onClick={() => !isEditing && selectSession(s.id)}
        className={`group relative flex items-center gap-2 p-2.5 rounded-xl border text-xs cursor-pointer transition-all duration-200 ${
          isActive
            ? 'bg-slate-800 border-slate-750 text-slate-100 font-semibold shadow-sm'
            : 'bg-slate-950/20 border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 hover:border-slate-700'
        }`}
      >
        <MessageSquare size={13} className={`shrink-0 transition-colors duration-200 ${isActive ? 'text-brand-400' : 'text-slate-500 group-hover:text-slate-350'}`} />
        
        {isEditing ? (
          <input
            ref={renameInputRef}
            type="text"
            value={renameTitle}
            onChange={(e) => setRenameTitle(e.target.value)}
            onBlur={() => handleSaveRename(s.id)}
            onKeyDown={(e) => handleRenameKeyDown(e, s.id)}
            onClick={(e) => e.stopPropagation()}
            className="flex-1 bg-slate-950 border border-brand-500 focus:outline-none rounded px-1.5 py-0.5 text-xs text-white"
          />
        ) : (
          <span className="flex-1 truncate pr-14" title={s.title || 'Untitled Chat'}>
            {s.title || 'Untitled Chat'}
          </span>
        )}

        {!isEditing && (
          <div className="absolute right-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={(e) => handlePinClick(s, e)}
              className="p-1 text-slate-500 hover:text-brand-400 hover:bg-slate-850 rounded-lg transition-all"
              title={s.is_pinned ? "Unpin Chat" : "Pin Chat"}
            >
              {s.is_pinned ? <PinOff size={11} /> : <Pin size={11} />}
            </button>
            <button
              onClick={(e) => handleStartRename(s, e)}
              className="p-1 text-slate-500 hover:text-slate-300 hover:bg-slate-850 rounded-lg transition-all"
              title="Rename Chat"
            >
              <Edit3 size={11} />
            </button>
            <button
              onClick={(e) => handleDeleteClick(s.id, e)}
              className="p-1 text-slate-500 hover:text-red-400 hover:bg-slate-850 rounded-lg transition-all"
              title="Delete Chat"
            >
              <Trash2 size={11} />
            </button>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="flex gap-4 h-[calc(100vh-140px)] p-1 relative overflow-hidden">
      
      {/* Delete Confirmation Modal Overlay */}
      {deletingId !== null && (
        <div className="absolute inset-0 bg-slate-905/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="glass-panel p-5 max-w-xs w-full shadow-2xl border border-slate-750 space-y-4">
            <div className="flex items-center gap-2.5 text-red-400">
              <AlertTriangle size={20} className="shrink-0" />
              <h4 className="text-sm font-bold text-white">Delete Chat History</h4>
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              Are you sure you want to delete this chat session? This action cannot be undone.
            </p>
            <div className="flex justify-end gap-2.5 pt-1">
              <button
                onClick={() => setDeletingId(null)}
                className="btn-secondary py-1.5 px-3 text-[11px] rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={async () => {
                  if (deletingId) {
                    await deleteSession(deletingId);
                  }
                  setDeletingId(null);
                }}
                className="btn-danger py-1.5 px-3 text-[11px] rounded-lg"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Sidebar: Conversation History */}
      <div className={`glass-panel border border-slate-750 flex flex-col p-4 shrink-0 transition-all duration-300 ease-in-out absolute md:relative z-20 h-full ${
        sidebarOpen ? 'w-64 translate-x-0' : 'w-0 -translate-x-full md:w-0 md:opacity-0 pointer-events-none'
      }`}>
        
        {/* New Chat Button */}
        <button
          onClick={startNewChat}
          className="btn-primary w-full p-2.5 mb-3 text-xs"
        >
          <Plus size={14} />
          <span>New Chat</span>
        </button>

        {/* Search History Box */}
        <div className="relative mb-3.5 shrink-0">
          <Search size={12} className="absolute left-3 top-2.5 text-slate-500" />
          <input
            type="text"
            placeholder="Search conversations..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-slate-950 border border-slate-750 focus:border-slate-700 rounded-xl pl-8 pr-8 py-2 text-[11px] text-slate-200 placeholder-slate-500 focus:outline-none transition-all duration-200"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-3 top-2.5 text-slate-500 hover:text-slate-350 text-[10px]"
            >
              <X size={12} />
            </button>
          )}
        </div>

        {/* History Scrollable List */}
        <div className="flex-1 overflow-y-auto space-y-4 pr-1">
          {sessionsLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 size={16} className="animate-spin text-brand-500" />
            </div>
          ) : (
            <>
              {/* Pinned Group */}
              {grouped.pinned.length > 0 && (
                <div className="space-y-1.5">
                  <h5 className="text-[10px] text-brand-400 font-bold uppercase tracking-wider px-2">Pinned</h5>
                  {grouped.pinned.map(renderSessionItem)}
                </div>
              )}

              {/* Today Group */}
              {grouped.today.length > 0 && (
                <div className="space-y-1.5">
                  <h5 className="text-[10px] text-slate-500 font-bold uppercase tracking-wider px-2">Today</h5>
                  {grouped.today.map(renderSessionItem)}
                </div>
              )}

              {/* Yesterday Group */}
              {grouped.yesterday.length > 0 && (
                <div className="space-y-1.5">
                  <h5 className="text-[10px] text-slate-500 font-bold uppercase tracking-wider px-2">Yesterday</h5>
                  {grouped.yesterday.map(renderSessionItem)}
                </div>
              )}

              {/* Last 7 Days Group */}
              {grouped.last7days.length > 0 && (
                <div className="space-y-1.5">
                  <h5 className="text-[10px] text-slate-500 font-bold uppercase tracking-wider px-2">Previous 7 Days</h5>
                  {grouped.last7days.map(renderSessionItem)}
                </div>
              )}

              {/* Older Group */}
              {grouped.older.length > 0 && (
                <div className="space-y-1.5">
                  <h5 className="text-[10px] text-slate-500 font-bold uppercase tracking-wider px-2">Older</h5>
                  {grouped.older.map(renderSessionItem)}
                </div>
              )}

              {filteredSessions.length === 0 && (
                <div className="text-center text-[11px] text-slate-600 py-8">
                  {searchQuery ? "No matching chats" : "No conversation history"}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 glass-panel border border-slate-750 flex flex-col overflow-hidden relative">
        
        {/* Chat Header */}
        <div className="p-4 border-b border-slate-750 flex justify-between items-center bg-slate-900 bg-opacity-10">
          <div className="flex items-center gap-2">
            
            {/* Sidebar toggle button (visible on mobile/tablet or when sidebar collapsed) */}
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="p-2 text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-750 rounded-xl border border-slate-750 transition-all duration-200 cursor-pointer"
              title={sidebarOpen ? "Hide History" : "Show History"}
            >
              <Menu size={14} />
            </button>
            
            <div className="flex items-center gap-2.5 ml-1">
              <div className="p-2 bg-brand-500 bg-opacity-10 rounded-xl text-brand-400 border border-brand-500/20 shrink-0">
                <MessageSquare size={16} />
              </div>
              <div>
                <h3 className="font-bold text-sm text-white">
                  {sessionId === null 
                    ? "New Chat" 
                    : (sessions.find(s => s.id === sessionId)?.title || "Research Assistant")}
                </h3>
                <p className="text-[9px] text-slate-500 font-bold uppercase tracking-wider">
                  {sessionId === null ? "Draft discussion" : "Persistent Discussion"}
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {sessionId !== null && (
              <button
                onClick={(e) => handleDeleteClick(sessionId, e)}
                className="p-2 text-slate-500 hover:text-red-400 bg-slate-800 hover:bg-slate-750 rounded-xl border border-slate-750 transition-all duration-200 cursor-pointer"
                title="Delete Conversation"
              >
                <Trash2 size={14} />
              </button>
            )}
          </div>
        </div>

        {/* Message Panel */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {historyLoading ? (
            <div className="h-full flex items-center justify-center">
              <Loader2 size={24} className="animate-spin text-brand-500" />
            </div>
          ) : messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center space-y-3 p-6">
              <div className="p-4 bg-slate-850 border border-slate-750 rounded-full text-slate-500">
                <MessageSquare size={32} />
              </div>
              <h4 className="font-bold text-sm text-slate-350">Start a Research Discussion</h4>
              <p className="text-xs text-slate-500 max-w-sm leading-relaxed font-normal">
                Ask questions about your workspace documents. The system will retrieve relevant chunks and generate cited academic responses.
              </p>
            </div>
          ) : (
            <>
              {messages.map((msg) => {
                const isUser = msg.role === 'user';
                return (
                  <div
                    key={msg.id}
                    className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
                  >
                    <div className={`max-w-[80%] p-4 rounded-2xl text-sm leading-relaxed border ${
                      isUser 
                        ? 'bg-slate-800 border-slate-700 text-slate-100 rounded-br-none' 
                        : msg.content.startsWith('I am ResearchPilot AI') 
                          ? 'bg-amber-950 bg-opacity-20 border-amber-900 border-opacity-40 text-amber-305 rounded-bl-none flex gap-2.5 items-start'
                          : 'bg-slate-850 border-slate-750 text-slate-200 rounded-bl-none font-normal'
                    }`}>
                      {!isUser && msg.content.startsWith('I am ResearchPilot AI') && (
                        <AlertTriangle size={18} className="text-amber-400 shrink-0 mt-0.5" />
                      )}
                      <div className="whitespace-pre-wrap font-normal">{msg.content}</div>
                    </div>
                  </div>
                );
              })}
              {sending && (
                <div className="flex justify-start">
                  <div className="bg-slate-850 border border-slate-750 p-4 rounded-2xl rounded-bl-none text-slate-400 text-xs flex items-center gap-2">
                    <Loader2 size={14} className="animate-spin text-brand-500" />
                    <span>Llama 3.3 retrieving documents and composing answer...</span>
                  </div>
                </div>
              )}
            </>
          )}
          
          {error && (
            <div className="bg-red-950 bg-opacity-40 border border-red-900 border-opacity-50 text-red-300 text-xs p-3.5 rounded-xl">
              {error}
            </div>
          )}
          <div ref={chatBottomRef} />
        </div>

        {/* Input Bar */}
        <form onSubmit={handleSend} className="p-4 border-t border-slate-750 bg-slate-950 flex gap-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a research-related question in this workspace..."
            className="flex-1 glass-input focus:ring-brand-500 focus:border-brand-500 text-sm"
            disabled={sending || historyLoading}
          />
          <button
            type="submit"
            disabled={!input.trim() || sending || historyLoading}
            className="btn-primary p-3 rounded-xl shadow-sm"
          >
            <Send size={16} />
          </button>
        </form>

      </div>

      {/* Sidebar: Active papers list */}
      <div className="w-72 glass-panel border border-slate-750 flex flex-col p-5 overflow-hidden shrink-0 hidden lg:flex">
        <h4 className="font-bold text-sm text-white mb-1.5 flex items-center gap-2">
          <BookOpen size={16} className="text-brand-400" />
          <span>Active Context Papers</span>
        </h4>
        <p className="text-[10px] text-slate-500 font-medium leading-relaxed mb-4">
          Only localized vector embeddings for the papers listed below are sent as RAG context to the LLM.
        </p>
        
        {papers.length === 0 ? (
          <div className="flex-1 flex items-center justify-center text-center text-xs text-slate-650 font-semibold px-4">
            No papers are currently vectorized in this workspace. Upload documents or import preprints.
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto space-y-2.5 pr-1">
            {papers.map((p) => (
              <div key={p.id} className="p-3 bg-slate-950 border border-slate-750/70 hover:border-slate-700 rounded-xl transition-all duration-150 shadow-sm">
                <p className="text-xs font-semibold text-slate-200 line-clamp-2" title={p.title}>
                  {p.title}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

    </div>
  );
};

export default ResearchChat;
