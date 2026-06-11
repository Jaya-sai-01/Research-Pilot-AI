import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import api from '../services/api';
import { useAuth } from './AuthContext';

export interface SharedChatMessage {
  id: number | string;
  session_id?: number;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  pending?: boolean;
}

export interface ChatSessionBrief {
  id: number;
  workspace_id: number;
  user_id: number;
  title: string | null;
  is_pinned: boolean;
  created_at: string;
  updated_at: string;
}

interface SendMessageOptions {
  documentIds?: number[];
  paperIds?: number[];
}

interface ChatContextType {
  sessionId: number | null;
  messages: SharedChatMessage[];
  historyLoading: boolean;
  sending: boolean;
  error: string;
  assistantOpen: boolean;
  setAssistantOpen: (open: boolean) => void;
  refreshHistory: () => Promise<void>;
  sendMessage: (content: string, options?: SendMessageOptions) => Promise<boolean>;
  clearMessages: () => Promise<void>;
  
  // Multiple sessions features
  sessions: ChatSessionBrief[];
  sessionsLoading: boolean;
  fetchSessions: () => Promise<void>;
  selectSession: (id: number | null) => Promise<void>;
  startNewChat: () => void;
  deleteSession: (id: number) => Promise<void>;
  renameSession: (id: number, title: string) => Promise<void>;
  togglePinSession: (id: number, isPinned: boolean) => Promise<void>;
}

const ChatContext = createContext<ChatContextType | undefined>(undefined);
const CHAT_CHANNEL = 'research-pilot-shared-chat';

