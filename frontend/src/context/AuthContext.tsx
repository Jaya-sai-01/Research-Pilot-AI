import React, { createContext, useState, useEffect, useContext } from 'react';
import api from '../services/api';

interface User {
  id: number;
  email: string;
  created_at: string;
}

interface Workspace {
  id: number;
  name: string;
  description?: string;
  user_id?: number;
  created_at: string;
}

interface AuthContextType {
  user: User | null;
  workspaces: Workspace[];
  activeWorkspace: Workspace | null;
  loading: boolean;
  login: (email: string, password: string, rememberMe?: boolean) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  createWorkspace: (name: string, description?: string) => Promise<Workspace>;
  deleteWorkspace: (id: number) => Promise<void>;
  renameWorkspace: (id: number, name: string, description?: string) => Promise<Workspace>;
  duplicateWorkspace: (id: number) => Promise<Workspace>;
  selectWorkspace: (workspace: Workspace | null) => void;
  refreshWorkspaces: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [activeWorkspace, setActiveWorkspace] = useState<Workspace | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchCurrentUser = async () => {
    try {
      const response = await api.get('/auth/me');
      setUser(response.data);
      await fetchWorkspaces();
    } catch (error) {
      logout();
    } finally {
      setLoading(false);
    }
  };

  const fetchWorkspaces = async () => {
    try {
      const response = await api.get('/workspaces/');
      setWorkspaces(response.data);
      // Select first workspace as active if none is set yet
      if (response.data.length > 0) {
        const storedWsId = localStorage.getItem('activeWorkspaceId');
        const active = response.data.find((w: Workspace) => w.id.toString() === storedWsId);
        setActiveWorkspace(active || response.data[0]);
      } else {
        setActiveWorkspace(null);
      }
    } catch (error) {
      console.error('Error fetching workspaces:', error);
    }
  };

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (token) {
      fetchCurrentUser();
    } else {
      setLoading(false);
    }
  }, []);

  const login = async (email: string, password: string, rememberMe = false) => {
    setLoading(true);
    try {
      const response = await api.post('/auth/login', { email: email.trim().toLowerCase(), password, remember_me: rememberMe });
      const { access_token, user: userData } = response.data;
      localStorage.setItem('token', access_token);
      setUser(userData);
      
      // Fetch workspaces
      const wsResponse = await api.get('/workspaces/');
      setWorkspaces(wsResponse.data);
      if (wsResponse.data.length > 0) {
        setActiveWorkspace(wsResponse.data[0]);
        localStorage.setItem('activeWorkspaceId', wsResponse.data[0].id.toString());
      }
    } catch (error) {
      setLoading(false);
      throw error;
    } finally {
      setLoading(false);
    }
  };

  const register = async (email: string, password: string) => {
    try {
      await api.post('/auth/register', { email: email.trim().toLowerCase(), password });
    } catch (error) {
      throw error;
    }
  };

  const logout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('activeWorkspaceId');
    setUser(null);
    setWorkspaces([]);
    setActiveWorkspace(null);
  };

  const createWorkspace = async (name: string, description?: string) => {
    try {
      const response = await api.post('/workspaces/', { name, description });
      const newWs = response.data;
      setWorkspaces((prev) => [...prev, newWs]);
      setActiveWorkspace(newWs);
      localStorage.setItem('activeWorkspaceId', newWs.id.toString());
      return newWs;
    } catch (error) {
      throw error;
    }
  };

  const deleteWorkspace = async (id: number) => {
    try {
      await api.delete(`/workspaces/${id}`);
      const updated = workspaces.filter((w) => w.id !== id);
      setWorkspaces(updated);
      
      if (activeWorkspace?.id === id) {
        const nextActive = updated.length > 0 ? updated[0] : null;
        setActiveWorkspace(nextActive);
        if (nextActive) {
          localStorage.setItem('activeWorkspaceId', nextActive.id.toString());
        } else {
          localStorage.removeItem('activeWorkspaceId');
        }
      }
    } catch (error) {
      throw error;
    }
  };

  const renameWorkspace = async (id: number, name: string, description?: string) => {
    const response = await api.patch(`/workspaces/${id}`, { name, description });
    const updated = response.data;
    setWorkspaces((prev) => prev.map((w) => (w.id === id ? updated : w)));
    if (activeWorkspace?.id === id) {
      setActiveWorkspace(updated);
      localStorage.setItem('activeWorkspaceId', updated.id.toString());
    }
    return updated;
  };

  const duplicateWorkspace = async (id: number) => {
    const response = await api.post(`/workspaces/${id}/duplicate`);
    const duplicate = response.data;
    setWorkspaces((prev) => [...prev, duplicate]);
    setActiveWorkspace(duplicate);
    localStorage.setItem('activeWorkspaceId', duplicate.id.toString());
    return duplicate;
  };

  const selectWorkspace = (workspace: Workspace | null) => {
    setActiveWorkspace(workspace);
    if (workspace) {
      localStorage.setItem('activeWorkspaceId', workspace.id.toString());
    } else {
      localStorage.removeItem('activeWorkspaceId');
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        workspaces,
        activeWorkspace,
        loading,
        login,
        register,
        logout,
        createWorkspace,
        deleteWorkspace,
        renameWorkspace,
        duplicateWorkspace,
        selectWorkspace,
        refreshWorkspaces: fetchWorkspaces,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
