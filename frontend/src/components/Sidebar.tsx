import React, { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { 
  LayoutDashboard, 
  Search, 
  FolderGit, 
  Upload, 
  Wand2, 
  MessageSquare, 
  FileText, 
  LogOut, 
  Compass,
  PanelLeftClose,
  PanelLeftOpen,
  UserCircle,
} from 'lucide-react';

const Sidebar: React.FC = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(() => (
    localStorage.getItem('mainSidebarCollapsed') === 'true'
  ));

  const toggleSidebar = () => {
    setCollapsed((current) => {
      const next = !current;
      localStorage.setItem('mainSidebarCollapsed', String(next));
      return next;
    });
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const navItems = [
    { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { to: '/search', label: 'Search Papers', icon: Search },
    { to: '/workspace', label: 'My Workspace', icon: FolderGit },
    { to: '/upload', label: 'Upload PDF', icon: Upload },
    { to: '/ai-tools', label: 'AI Tools Hub', icon: Wand2 },
    { to: '/chat', label: 'Research Chat', icon: MessageSquare },
    { to: '/doc-space', label: 'Document Space', icon: FileText },
  ];

  return (
    <aside className={`bg-slate-850 border-r border-slate-750 flex flex-col h-screen shrink-0 relative z-10 shadow-glass transition-[width] duration-300 ease-in-out ${
      collapsed ? 'w-20' : 'w-64'
    }`}>
      {/* Brand Header */}
      <div className={`flex min-h-[89px] items-center border-b border-slate-750 transition-all duration-300 ${
        collapsed ? 'justify-center px-3' : 'gap-3 px-5'
      }`}>
        <div className={`bg-brand-500 p-2 rounded-xl text-white shadow-sm shrink-0 items-center justify-center ${
          collapsed ? 'hidden' : 'flex'
        }`}>
          <Compass size={22} className="text-white" />
        </div>
        <div className={`min-w-0 flex-1 overflow-hidden transition-all duration-200 ${
          collapsed ? 'w-0 opacity-0' : 'w-auto opacity-100'
        }`}>
          <h1 className="font-extrabold text-lg tracking-tight bg-gradient-to-r from-brand-300 via-brand-100 to-indigo-300 bg-clip-text text-transparent">
            ResearchPilot
          </h1>
          <span className="text-xs font-semibold text-brand-400 uppercase tracking-widest">
            AI Agent Hub
          </span>
        </div>
        <button
          type="button"
          onClick={toggleSidebar}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-800 hover:text-white"
          title={collapsed ? 'Expand navigation' : 'Collapse navigation'}
          aria-label={collapsed ? 'Expand navigation sidebar' : 'Collapse navigation sidebar'}
        >
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </button>
      </div>

      {/* Nav Menu */}
      <nav className={`flex-1 space-y-1 overflow-y-auto transition-all duration-300 ${
        collapsed ? 'p-3' : 'p-4'
      }`}>
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            title={collapsed ? item.label : undefined}
            aria-label={item.label}
            className={({ isActive }) =>
              `flex min-h-11 items-center rounded-xl text-sm font-semibold transition-all duration-200 ${
                collapsed ? 'justify-center px-2' : 'gap-3.5 px-4'
              } ${
                isActive
                  ? 'bg-slate-800 text-slate-100 border border-slate-750 shadow-sm'
                  : 'border border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800 hover:bg-opacity-40'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <item.icon size={19} className={`shrink-0 transition-colors duration-200 ${isActive ? 'text-brand-400' : 'text-slate-400'}`} />
                <span className={`overflow-hidden whitespace-nowrap transition-all duration-200 ${
                  collapsed ? 'w-0 opacity-0' : 'w-auto opacity-100'
                }`}>{item.label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* User Status and Logout */}
      <div className={`border-t border-slate-750 bg-slate-900 bg-opacity-30 transition-all duration-300 ${
        collapsed ? 'p-3' : 'p-4'
      }`}>
        <div
          className={`flex items-center mb-3 ${
            collapsed ? 'justify-center' : 'px-2'
          }`}
          title={collapsed ? user?.email : undefined}
        >
          {collapsed && <UserCircle size={21} className="text-slate-400" />}
          <div className={`overflow-hidden transition-all duration-200 ${
            collapsed ? 'w-0 opacity-0' : 'w-full pr-2 opacity-100'
          }`}>
            <p className="text-xs text-slate-500 font-medium">Signed in as</p>
            <p className="text-sm font-semibold text-slate-300 truncate" title={user?.email}>
              {user?.email}
            </p>
          </div>
        </div>
        <button
          onClick={handleLogout}
          title={collapsed ? 'Sign Out' : undefined}
          aria-label="Sign Out"
          className={`w-full flex min-h-11 items-center justify-center bg-slate-800 hover:bg-red-950 hover:bg-opacity-20 hover:text-red-300 text-slate-300 font-semibold rounded-xl text-sm border border-slate-750 hover:border-red-900 hover:border-opacity-50 transition-all duration-200 cursor-pointer ${
            collapsed ? 'px-2' : 'gap-2 px-4'
          }`}
        >
          <LogOut size={16} />
          <span className={`overflow-hidden whitespace-nowrap transition-all duration-200 ${
            collapsed ? 'w-0 opacity-0' : 'w-auto opacity-100'
          }`}>Sign Out</span>
        </button>
      </div>
    </aside>
  );
};

export default Sidebar;
