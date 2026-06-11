import React from 'react';
import { Link, Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { ShieldAlert, Compass, Search, MessageSquare, Cpu, FileText } from 'lucide-react';

const Home: React.FC = () => {
  const { user } = useAuth();

  // If user is already logged in, redirect straight to dashboard
  if (user) {
    return <Navigate to="/dashboard" replace />;
  }

  const features = [
    {
      title: "Scholarly Query Guardrails",
      desc: "Filters out casual chats, recipes, and sports. Enforces strict academic focus on all queries.",
      icon: ShieldAlert,
      color: "text-amber-400"
    },
    {
      title: "Hybrid Discovery Pipeline",
      desc: "Search trusted academic APIs and public metadata sources, then import papers to workspaces in one click.",
      icon: Search,
      color: "text-brand-400"
    },
    {
      title: "Text Extraction & Indexing",
      desc: "Upload local research PDFs. Extract text dynamically and compile semantic vectors to ChromaDB.",
      icon: FileText,
      color: "text-emerald-400"
    },
    {
      title: "Retrieval-Augmented Chat",
      desc: "Chat directly with your uploaded papers. Pulls relevant chunks and cites sources inline.",
      icon: MessageSquare,
      color: "text-violet-400"
    }
  ];

  return (
    <div className="min-h-screen flex flex-col justify-between relative overflow-hidden bg-slate-900">
      <div className="glow-bg top-[-10%] left-[-10%]" />
      <div className="glow-bg bottom-[-10%] right-[-10%]" />

      {/* Top Navbar */}
      <nav className="max-w-7xl mx-auto w-full px-6 py-6 flex justify-between items-center relative z-10">
        <div className="flex items-center gap-3">
          <div className="bg-brand-500 p-2 rounded-xl text-white">
            <Compass size={22} />
          </div>
          <span className="font-extrabold text-lg tracking-tight text-white font-sans">
            ResearchPilot <span className="text-brand-400 text-xs font-bold uppercase ml-1">AI</span>
          </span>
        </div>
        <div className="flex items-center gap-4">
          <Link to="/login" className="text-slate-300 hover:text-white text-sm font-semibold transition-colors">
            Sign In
          </Link>
          <Link to="/register" className="btn-primary py-2 px-4 text-sm font-semibold shadow-sm hover:shadow-glow/50">
            Sign Up Free
          </Link>
        </div>
      </nav>

      {/* Hero Body */}
      <main className="max-w-6xl mx-auto px-6 py-16 flex-1 flex flex-col items-center justify-center text-center relative z-10">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-800 border border-slate-750 mb-6 text-brand-300 font-semibold text-xs tracking-wider uppercase">
          <Cpu size={14} className="animate-spin" />
          <span>Llama 3.3 70B & ChromaDB Powered</span>
        </div>
        <h1 className="text-4xl md:text-6xl font-extrabold tracking-tight mb-6 leading-tight max-w-4xl text-white">
          Autonomous Research Intelligence{' '}
          <span className="bg-gradient-to-r from-brand-400 via-indigo-200 to-emerald-300 bg-clip-text text-transparent">
            Hub
          </span>
        </h1>
        <p className="text-slate-400 text-base md:text-lg max-w-2xl mb-8 leading-relaxed">
          Manage literature, query papers semantically, compare papers, and write reviews in a single secure environment with strict research guardrails.
        </p>
        <div className="flex gap-4 mb-20">
          <Link to="/register" className="bg-brand-500 hover:bg-brand-600 text-white font-bold py-3.5 px-8 rounded-xl text-base transition-all duration-200 cursor-pointer shadow-sm hover:shadow-glow/50">
            Start Researching
          </Link>
          <Link to="/login" className="bg-slate-800 hover:bg-slate-750 text-slate-200 font-bold py-3.5 px-8 rounded-xl text-base border border-slate-750 hover:border-slate-700 transition-all duration-200 cursor-pointer shadow-sm">
            Access Dashboard
          </Link>
        </div>

        {/* Feature Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 w-full text-left">
          {features.map((f, idx) => (
            <div key={idx} className="glass-panel glass-panel-hover p-6 flex flex-col justify-between relative group transition-all duration-200 shadow-sm">
              <div>
                <div className={`${f.color} mb-4 p-2 bg-slate-800 border border-slate-750 group-hover:border-brand-500/30 rounded-xl w-fit transition-all duration-200`}>
                  <f.icon size={22} />
                </div>
                <h3 className="font-bold text-white text-base mb-2">{f.title}</h3>
                <p className="text-slate-400 text-sm leading-relaxed">{f.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </main>

      {/* Footer */}
      <footer className="py-8 border-t border-slate-750 text-center text-xs text-slate-500 relative z-10">
        © 2026 ResearchPilot AI Agent — Autonomous Academic Assistant. All rights reserved.
      </footer>
    </div>
  );
};

export default Home;