export const ChatProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { activeWorkspace, user } = useAuth();
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<SharedChatMessage[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [assistantOpen, setAssistantOpen] = useState(false);
  
  const [sessions, setSessions] = useState<ChatSessionBrief[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);

  const channelRef = useRef<BroadcastChannel | null>(null);
  const workspaceIdRef = useRef<number | undefined>(activeWorkspace?.id);

  useEffect(() => {
    workspaceIdRef.current = activeWorkspace?.id;
  }, [activeWorkspace?.id]);

  const fetchSessions = useCallback(async () => {
    const workspaceId = workspaceIdRef.current;
    if (!workspaceId || !user) {
      setSessions([]);
      return;
    }
    setSessionsLoading(true);
    try {
      const response = await api.get(`/chat/workspace/${workspaceId}/sessions`);
      if (workspaceIdRef.current !== workspaceId) return;
      setSessions(response.data || []);
    } catch (err) {
      console.error('Failed to fetch chat sessions list:', err);
    } finally {
      if (workspaceIdRef.current === workspaceId) {
        setSessionsLoading(false);
      }
    }
  }, [user]);

  const selectSession = useCallback(async (id: number | null) => {
    const workspaceId = workspaceIdRef.current;
    if (!workspaceId) return;
    
    setSessionId(id);
    if (id === null) {
      setMessages([]);
      return;
    }

    setHistoryLoading(true);
    setError('');
    try {
      const response = await api.get(`/chat/session/${id}/messages`);
      if (workspaceIdRef.current !== workspaceId) return;
      setMessages(response.data || []);
    } catch (err) {
      console.error(err);
      if (workspaceIdRef.current === workspaceId) {
        setError('Failed to load session messages.');
      }
    } finally {
      if (workspaceIdRef.current === workspaceId) {
        setHistoryLoading(false);
      }
    }
  }, []);

  const refreshHistory = useCallback(async () => {
    const workspaceId = workspaceIdRef.current;
    if (!workspaceId || !user) {
      setSessionId(null);
      setMessages([]);
      setSessions([]);
      return;
    }

    setHistoryLoading(true);
    setError('');
    try {
      const sessionsResponse = await api.get(`/chat/workspace/${workspaceId}/sessions`);
      if (workspaceIdRef.current !== workspaceId) return;
      
      const fetchedSessions: ChatSessionBrief[] = sessionsResponse.data || [];
      setSessions(fetchedSessions);

      if (fetchedSessions.length > 0) {
        // Load the most recently updated session
        const sortedByUpdate = [...fetchedSessions].sort(
          (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
        );
        const recentSession = sortedByUpdate[0];
        
        setSessionId(recentSession.id);
        const messagesResponse = await api.get(`/chat/session/${recentSession.id}/messages`);
        if (workspaceIdRef.current !== workspaceId) return;
        setMessages(messagesResponse.data || []);
      } else {
        setSessionId(null);
        setMessages([]);
      }
    } catch (err) {
      console.error(err);
      if (workspaceIdRef.current === workspaceId) {
        setError('Failed to load workspace conversations.');
      }
    } finally {
      if (workspaceIdRef.current === workspaceId) {
        setHistoryLoading(false);
      }
    }
  }, [user]);

  useEffect(() => {
    setSessionId(null);
    setMessages([]);
    setSessions([]);
    setError('');
    setSending(false);
    void refreshHistory();
  }, [activeWorkspace?.id, refreshHistory]);

  useEffect(() => {
    if (typeof BroadcastChannel === 'undefined') return;
    const channel = new BroadcastChannel(CHAT_CHANNEL);
    channelRef.current = channel;
    channel.onmessage = (event) => {
      if (event.data?.workspaceId === workspaceIdRef.current) {
        void refreshHistory();
      }
    };
    return () => {
      channel.close();
      channelRef.current = null;
    };
  }, [refreshHistory]);

  useEffect(() => {
    const handleFocus = () => void refreshHistory();
    window.addEventListener('focus', handleFocus);
    return () => window.removeEventListener('focus', handleFocus);
  }, [refreshHistory]);

  const notifyConversationChanged = (workspaceId: number) => {
    channelRef.current?.postMessage({ workspaceId, changedAt: Date.now() });
  };

  const sendMessage = useCallback(async (
    content: string,
    options: SendMessageOptions = {},
  ) => {
    const workspaceId = workspaceIdRef.current;
    const trimmed = content.trim();
    if (!workspaceId || !trimmed || sending) return false;

    const pendingId = `pending-${Date.now()}`;
    const pendingMessage: SharedChatMessage = {
      id: pendingId,
      role: 'user',
      content: trimmed,
      timestamp: new Date().toISOString(),
      pending: true,
    };
    setMessages((previous) => [...previous, pendingMessage]);
    setSending(true);
    setError('');

    try {
      let response;
      if (sessionId === null) {
        response = await api.post(`/chat/session`, {
          workspace_id: workspaceId,
          first_message: trimmed,
          document_ids: options.documentIds || [],
          paper_ids: options.paperIds || [],
        });
      } else {
        response = await api.post(`/chat/session/${sessionId}/message`, {
          content: trimmed,
          document_ids: options.documentIds || [],
          paper_ids: options.paperIds || [],
        });
      }

      if (workspaceIdRef.current !== workspaceId) return true;
      
      const newSessionId = response.data.session_id;
      setSessionId(newSessionId);
      setMessages((previous) => [
        ...previous.filter((message) => message.id !== pendingId),
        ...(response.data.messages || []),
      ]);
      
      void fetchSessions();
      notifyConversationChanged(workspaceId);
      return true;
    } catch (err: any) {
      console.error(err);
      if (workspaceIdRef.current === workspaceId) {
        setMessages((previous) => previous.filter((message) => message.id !== pendingId));
        setError(err.response?.data?.detail || 'Research Assistant could not respond.');
      }
      return false;
    } finally {
      if (workspaceIdRef.current === workspaceId) {
        setSending(false);
      }
    }
  }, [sending, sessionId, fetchSessions]);

  const deleteSession = useCallback(async (id: number) => {
    const workspaceId = workspaceIdRef.current;
    if (!workspaceId) return;
    setError('');
    try {
      await api.delete(`/chat/session/${id}`);
      if (workspaceIdRef.current === workspaceId) {
        if (sessionId === id) {
          setSessionId(null);
          setMessages([]);
        }
        void fetchSessions();
      }
      notifyConversationChanged(workspaceId);
    } catch (err) {
      console.error(err);
      setError('Failed to delete the chat session.');
    }
  }, [sessionId, fetchSessions]);

  const renameSession = useCallback(async (id: number, title: string) => {
    const workspaceId = workspaceIdRef.current;
    if (!workspaceId) return;
    setError('');
    try {
      await api.patch(`/chat/session/${id}/rename`, { title });
      if (workspaceIdRef.current === workspaceId) {
        void fetchSessions();
      }
      notifyConversationChanged(workspaceId);
    } catch (err) {
      console.error(err);
      setError('Failed to rename the chat session.');
    }
  }, [fetchSessions]);

  const togglePinSession = useCallback(async (id: number, isPinned: boolean) => {
    const workspaceId = workspaceIdRef.current;
    if (!workspaceId) return;
    setError('');
    try {
      await api.patch(`/chat/session/${id}/pin`, { is_pinned: isPinned });
      if (workspaceIdRef.current === workspaceId) {
        void fetchSessions();
      }
      notifyConversationChanged(workspaceId);
    } catch (err) {
      console.error(err);
      setError('Failed to pin the chat session.');
    }
  }, [fetchSessions]);

  const startNewChat = useCallback(() => {
    setSessionId(null);
    setMessages([]);
    setError('');
  }, []);

  const clearMessages = useCallback(async () => {
    const workspaceId = workspaceIdRef.current;
    if (!workspaceId || sessionId === null) return;
    setError('');
    try {
      await api.delete(`/chat/session/${sessionId}`);
      if (workspaceIdRef.current === workspaceId) {
        setSessionId(null);
        setMessages([]);
        void fetchSessions();
      }
      notifyConversationChanged(workspaceId);
    } catch (err) {
      console.error(err);
      setError('Failed to delete this chat session.');
    }
  }, [sessionId, fetchSessions]);

  const value = useMemo<ChatContextType>(() => ({
    sessionId,
    messages,
    historyLoading,
    sending,
    error,
    assistantOpen,
    setAssistantOpen,
    refreshHistory,
    sendMessage,
    clearMessages,
    
    // Multiple sessions features
    sessions,
    sessionsLoading,
    fetchSessions,
    selectSession,
    startNewChat,
    deleteSession,
    renameSession,
    togglePinSession,
  }), [
    sessionId,
    messages,
    historyLoading,
    sending,
    error,
    assistantOpen,
    refreshHistory,
    sendMessage,
    clearMessages,
    sessions,
    sessionsLoading,
    fetchSessions,
    selectSession,
    startNewChat,
    deleteSession,
    renameSession,
    togglePinSession,
  ]);

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
};

export const useSharedChat = () => {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error('useSharedChat must be used within ChatProvider');
  }
  return context;
};
