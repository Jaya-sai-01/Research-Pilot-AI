import React, { useState, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import { Upload, FileText, CheckCircle, AlertTriangle, Loader2, ArrowRight } from 'lucide-react';

interface LogMessage {
  text: string;
  status: 'info' | 'success' | 'error';
}

const UploadPDF: React.FC = () => {
  const { activeWorkspace } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [isDragOver, setIsDragOver] = useState(false);
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState<LogMessage[]>([]);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const droppedFiles = e.dataTransfer.files;
    if (droppedFiles.length > 0) {
      validateAndSetFile(droppedFiles[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = e.target.files;
    if (selectedFiles && selectedFiles.length > 0) {
      validateAndSetFile(selectedFiles[0]);
    }
  };

  const validateAndSetFile = (selectedFile: File) => {
    setError('');
    setSuccess(false);
    setLogs([]);
    
    if (!selectedFile.name.toLowerCase().endsWith('.pdf')) {
      setError('Only PDF files are supported.');
      setFile(null);
      return;
    }

    if (selectedFile.size > 15 * 1024 * 1024) {
      setError('File size exceeds the limit of 15MB.');
      setFile(null);
      return;
    }

    setFile(selectedFile);
    // Auto populate title field with cleaned filename
    const cleanTitle = selectedFile.name.split('.').slice(0, -1).join('.') || selectedFile.name.replace(/\.[^/.]+$/, "");
    const formattedTitle = cleanTitle.replace(/[_-]/g, ' ').trim();
    setTitle(formattedTitle.charAt(0).toUpperCase() + formattedTitle.slice(1));
  };

  const triggerFileInput = () => {
    fileInputRef.current?.click();
  };

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || !activeWorkspace) return;

    setLoading(true);
    setError('');
    setSuccess(false);
    
    const newLogs: LogMessage[] = [
      { text: 'Starting pipeline...', status: 'info' }
    ];
    setLogs([...newLogs]);

    const formData = new FormData();
    formData.append('file', file);
    if (title.trim()) {
      formData.append('title', title);
    }

    try {
      // Step 1: Uploading
      updateLogs('Uploading PDF file layers to backend...', 'info');
      
      const response = await api.post(
        `/papers/workspace/${activeWorkspace.id}/upload`, 
        formData, 
        {
          headers: {
            'Content-Type': 'multipart/form-data'
          }
        }
      );
      
      // Step 2: Extraction completed
      updateLogs('PDF uploads complete. Extracting text layers...', 'success');
      
      // Step 3: Vector indexing
      if (response.data.indexed_status) {
        updateLogs('Sentence-transformer tokens generated. Stored embeddings in ChromaDB.', 'success');
        updateLogs('Metadata synced with relational database.', 'success');
      } else {
        updateLogs('Warning: Document stored, but ChromaDB indexing failed. Checking parameters...', 'error');
      }
      
      setSuccess(true);
      setFile(null);
      setTitle('');
    } catch (err: any) {
      console.error(err);
      const errDetail = err.response?.data?.detail || 'An error occurred during file processing.';
      updateLogs(`Pipeline Error: ${errDetail}`, 'error');
      setError(errDetail);
    } finally {
      setLoading(false);
    }
  };

  const updateLogs = (text: string, status: 'info' | 'success' | 'error') => {
    setLogs(prev => [...prev, { text, status }]);
  };

  if (!activeWorkspace) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center space-y-4">
        <Upload size={48} className="text-slate-700" />
        <h2 className="text-xl font-bold text-slate-300">No Active Workspace Selected</h2>
        <p className="text-slate-500 max-w-sm text-sm">
          Please select or create an active workspace first before uploading local PDFs.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-8 p-1">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-white tracking-tight">Upload PDF Document</h1>
        <p className="text-slate-400 text-sm">
          Drag and drop local research papers to extract text, calculate vector embeddings, and store them in ChromaDB.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        
        {/* Upload Column */}
        <div className="space-y-6">
          <div className="glass-panel p-6 border border-slate-750">
            <form onSubmit={handleUploadSubmit} className="space-y-5">
              
              {/* Drag/Drop Zone */}
              <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={triggerFileInput}
                className={`border-2 border-dashed rounded-2xl p-8 flex flex-col items-center justify-center gap-3.5 cursor-pointer transition-all duration-200 bg-slate-950 bg-opacity-10 ${
                  isDragOver 
                    ? 'border-brand-500 bg-brand-500 bg-opacity-5' 
                    : file 
                      ? 'border-emerald-900 bg-emerald-950 bg-opacity-[0.08]' 
                      : 'border-slate-750 hover:border-slate-700 hover:bg-slate-950/30'
                }`}
              >
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleFileChange}
                  accept=".pdf"
                  className="hidden"
                />
                
                {file ? (
                  <div className="text-emerald-400 p-3 bg-emerald-950/20 rounded-xl border border-emerald-900/60">
                    <FileText size={36} />
                  </div>
                ) : (
                  <div className="text-slate-500 p-3 bg-slate-950 rounded-xl border border-slate-750">
                    <Upload size={36} />
                  </div>
                )}
                
                <div className="text-center">
                  {file ? (
                    <>
                      <p className="text-sm font-semibold text-slate-200">{file.name}</p>
                      <p className="text-xs text-slate-500 font-medium mt-1">
                        {(file.size / (1024 * 1024)).toFixed(2)} MB — Click to replace
                      </p>
                    </>
                  ) : (
                    <>
                      <p className="text-sm font-semibold text-slate-200">
                        Drag and drop your research paper PDF here
                      </p>
                      <p className="text-xs text-slate-500 font-medium mt-1">
                        or click to browse local files (max 15MB)
                      </p>
                    </>
                  )}
                </div>
              </div>

              {/* Title override */}
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wider">
                  Document Title (Optional)
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Deep Residual Learning for Image Recognition"
                  className="w-full glass-input"
                  disabled={loading || !file}
                />
              </div>

              <button
                type="submit"
                disabled={loading || !file}
                className="btn-primary w-full py-3 px-4 flex items-center justify-center gap-2"
              >
                {loading ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    <span>Processing Document...</span>
                  </>
                ) : (
                  <>
                    <span>Upload & Index</span>
                    <ArrowRight size={16} />
                  </>
                )}
              </button>
            </form>
          </div>
          
          {error && (
            <div className="bg-red-950 bg-opacity-40 border border-red-900 border-opacity-50 text-red-300 text-sm px-4 py-3.5 rounded-xl flex items-center gap-2.5">
              <AlertTriangle size={18} className="text-red-400 shrink-0" />
              <span>{error}</span>
            </div>
          )}
        </div>

        {/* Pipeline Progress logs */}
        <div className="glass-panel p-6 border border-slate-750 flex flex-col justify-between min-h-[350px]">
          <div>
            <h3 className="font-bold text-base text-white mb-1.5 flex items-center gap-2">
              <FileText size={18} className="text-brand-400" />
              <span>Indexing Pipeline Logs</span>
            </h3>
            <p className="text-slate-500 text-xs mb-4">
              Real-time breakdown of parsing, chunking, and ChromaDB vector syncing.
            </p>
            
            {logs.length === 0 ? (
              <div className="py-12 text-center text-xs text-slate-500 font-medium">
                Waiting to receive PDF file streams...
              </div>
            ) : (
              <div className="bg-slate-950 border border-slate-750 p-4 rounded-xl space-y-3 font-mono text-xs max-h-[260px] overflow-y-auto pr-1">
                {logs.map((log, i) => (
                  <div key={i} className="flex gap-2 text-left">
                    <span className="text-slate-500">[{i+1}]</span>
                    <span className={
                      log.status === 'success' ? 'text-emerald-400' :
                      log.status === 'error' ? 'text-red-400' : 'text-slate-350'
                    }>
                      {log.text}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
          
          {success && (
            <div className="mt-4 p-4 bg-emerald-950 bg-opacity-30 border border-emerald-800/60 rounded-xl flex items-center gap-3 text-emerald-400">
              <CheckCircle size={22} className="shrink-0 animate-fadeIn" />
              <div>
                <h4 className="text-sm font-bold">Vector Index Synced!</h4>
                <p className="text-xs text-slate-400 leading-relaxed">
                  The PDF has been processed. You can now run summaries, literature reviews, or chat with it.
                </p>
              </div>
            </div>
          )}
        </div>
        
      </div>
    </div>
  );
};

export default UploadPDF;
