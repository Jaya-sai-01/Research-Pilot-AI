import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import { Wand2, Loader2, Copy, Check, FileText, CheckSquare, Square, Info } from 'lucide-react';

interface Paper {
  id: number;
  title: string;
  authors: string;
}

type ToolKey = 'summarize' | 'insights' | 'lit-review' | 'compare' | 'review';

const toolEndpoints: Record<ToolKey, string> = {
  summarize: 'summarize',
  insights: 'insights',
  'lit-review': 'lit-review',
  compare: 'compare',
  review: 'review',
};

const AITools: React.FC = () => {
  const { activeWorkspace } = useAuth();
  const [papers, setPapers] = useState<Paper[]>([]);
  const [selectedPaperId, setSelectedPaperId] = useState<number | null>(null);
  const [selectedPaperIds, setSelectedPaperIds] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<ToolKey>('summarize');
  const [output, setOutput] = useState('');
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');

  const fetchPapers = async () => {
    if (!activeWorkspace) return;
    try {
      const response = await api.get(`/papers/workspace/${activeWorkspace.id}`);
      setPapers(response.data);
      if (response.data.length > 0) {
        setSelectedPaperId(response.data[0].id);
        setSelectedPaperIds([response.data[0].id]);
      }
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchPapers();
    setOutput('');
    setError('');
  }, [activeWorkspace]);

  const toggleMultiPaperSelect = (id: number) => {
    setSelectedPaperIds((prev) =>
      prev.includes(id) ? prev.filter((pid) => pid !== id) : [...prev, id]
    );
  };

  const handleRunTool = async () => {
    if (!activeWorkspace) return;
    setError('');
    setOutput('');
    setLoading(true);

    try {
      let endpoint = '';
      let payload = {};
      const isSinglePaperTool =
        activeTab === 'summarize' || activeTab === 'insights' || activeTab === 'review';

      if (isSinglePaperTool) {
        if (!selectedPaperId) {
          setError('Please select a paper first.');
          setLoading(false);
          return;
        }
        endpoint = `/tools/${toolEndpoints[activeTab]}`;
        payload = { paper_id: selectedPaperId, workspace_id: activeWorkspace.id };
      } else {
        if (selectedPaperIds.length < 2) {
          setError('Please select at least two papers.');
          setLoading(false);
          return;
        }
        endpoint = `/tools/${toolEndpoints[activeTab]}`;
        payload = { paper_ids: selectedPaperIds, workspace_id: activeWorkspace.id };
      }

      const response = await api.post(endpoint, payload);
      setOutput(response.data.content);
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || 'Failed to generate content from AI model.');
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = () => {
    navigator.clipboard.writeText(output);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!activeWorkspace) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center space-y-4">
        <Wand2 size={48} className="text-slate-700" />
        <h2 className="text-xl font-bold text-slate-300">No Active Workspace Selected</h2>
        <p className="text-slate-500 max-w-sm text-sm">
          Please select or create an active workspace first to use the AI Analysis tools.
        </p>
      </div>
    );
  }

  const tabLabels: Array<{ key: ToolKey; label: string; isMulti: boolean }> = [
    { key: 'summarize', label: 'Paper Summarizer', isMulti: false },
    { key: 'insights', label: 'Insights Generator', isMulti: false },
    { key: 'review', label: 'Research Paper Reviewer', isMulti: false },
    { key: 'lit-review', label: 'Literature Review', isMulti: true },
    { key: 'compare', label: 'Paper Comparison', isMulti: true },
  ];

  const currentTabInfo = tabLabels.find((tab) => tab.key === activeTab);

  return (
    <div className="space-y-8 p-1">
      <div>
        <h1 className="text-3xl font-bold text-white tracking-tight">AI Tools Hub</h1>
        <p className="text-slate-400 text-sm">
          Generate structured summaries, insights, paper reviews, literature reviews, and comparisons powered by Llama 3.3.
        </p>
      </div>

      <div className="flex flex-wrap gap-2 border-b border-slate-750 pb-3">
        {tabLabels.map((tab) => (
          <button
            key={tab.key}
            onClick={() => {
              setActiveTab(tab.key);
              setOutput('');
              setError('');
            }}
            className={`tab-btn ${
              activeTab === tab.key ? 'tab-btn-active' : 'tab-btn-inactive'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="space-y-6">
          <div className="glass-panel p-6 border border-slate-750">
            <h3 className="font-bold text-base text-white mb-3">
              Select {currentTabInfo?.isMulti ? 'Papers (Multiple)' : 'Paper (Single)'}
            </h3>

            {papers.length === 0 ? (
              <div className="py-8 text-center text-xs text-slate-500">
                No papers found in library. Import preprints or upload PDFs to start.
              </div>
            ) : (
              <div className="space-y-2.5 max-h-[300px] overflow-y-auto pr-1">
                {papers.map((paper) => {
                  if (currentTabInfo?.isMulti) {
                    const isSelected = selectedPaperIds.includes(paper.id);
                    return (
                      <div
                        key={paper.id}
                        onClick={() => toggleMultiPaperSelect(paper.id)}
                        className={`flex items-center gap-3 p-3 bg-slate-950 border rounded-xl cursor-pointer hover:border-slate-700 transition-colors ${
                          isSelected ? 'border-brand-500' : 'border-slate-750'
                        }`}
                      >
                        {isSelected ? (
                          <CheckSquare size={16} className="text-brand-400 shrink-0" />
                        ) : (
                          <Square size={16} className="text-slate-650 shrink-0" />
                        )}
                        <div className="min-w-0">
                          <p className="text-xs font-semibold text-slate-200 truncate">{paper.title}</p>
                          <p className="text-[10px] text-slate-500 truncate">{paper.authors}</p>
                        </div>
                      </div>
                    );
                  }

                  const isSelected = selectedPaperId === paper.id;
                  return (
                    <div
                      key={paper.id}
                      onClick={() => setSelectedPaperId(paper.id)}
                      className={`flex items-center gap-3 p-3 bg-slate-950 border rounded-xl cursor-pointer hover:border-slate-700 transition-colors ${
                        isSelected
                          ? 'border-brand-500 bg-brand-500 bg-opacity-5'
                          : 'border-slate-750'
                      }`}
                    >
                      <div className={`h-4 w-4 rounded-full border flex items-center justify-center shrink-0 ${
                        isSelected ? 'border-brand-500 text-brand-400' : 'border-slate-650'
                      }`}>
                        {isSelected && <div className="h-2 w-2 rounded-full bg-brand-500" />}
                      </div>
                      <div className="min-w-0">
                        <p className="text-xs font-semibold text-slate-200 truncate">{paper.title}</p>
                        <p className="text-[10px] text-slate-500 truncate">{paper.authors}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            <button
              onClick={handleRunTool}
              disabled={loading || papers.length === 0}
              className="btn-primary w-full py-3 px-4 mt-5 flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <Loader2 size={16} className="animate-spin text-white" />
                  <span>Generating report...</span>
                </>
              ) : (
                <>
                  <Wand2 size={16} />
                  <span>Generate Report</span>
                </>
              )}
            </button>
          </div>

          {error && (
            <div className="bg-red-950 bg-opacity-40 border border-red-900 border-opacity-50 text-red-300 text-sm px-4 py-3 rounded-xl">
              {error}
            </div>
          )}
        </div>

        <div className="lg:col-span-2 space-y-4">
          <div className="glass-panel p-6 border border-slate-750 flex flex-col justify-between min-h-[420px]">
            <div>
              <div className="flex items-center justify-between border-b border-slate-750 pb-3 mb-4">
                <h3 className="font-bold text-base text-white flex items-center gap-2">
                  <FileText size={18} className="text-brand-400" />
                  <span>AI Generated Report</span>
                </h3>
                {output && (
                  <button
                    onClick={copyToClipboard}
                    className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors py-1.5 px-3 bg-slate-800 hover:bg-slate-750 border border-slate-750 rounded-xl cursor-pointer"
                  >
                    {copied ? (
                      <>
                        <Check size={14} className="text-emerald-400" />
                        <span className="text-emerald-400">Copied</span>
                      </>
                    ) : (
                      <>
                        <Copy size={14} />
                        <span>Copy</span>
                      </>
                    )}
                  </button>
                )}
              </div>

              {loading ? (
                <div className="py-20 flex flex-col items-center justify-center gap-4">
                  <Loader2 size={36} className="animate-spin text-brand-500" />
                  <p className="text-xs text-slate-400 font-medium">Generating report...</p>
                </div>
              ) : !output ? (
                <div className="py-20 text-center text-slate-500 text-sm flex flex-col items-center justify-center gap-2.5">
                  <Info size={28} className="text-slate-750" />
                  <span>Select documents and click "Generate Report" to output results.</span>
                </div>
              ) : (
                <div className="bg-slate-950 border border-slate-750 p-6 rounded-2xl text-slate-200 text-sm leading-relaxed whitespace-pre-wrap max-h-[550px] overflow-y-auto pr-1 text-left font-normal select-text font-sans">
                  {output}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AITools;
