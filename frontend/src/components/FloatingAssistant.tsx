import React, { useEffect, useRef, useState } from 'react';
import { Bot, Loader2, Maximize2, MessageSquare, Send, Sparkles, Trash2, X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useSharedChat } from '../context/ChatContext';

const suggestions = [
  'Summarize my uploaded papers',
  'Compare papers in this workspace',
  'Extract key findings',
  'Find limitations in a paper',
];

const FloatingAssistant: React.FC = () => {
  const { activeWorkspace } = useAuth();
  const navigate = useNavigate();
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);
  const {
    messages,
    historyLoading,
    sending,
    error,
    assistantOpen,
    setAssistantOpen,
    sendMessage,
    clearMessages,
  } = useSharedChat();

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending, assistantOpen]);

  const submitCurrentInput = async () => {
    if (!input.trim() || sending || !activeWorkspace) return;
    const message = input;
    setInput('');
    await sendMessage(message);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    await submitCurrentInput();
  };

  const sendSuggestion = async (message: string) => {
    if (sending || !activeWorkspace) return;
    setInput('');
    await sendMessage(message);
  };

  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col items-end">
      {assistantOpen && (
        <div className="mb-4 flex h-[min(680px,calc(100vh-120px))] w-[min(420px,calc(100vw-40px))] flex-col overflow-hidden rounded-2xl border border-slate-750 bg-slate-900 shadow-glass animate-fadeIn">
          <div className="flex items-center justify-between border-b border-slate-750 bg-slate-850 px-4 py-3">
            <div className="flex items-center gap-3 min-w-0">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-500 bg-opacity-10 text-brand-400 border border-brand-500/20">
                <Bot size={18} />
              </div>
              <div className="min-w-0">
                <h3 className="text-sm font-bold text-white">Research Assistant</h3>
                <p className="truncate text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                  {activeWorkspace ? activeWorkspace.name : 'Select a workspace'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-1">
              {messages.length > 0 && (
                <button
                  type="button"
                  onClick={() => {
                    if (window.confirm('Clear this workspace conversation?')) {
                      void clearMessages();
                    }
                  }}
                  className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-slate-800 hover:text-red-400"
                  title="Clear conversation"
                >
                  <Trash2 size={15} />
                </button>
              )}
              <button
                type="button"
                onClick={() => {
                  setAssistantOpen(false);
                  navigate('/chat');
                }}
                className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-slate-800 hover:text-white"
                title="Open full Research Chat"
              >
                <Maximize2 size={16} />
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-4 py-4">
            {!activeWorkspace ? (
              <div className="flex h-full flex-col items-center justify-center text-center">
                <MessageSquare size={34} className="mb-3 text-slate-700" />
                <p className="text-sm font-bold text-slate-300">No active workspace selected</p>
                <p className="mt-1 max-w-xs text-xs leading-relaxed text-slate-500">
                  Choose or create a workspace to ask questions about your papers.
                </p>
              </div>
            ) : historyLoading ? (
              <div className="flex h-full items-center justify-center">
                <Loader2 size={22} className="animate-spin text-brand-500" />
              </div>
            ) : messages.length === 0 ? (
              <div className="space-y-4">
                <div className="rounded-2xl border border-slate-750 bg-slate-850 p-4">
                  <div className="mb-2 flex items-center gap-2 text-brand-400">
                    <Sparkles size={16} />
                    <span className="text-xs font-bold uppercase tracking-wider">Research assistant</span>
                  </div>
                  <p className="text-sm leading-relaxed text-slate-300">
                    Ask for summaries, comparisons, methodology explanations, limitations, key findings, or writing help.
                  </p>
                </div>
                <div className="grid grid-cols-1 gap-2">
                  {suggestions.map((suggestion) => (
                    <button
                      key={suggestion}
                      type="button"
                      onClick={() => sendSuggestion(suggestion)}
                      className="rounded-xl border border-slate-750 bg-slate-950 bg-opacity-40 px-3 py-2.5 text-left text-xs font-semibold text-slate-300 transition-all duration-200 hover:border-slate-700 hover:bg-slate-800/40 hover:text-slate-200"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                {messages.map((message) => {
                  const isUser = message.role === 'user';
                  return (
                    <div key={message.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                      <div
                        className={`max-w-[86%] rounded-2xl border px-4 py-3 text-sm leading-relaxed ${
                          isUser
                            ? 'rounded-br-none border-slate-700 bg-slate-800 text-slate-100'
                            : 'rounded-bl-none border-slate-750 bg-slate-850 text-slate-200'
                        }`}
                      >
                        <div className="whitespace-pre-wrap font-light">{message.content}</div>
                      </div>
                    </div>
                  );
                })}
                {sending && (
                  <div className="flex justify-start">
                    <div className="flex items-center gap-2 rounded-2xl rounded-bl-none border border-slate-750 bg-slate-850 px-4 py-3 text-xs text-slate-400">
                      <Loader2 size={14} className="animate-spin text-brand-500" />
                      <span>Searching papers and composing...</span>
                    </div>
                  </div>
                )}
                <div ref={bottomRef} />
              </div>
            )}
          </div>

          {error && (
            <div className="mx-4 mb-3 rounded-xl border border-red-900 border-opacity-50 bg-red-950 bg-opacity-40 px-3 py-2 text-xs text-red-300">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="flex gap-2 border-t border-slate-750 bg-slate-900 bg-opacity-40 p-3">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value.slice(0, 4000))}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void submitCurrentInput();
                }
              }}
              disabled={!activeWorkspace || sending || historyLoading}
              placeholder="Ask your research assistant..."
              rows={1}
              className="min-h-[44px] flex-1 resize-none rounded-xl border border-slate-750 bg-slate-950 px-3 py-3 text-sm text-slate-200 placeholder:text-slate-650 focus:border-slate-700 focus:outline-none disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={!input.trim() || !activeWorkspace || sending || historyLoading}
              className="btn-primary flex h-11 w-11 p-0 shrink-0 items-center justify-center rounded-xl bg-brand-500 hover:bg-brand-600 shadow-sm"
              title="Send message"
            >
              {sending ? <Loader2 size={17} className="animate-spin" /> : <Send size={17} />}
            </button>
          </form>
        </div>
      )}

      <button
        type="button"
        onClick={() => setAssistantOpen(!assistantOpen)}
        className="flex h-14 w-14 items-center justify-center rounded-full bg-brand-500 text-white shadow-md transition-all duration-200 hover:bg-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-400 focus:ring-offset-2 focus:ring-offset-slate-900"
        title={assistantOpen ? 'Close Research Assistant' : 'Open Research Assistant'}
        aria-label={assistantOpen ? 'Close Research Assistant' : 'Open Research Assistant'}
      >
        {assistantOpen ? <X size={22} /> : <Bot size={23} />}
      </button>
    </div>
  );
};

export default FloatingAssistant;
