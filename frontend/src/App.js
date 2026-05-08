import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import {
  Github, Search, Loader2, CheckCircle2, AlertCircle,
  ChevronDown, ChevronRight, Code2, FileCode, Zap, Terminal
} from 'lucide-react';
import { ingestRepo, getStatus, queryRepo } from './hooks/api';

const EXAMPLE_QUERIES = [
  'Where is the authentication logic implemented?',
  'Which file handles database connections?',
  'Show me all API endpoints defined in this project.',
  'Where is the login function and what does it call?',
];

export default function App() {
  const [url, setUrl] = useState('');
  const [repoId, setRepoId] = useState('');
  const [repoInfo, setRepoInfo] = useState(null);
  const [ingestStatus, setIngestStatus] = useState('idle'); // idle|loading|polling|ready|error
  const [statusMsg, setStatusMsg] = useState('');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [querying, setQuerying] = useState(false);
  const [expandedSnippets, setExpandedSnippets] = useState({});
  const pollRef = useRef(null);

  const stopPolling = () => { if (pollRef.current) clearInterval(pollRef.current); };

  const handleIngest = async () => {
    if (!url.trim()) return;
    stopPolling();
    setIngestStatus('loading');
    setStatusMsg('Sending request...');
    setResults([]);

    try {
      const data = await ingestRepo(url.trim());
      setRepoId(data.repo_id);

      if (data.status === 'ready') {
        setIngestStatus('ready');
        setStatusMsg(data.message);
        return;
      }

      setIngestStatus('polling');
      setStatusMsg(data.message);

      pollRef.current = setInterval(async () => {
        try {
          const s = await getStatus(data.repo_id);
          setStatusMsg(s.message);
          if (s.status === 'ready') {
            stopPolling();
            setIngestStatus('ready');
            setRepoInfo(s);
          } else if (s.status === 'error') {
            stopPolling();
            setIngestStatus('error');
          }
        } catch { stopPolling(); setIngestStatus('error'); }
      }, 2000);
    } catch (e) {
      setIngestStatus('error');
      setStatusMsg(e?.response?.data?.detail || 'Failed to ingest repository.');
    }
  };

  const handleQuery = async (q) => {
    const question = q || query;
    if (!question.trim() || !repoId || ingestStatus !== 'ready') return;
    setQuerying(true);
    setResults([]);
    setExpandedSnippets({});
    try {
      const data = await queryRepo(repoId, question);
      setResults(prev => [{ question, ...data, ts: Date.now() }, ...prev]);
    } catch (e) {
      setResults(prev => [{
        question, answer: '**Error:** ' + (e?.response?.data?.detail || 'Query failed.'),
        results: [], ts: Date.now()
      }, ...prev]);
    } finally {
      setQuerying(false);
    }
  };

  useEffect(() => () => stopPolling(), []);

  const toggleSnippet = (key) =>
    setExpandedSnippets(p => ({ ...p, [key]: !p[key] }));

  return (
    <div style={styles.root}>
      {/* Header */}
      <header style={styles.header}>
        <div style={styles.logo}>
          <Github size={28} color="#58a6ff" />
          <span style={styles.logoText}>Repo<span style={{ color: '#58a6ff' }}>Intel</span></span>
        </div>
        <p style={styles.tagline}>Natural Language Code Search & Semantic Navigation</p>
      </header>

      <main style={styles.main}>
        {/* Ingest Panel */}
        <section style={styles.card}>
          <h2 style={styles.sectionTitle}><Zap size={18} color="#f0883e" /> Index a Repository</h2>
          <div style={styles.inputRow}>
            <input
              style={styles.input}
              placeholder="https://github.com/owner/repo"
              value={url}
              onChange={e => setUrl(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleIngest()}
            />
            <button
              style={{
                ...styles.btn,
                opacity: ingestStatus === 'loading' || ingestStatus === 'polling' ? 0.6 : 1
              }}
              onClick={handleIngest}
              disabled={ingestStatus === 'loading' || ingestStatus === 'polling'}
            >
              {ingestStatus === 'loading' || ingestStatus === 'polling'
                ? <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} />
                : <><Code2 size={16} /> Index</>}
            </button>
          </div>

          {/* Status Bar */}
          {ingestStatus !== 'idle' && (
            <div style={{
              ...styles.statusBar,
              borderColor: ingestStatus === 'ready' ? '#238636'
                : ingestStatus === 'error' ? '#da3633' : '#388bfd',
              background: ingestStatus === 'ready' ? '#0d2119'
                : ingestStatus === 'error' ? '#1b0000' : '#0d1b2e',
            }}>
              {ingestStatus === 'ready' && <CheckCircle2 size={16} color="#3fb950" />}
              {ingestStatus === 'error' && <AlertCircle size={16} color="#f85149" />}
              {(ingestStatus === 'loading' || ingestStatus === 'polling') &&
                <Loader2 size={16} color="#388bfd" style={{ animation: 'spin 1s linear infinite' }} />}
              <span style={{ fontSize: 13, color: '#c9d1d9' }}>{statusMsg}</span>
              {repoId && <code style={styles.repoIdBadge}>{repoId}</code>}
              {repoInfo?.indexed_chunks &&
                <span style={styles.badge}>{repoInfo.indexed_chunks} chunks • {repoInfo.file_count} files</span>}
            </div>
          )}
        </section>

        {/* Query Panel */}
        {ingestStatus === 'ready' && (
          <section style={styles.card}>
            <h2 style={styles.sectionTitle}><Search size={18} color="#58a6ff" /> Ask About the Code</h2>

            {/* Example queries */}
            <div style={styles.examples}>
              {EXAMPLE_QUERIES.map((eq, i) => (
                <button key={i} style={styles.exampleBtn} onClick={() => { setQuery(eq); handleQuery(eq); }}>
                  <Terminal size={12} />
                  {eq}
                </button>
              ))}
            </div>

            <div style={styles.inputRow}>
              <input
                style={styles.input}
                placeholder="Where is the authentication logic implemented?"
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleQuery()}
              />
              <button
                style={{ ...styles.btn, opacity: querying ? 0.6 : 1 }}
                onClick={() => handleQuery()}
                disabled={querying}
              >
                {querying
                  ? <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} />
                  : <><Search size={16} /> Search</>}
              </button>
            </div>
          </section>
        )}

        {/* Results */}
        {results.map((res, ri) => (
          <section key={res.ts} style={{ ...styles.card, borderColor: '#30363d' }}>
            <div style={styles.questionBadge}>
              <Search size={14} color="#58a6ff" />
              <strong style={{ color: '#e6edf3' }}>{res.question}</strong>
            </div>

            <div style={styles.markdownBody}>
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  code({ node, inline, className, children, ...props }) {
                    const match = /language-(\w+)/.exec(className || '');
                    return !inline && match ? (
                      <SyntaxHighlighter style={oneDark} language={match[1]} PreTag="div" {...props}>
                        {String(children).replace(/\n$/, '')}
                      </SyntaxHighlighter>
                    ) : (
                      <code style={styles.inlineCode} {...props}>{children}</code>
                    );
                  },
                }}
              >
                {res.answer}
              </ReactMarkdown>
            </div>

            {/* Code result cards */}
            {res.results?.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <h4 style={{ color: '#8b949e', fontSize: 12, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 }}>
                  Top Matches
                </h4>
                {res.results.slice(0, 6).map((r, i) => {
                  const key = `${ri}-${i}`;
                  return (
                    <div key={key} style={styles.resultCard}>
                      <div style={styles.resultHeader} onClick={() => toggleSnippet(key)}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1 }}>
                          <FileCode size={14} color="#58a6ff" />
                          <code style={styles.filePath}>{r.file_path}</code>
                          <span style={styles.linesBadge}>L{r.start_line}–{r.end_line}</span>
                          {r.symbol_name && (
                            <span style={styles.symbolBadge}>{r.symbol_name}</span>
                          )}
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <span style={styles.scoreBadge}>{(r.score * 100).toFixed(0)}%</span>
                          {expandedSnippets[key]
                            ? <ChevronDown size={14} color="#8b949e" />
                            : <ChevronRight size={14} color="#8b949e" />}
                        </div>
                      </div>
                      {expandedSnippets[key] && (
                        <SyntaxHighlighter
                          style={oneDark}
                          language={r.language?.replace('.', '') || 'text'}
                          showLineNumbers
                          startingLineNumber={r.start_line}
                          customStyle={{ margin: 0, borderRadius: '0 0 8px 8px', fontSize: 12 }}
                        >
                          {r.snippet}
                        </SyntaxHighlighter>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        ))}
      </main>

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        * { box-sizing: border-box; }
        ::-webkit-scrollbar { width: 6px; } 
        ::-webkit-scrollbar-track { background: #161b22; }
        ::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }
      `}</style>
    </div>
  );
}

const styles = {
  root: {
    minHeight: '100vh',
    background: '#0d1117',
    color: '#e6edf3',
    fontFamily: "'Space Grotesk', sans-serif",
  },
  header: {
    textAlign: 'center',
    padding: '48px 24px 24px',
    borderBottom: '1px solid #21262d',
  },
  logo: {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    gap: 10, marginBottom: 8,
  },
  logoText: {
    fontSize: 28, fontWeight: 700, color: '#e6edf3', letterSpacing: -1,
  },
  tagline: {
    color: '#8b949e', fontSize: 14, margin: 0,
  },
  main: {
    maxWidth: 860, margin: '0 auto', padding: '24px 16px',
    display: 'flex', flexDirection: 'column', gap: 20,
  },
  card: {
    background: '#161b22',
    border: '1px solid #30363d',
    borderRadius: 12,
    padding: 24,
  },
  sectionTitle: {
    display: 'flex', alignItems: 'center', gap: 8,
    fontSize: 16, fontWeight: 600, color: '#e6edf3', margin: '0 0 16px',
  },
  inputRow: {
    display: 'flex', gap: 10,
  },
  input: {
    flex: 1,
    background: '#0d1117',
    border: '1px solid #30363d',
    borderRadius: 8,
    color: '#e6edf3',
    fontSize: 14,
    padding: '10px 14px',
    fontFamily: "'JetBrains Mono', monospace",
    outline: 'none',
  },
  btn: {
    background: '#238636',
    color: '#fff',
    border: 'none',
    borderRadius: 8,
    padding: '10px 20px',
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    whiteSpace: 'nowrap',
  },
  statusBar: {
    marginTop: 12,
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '10px 14px',
    borderRadius: 8,
    border: '1px solid',
    flexWrap: 'wrap',
  },
  repoIdBadge: {
    background: '#0d1117',
    color: '#58a6ff',
    padding: '2px 8px',
    borderRadius: 4,
    fontSize: 12,
    fontFamily: "'JetBrains Mono', monospace",
  },
  badge: {
    background: '#21262d',
    color: '#8b949e',
    padding: '2px 8px',
    borderRadius: 4,
    fontSize: 12,
  },
  examples: {
    display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 14,
  },
  exampleBtn: {
    background: '#21262d',
    border: '1px solid #30363d',
    borderRadius: 6,
    color: '#8b949e',
    fontSize: 12,
    padding: '5px 10px',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    gap: 5,
    transition: 'all 0.15s',
  },
  questionBadge: {
    display: 'flex', alignItems: 'flex-start', gap: 8,
    marginBottom: 16,
    padding: '10px 14px',
    background: '#0d1b2e',
    borderRadius: 8,
    borderLeft: '3px solid #388bfd',
    fontSize: 14,
  },
  markdownBody: {
    fontSize: 14,
    lineHeight: 1.7,
    color: '#c9d1d9',
  },
  inlineCode: {
    background: '#21262d',
    padding: '2px 6px',
    borderRadius: 4,
    fontFamily: "'JetBrains Mono', monospace",
    fontSize: 12,
    color: '#f0883e',
  },
  resultCard: {
    border: '1px solid #30363d',
    borderRadius: 8,
    marginBottom: 8,
    overflow: 'hidden',
  },
  resultHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '10px 14px',
    background: '#21262d',
    cursor: 'pointer',
  },
  filePath: {
    fontSize: 12,
    color: '#58a6ff',
    fontFamily: "'JetBrains Mono', monospace",
  },
  linesBadge: {
    background: '#0d1117',
    color: '#8b949e',
    padding: '1px 6px',
    borderRadius: 4,
    fontSize: 11,
    fontFamily: "'JetBrains Mono', monospace",
  },
  symbolBadge: {
    background: '#1b2a1b',
    color: '#3fb950',
    padding: '1px 8px',
    borderRadius: 10,
    fontSize: 11,
  },
  scoreBadge: {
    background: '#1b2233',
    color: '#388bfd',
    padding: '1px 8px',
    borderRadius: 10,
    fontSize: 11,
    fontWeight: 600,
  },
};
