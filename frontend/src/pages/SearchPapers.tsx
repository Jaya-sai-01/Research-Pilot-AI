import React, { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import { Search, Loader2, ArrowRight, ExternalLink, Plus, Check, Info, X } from 'lucide-react';

interface DiscoveredPaper {
  title: string;
  doi?: string;
  authors: string[];
  abstract: string;
  source: string;
  published_date: string;
  publication_year?: string;
  pdf_url: string;
  paper_url: string;
  url?: string;
  doi_url?: string;
  source_url?: string;
  publisher_url?: string;
  ieee_url?: string;
  preferred_access_url?: string;
  preferred_access_type?: string;
  open_url?: string;
  retrieved_via?: string;
  access_type?: string;
  citation_count: number;
  publisher?: string;
  journal?: string;
  venue?: string;
}

type SourceFilter = 'all' | 'api' | 'scraped';

const API_SOURCES = new Set(['arXiv', 'PubMed', 'Semantic Scholar', 'Crossref', 'CORE', 'DOAJ']);
const SOURCE_STYLES: Record<string, string> = {
  arXiv: 'bg-red-950 text-red-300 border-red-800',
  PubMed: 'bg-cyan-950 text-cyan-300 border-cyan-800',
  'Semantic Scholar': 'bg-violet-950 text-violet-300 border-violet-800',
  Crossref: 'bg-amber-950 text-amber-300 border-amber-800',
  CORE: 'bg-lime-950 text-lime-300 border-lime-800',
  DOAJ: 'bg-green-950 text-green-300 border-green-800',
  IEEE: 'bg-blue-950 text-blue-300 border-blue-800',
  ACM: 'bg-emerald-950 text-emerald-300 border-emerald-800',
  Springer: 'bg-sky-950 text-sky-300 border-sky-800',
  Elsevier: 'bg-orange-950 text-orange-300 border-orange-800',
  Wiley: 'bg-purple-950 text-purple-300 border-purple-800',
  'Taylor & Francis': 'bg-pink-950 text-pink-300 border-pink-800',
  SAGE: 'bg-rose-950 text-rose-300 border-rose-800',
  OUP: 'bg-indigo-950 text-indigo-300 border-indigo-800',
  CUP: 'bg-teal-950 text-teal-300 border-teal-800',
  AAAI: 'bg-slate-800 text-slate-200 border-slate-600',
  NeurIPS: 'bg-fuchsia-950 text-fuchsia-300 border-fuchsia-800',
  ICML: 'bg-orange-950 text-orange-300 border-orange-800',
  ICLR: 'bg-teal-950 text-teal-300 border-teal-800',
};

const paperKey = (paper: DiscoveredPaper) =>
  `${paper.source}:${paper.paper_url || paper.title}`.toLowerCase();

const getDoiUrl = (paper: DiscoveredPaper) =>
  paper.doi_url || (paper.doi ? `https://doi.org/${paper.doi}` : '');

const getFinalOpenUrl = (paper: DiscoveredPaper) =>
  paper.pdf_url || getDoiUrl(paper) || paper.source_url || paper.url || paper.paper_url || '';

const getSourcePageUrl = (paper: DiscoveredPaper) =>
  paper.source_url || paper.url || paper.paper_url || paper.publisher_url || '';

const getAccessType = (paper: DiscoveredPaper) => {
  if (paper.pdf_url) return 'Open PDF';
  if (paper.doi_url || paper.doi) return 'DOI';
  if (paper.source_url || paper.publisher_url || paper.url) return 'Publisher Page';
  if (paper.paper_url || paper.ieee_url) return 'IEEE Page';
  if (paper.preferred_access_type) return paper.preferred_access_type;
  if (paper.access_type) return paper.access_type;
  return 'Unavailable';
};

const paperUrlRow = (label: string, value?: string) => (
  <div className="flex items-center gap-1.5 bg-slate-950 border border-slate-750/70 p-3 rounded-xl hover:border-slate-700 transition-colors duration-150">
    <span className="text-xs text-slate-400 shrink-0">{label}:</span>
    {value ? (
      <a
        href={value}
        target="_blank"
        rel="noopener noreferrer"
        className="text-xs text-brand-400 hover:underline truncate ml-1"
      >
        {value}
      </a>
    ) : (
      <span className="text-xs text-slate-600 ml-1">Unavailable</span>
    )}
  </div>
);

const SearchPapers: React.FC = () => {
  const { activeWorkspace } = useAuth();
  const [query, setQuery] = useState('');
  const [papers, setPapers] = useState<DiscoveredPaper[]>([]);
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('all');
  const [loading, setLoading] = useState(false);
  const [importingKey, setImportingKey] = useState<string | null>(null);
  const [importedKeys, setImportedKeys] = useState<Set<string>>(new Set());
  const [selectedPaper, setSelectedPaper] = useState<DiscoveredPaper | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    papers.forEach((paper) => {
      console.info('ResearchPilot paper access URLs', {
        title: paper.title,
        source: paper.source,
        pdf_url: paper.pdf_url || '',
        doi_url: getDoiUrl(paper),
        source_url: paper.source_url || '',
        url: paper.url || paper.paper_url || '',
        publisher_url: paper.publisher_url || '',
        ieee_url: paper.ieee_url || '',
        final_open_url: getFinalOpenUrl(paper),
      });
    });
  }, [papers]);

  const filteredPapers = useMemo(() => {
    if (sourceFilter === 'api') {
      return papers.filter((paper) => API_SOURCES.has(paper.source));
    }
    if (sourceFilter === 'scraped') {
      return papers.filter((paper) => !API_SOURCES.has(paper.source));
    }
    return papers;
  }, [papers, sourceFilter]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError('');
    try {
      const response = await api.get('/papers/search', { params: { q: query.trim() } });
      const results: DiscoveredPaper[] = response.data.papers || [];
      setPapers(results);
      setImportedKeys(new Set());
      if (results.length === 0) {
        setError('No papers found matching your query.');
      }
    } catch (err) {
      console.error(err);
      setError('Hybrid search failed. Some academic providers may be temporarily unavailable.');
    } finally {
      setLoading(false);
    }
  };

  const handleImport = async (paper: DiscoveredPaper) => {
    if (!activeWorkspace) {
      setError('Please select or create an active workspace first.');
      return;
    }

    const key = paperKey(paper);
    setImportingKey(key);
    setError('');
    try {
      await api.post(`/papers/workspace/${activeWorkspace.id}/import`, paper);
      setImportedKeys((previous) => new Set(previous).add(key));
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to import paper.');
    } finally {
      setImportingKey(null);
    }
  };

  const openPaper = (paper: DiscoveredPaper) => {
    const finalUrl = getFinalOpenUrl(paper);
    console.info('ResearchPilot open paper selected URL', {
      title: paper.title,
      source: paper.source,
      pdf_url: paper.pdf_url || '',
      doi_url: getDoiUrl(paper),
      source_url: paper.source_url || '',
      url: paper.url || paper.paper_url || '',
      final_open_url: finalUrl,
    });
    if (!finalUrl) {
      setError('No accessible paper link available');
      return;
    }
    window.open(finalUrl, '_blank', 'noopener,noreferrer');
  };

  return (
    <div className="space-y-7 p-1">
      <div>
        <h1 className="text-3xl font-bold text-white">Hybrid Research Search</h1>
        <p className="text-slate-400 text-sm">
          Search APIs and public academic metadata sources from one workspace.
        </p>
      </div>

      <form onSubmit={handleSearch} className="flex gap-3 max-w-3xl">
        <div className="relative flex-1">
          <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center text-slate-500 pointer-events-none">
            <Search size={18} />
          </span>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by topic, title, author, or keyword..."
            className="w-full glass-input pl-10"
            required
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="btn-primary py-3 px-6 text-sm"
        >
          {loading ? <Loader2 size={16} className="animate-spin text-white" /> : <ArrowRight size={16} />}
          <span>{loading ? 'Searching...' : 'Search'}</span>
        </button>
      </form>

      <div className="inline-flex border border-slate-750 bg-slate-950 p-1 rounded-xl" role="group" aria-label="Source filter">
        {([
          ['all', 'All Sources'],
          ['api', 'APIs Only'],
          ['scraped', 'Scraped Sources Only'],
        ] as const).map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => setSourceFilter(value)}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors duration-200 ${
              sourceFilter === value
                ? 'bg-slate-800 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {error && (
        <div className="bg-red-950 bg-opacity-40 border border-red-900 text-red-300 text-sm px-4 py-3 rounded-lg max-w-3xl">
          {error}
        </div>
      )}

      {papers.length > 0 && (
        <div className="flex items-center justify-between text-xs text-slate-500">
          <span>{filteredPapers.length} of {papers.length} results</span>
          <span>Ranked by relevance, citations, and recency</span>
        </div>
      )}

      {filteredPapers.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {filteredPapers.map((paper) => {
            const key = paperKey(paper);
            const sourcePageUrl = getSourcePageUrl(paper);
            return (
              <div key={key} className="glass-panel p-5 border border-slate-750 flex flex-col justify-between gap-4">
                <div className="space-y-2.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${SOURCE_STYLES[paper.source] || 'bg-slate-950 text-slate-400 border-slate-750'}`}>
                      Source: {paper.source}
                    </span>
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded border bg-slate-950 text-slate-400 border-slate-750">
                      Retrieved Via: {paper.retrieved_via || paper.source}
                    </span>
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded border bg-emerald-950/20 text-emerald-400 border-emerald-900/60">
                      Access Type: {getAccessType(paper)}
                    </span>
                    {(paper.publication_year || paper.published_date) && (
                      <span className="text-[10px] text-slate-500">{paper.publication_year || paper.published_date}</span>
                    )}
                    {paper.citation_count > 0 && (
                      <span className="text-[10px] text-slate-500">{paper.citation_count} citations</span>
                    )}
                  </div>
                  {paper.source === 'IEEE' && (
                    <div className="text-[11px] text-amber-305 bg-amber-950 bg-opacity-20 border border-amber-900 px-3 py-2 rounded-lg">
                      IEEE access may depend on browser restrictions
                    </div>
                  )}
                  <h3 className="font-extrabold text-base text-white leading-snug line-clamp-2" title={paper.title}>
                    {paper.title}
                  </h3>
                  <p className="text-xs text-brand-300 font-semibold line-clamp-1">
                    {paper.authors.length ? paper.authors.join(', ') : 'Authors unavailable'}
                  </p>
                  <p className="text-slate-400 text-xs leading-relaxed line-clamp-3 font-normal">
                    {paper.abstract || 'No abstract preview is available from this source.'}
                  </p>
                </div>

                <div className="flex items-center justify-between border-t border-slate-750 pt-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => openPaper(paper)}
                      className="flex items-center gap-1.5 text-xs font-semibold text-slate-400 hover:text-slate-200 transition-colors duration-200"
                    >
                      <ExternalLink size={14} />
                      <span>Open paper</span>
                    </button>
                    {paper.pdf_url && (
                      <a
                        href={paper.pdf_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs font-semibold text-emerald-400 hover:text-emerald-300 transition-colors"
                      >
                        Open PDF
                      </a>
                    )}
                    {sourcePageUrl && (
                      <a
                        href={sourcePageUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs font-semibold text-brand-400 hover:text-brand-300 transition-colors"
                      >
                        Open Source Page
                      </a>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setSelectedPaper(paper)}
                      className="p-2 bg-slate-800 hover:bg-slate-750 text-slate-300 hover:text-white rounded-xl border border-slate-750 transition-colors"
                      title="View details"
                    >
                      <Info size={16} />
                    </button>
                    {importedKeys.has(key) ? (
                      <span className="flex items-center gap-1 bg-emerald-950/20 text-emerald-400 border border-emerald-900 py-1.5 px-3 rounded-xl text-xs font-semibold">
                        <Check size={14} /> Imported
                      </span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => handleImport(paper)}
                        disabled={importingKey === key}
                        className="flex items-center gap-1.5 bg-brand-500/10 hover:bg-brand-500 border border-brand-500/30 hover:border-brand-500/60 text-brand-400 hover:text-white font-semibold py-1.5 px-3 rounded-xl text-xs transition-all duration-150 disabled:opacity-55 cursor-pointer"
                      >
                        {importingKey === key ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                        <span>{importingKey === key ? 'Importing...' : 'Import'}</span>
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {papers.length > 0 && filteredPapers.length === 0 && (
        <p className="text-sm text-slate-500">No results are available for this source category.</p>
      )}

      {selectedPaper && (
        <div className="fixed inset-0 bg-black bg-opacity-65 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="glass-panel max-w-2xl w-full p-6 relative shadow-2xl animate-fadeIn max-h-[85vh] flex flex-col">
            <button
              type="button"
              onClick={() => setSelectedPaper(null)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white"
              title="Close"
            >
              <X size={20} />
            </button>
            <div className="overflow-y-auto pr-1 space-y-4">
              <div className="pr-8">
                <span className={`inline-block text-[10px] font-bold px-2 py-0.5 rounded border ${SOURCE_STYLES[selectedPaper.source] || 'bg-slate-955 text-slate-400 border-slate-750'}`}>
                  Source: {selectedPaper.source}
                </span>
                <span className="inline-block ml-2 text-[10px] font-bold px-2 py-0.5 rounded border bg-slate-955 text-slate-400 border-slate-750">
                  Retrieved Via: {selectedPaper.retrieved_via || selectedPaper.source}
                </span>
                <span className="inline-block ml-2 text-[10px] font-bold px-2 py-0.5 rounded border bg-emerald-950/20 text-emerald-400 border-emerald-900/60">
                  Access Type: {getAccessType(selectedPaper)}
                </span>
                <h2 className="text-xl font-bold text-white leading-tight mt-2">{selectedPaper.title}</h2>
                <p className="text-xs text-brand-300 font-semibold mt-1">
                  {selectedPaper.authors.join(', ') || 'Authors unavailable'}
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  {selectedPaper.publication_year || selectedPaper.published_date || 'Publication date unavailable'}
                  {selectedPaper.citation_count > 0 ? ` · ${selectedPaper.citation_count} citations` : ''}
                </p>
              </div>
              <hr className="border-slate-750" />
              <div>
                <h4 className="text-xs font-bold text-slate-400 uppercase">Abstract</h4>
                <p className="text-sm text-slate-300 leading-relaxed bg-slate-955 border border-slate-750 p-5 rounded-xl mt-2 font-normal">
                  {selectedPaper.abstract || 'No abstract preview is available from this source.'}
                </p>
              </div>
              <div className="space-y-2">
                {paperUrlRow('PDF URL', selectedPaper.pdf_url)}
                {paperUrlRow('DOI URL', getDoiUrl(selectedPaper))}
                {paperUrlRow('Source URL', selectedPaper.source_url || selectedPaper.url || selectedPaper.paper_url)}
                {paperUrlRow('Final Open URL', getFinalOpenUrl(selectedPaper))}
              </div>
              <div className="flex justify-end gap-3 pt-2">
                {selectedPaper.pdf_url && (
                  <a
                    href={selectedPaper.pdf_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-secondary py-2 px-4"
                  >
                    Open PDF
                  </a>
                )}
                {getSourcePageUrl(selectedPaper) && (
                  <a
                    href={getSourcePageUrl(selectedPaper)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-secondary py-2 px-4"
                  >
                    Open Source Page
                  </a>
                )}
                <button
                  type="button"
                  onClick={() => openPaper(selectedPaper)}
                  className="btn-secondary py-2 px-4"
                >
                  Open paper
                </button>
                <button
                  type="button"
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

export default SearchPapers;
