'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowUp, BookOpen, Check, ChevronDown, ChevronRight, CircleHelp, Copy, FileCheck2, FileText, History, LayoutDashboard, Loader2, MessageSquareText, PanelRight, Quote, Sparkles, ShieldCheck, ThumbsDown, ThumbsUp, Upload } from 'lucide-react'

const API_BASE = 'http://localhost:8000'
const exampleQueries = ['What is the assignment?', 'Summarize our data retention policy', 'What triggers an incident report?']
const emptyAnswer = { question: '', summary: '', detail: '', confidence: { score: 0, classification: 'No confidence yet', message: 'The evidence panel will populate after your first grounded query.' }, sources: [] }

const CITATION_RE = /\[([^\[\]]+?),\s*p\.\s*(\d+),\s*Score:\s*([\d.]+)\]/g
/* ---------- Inline text + citation rendering ---------- */
function renderBold(text, keyPrefix) {
  return text
    .split(/(\*\*[^*]+\*\*)/g)
    .filter(Boolean)
    .map((part, index) =>
      part.startsWith('**') && part.endsWith('**')
        ? <strong key={`${keyPrefix}-b${index}`}>{part.slice(2, -2)}</strong>
        : <span key={`${keyPrefix}-s${index}`}>{part}</span>,
    )
}

function Citation({ entry }) {
  return (
    <span className="citation" tabIndex={0}>
      <span className="citation-marker">{entry.n}</span>
      <span className="citation-pop" role="tooltip">
        <span className="citation-pop-title"><FileText className="size-3.5 shrink-0 text-accent" />{entry.title}</span>
        <span className="citation-pop-meta"><span>Page {entry.page}</span><span className="citation-chip-score">Score {entry.score.toFixed(2)}</span></span>
        {entry.excerpt && <span className="citation-pop-excerpt">“{entry.excerpt}”</span>}
      </span>
    </span>
  )
}

function renderInline(text, registry, keyPrefix) {
  const nodes = []
  let lastIndex = 0
  let match
  let i = 0
  CITATION_RE.lastIndex = 0
  while ((match = CITATION_RE.exec(text)) !== null) {
    if (match.index > lastIndex) nodes.push(...renderBold(text.slice(lastIndex, match.index), `${keyPrefix}-t${i}`))
    const key = `${match[1].trim()}||${match[2]}`
    const entry = registry.get(key)
    if (entry) nodes.push(<Citation key={`${keyPrefix}-c${i}`} entry={entry} />)
    lastIndex = match.index + match[0].length
    i += 1
  }
  if (lastIndex < text.length) nodes.push(...renderBold(text.slice(lastIndex), `${keyPrefix}-t${i}`))
  return nodes
}

function parseBlocks(text) {
  const blocks = []
  let paragraph = []
  let list = []
  const flushParagraph = () => { if (paragraph.length) { blocks.push({ type: 'p', text: paragraph.join(' ') }); paragraph = [] } }
  const flushList = () => { if (list.length) { blocks.push({ type: 'ul', items: [...list] }); list = [] } }
  for (const raw of (text || '').split('\n')) {
    const line = raw.trim()
    if (!line) { flushParagraph(); flushList(); continue }
    const heading = line.match(/^\*\*(.+?):?\*\*:?$/)
    const bullet = line.match(/^[*-]\s+(.*)/)
    if (heading) { flushParagraph(); flushList(); blocks.push({ type: 'h', text: heading[1] }); continue }
    if (bullet) { flushParagraph(); list.push(bullet[1]); continue }
    flushList(); paragraph.push(line)
  }
  flushParagraph(); flushList()
  return blocks
}

function AnswerProse({ text, registry }) {
  const blocks = useMemo(() => parseBlocks(text), [text])
  return (
    <div className="answer-prose">
      {blocks.map((block, index) => {
        if (block.type === 'h') return <h4 key={`h${index}`}>{renderInline(block.text, registry, `h${index}`)}</h4>
        if (block.type === 'ul') return <ul key={`u${index}`}>{block.items.map((item, j) => <li key={`u${index}-${j}`}>{renderInline(item, registry, `u${index}-${j}`)}</li>)}</ul>
        return <p key={`p${index}`}>{renderInline(block.text, registry, `p${index}`)}</p>
      })}
    </div>
  )
}

/* ---------- Shared UI ---------- */
function Ambient() {
  return (
    <div className="ambient" aria-hidden="true">
      <div className="ambient-grid" />
      <div className="ambient-orb ambient-orb-a" />
      <div className="ambient-orb ambient-orb-b" />
    </div>
  )
}
function Logo() { return <div className="flex items-center gap-3"><div className="grid size-9 place-items-center rounded-xl bg-gradient-to-br from-primary to-[oklch(0.4_0.09_240)] text-primary-foreground shadow-sm"><ShieldCheck className="size-5" /></div><div><p className="font-serif text-lg font-semibold leading-none tracking-tight text-ink">Stride</p><p className="mt-1 font-mono text-[9px] uppercase tracking-[0.2em] text-muted-foreground">compliance copilot</p></div></div> }
function NavItem({ icon: Icon, label, active, onClick }) { return <button onClick={onClick} className={`nav-item ${active ? 'nav-item-active' : ''}`} aria-current={active ? 'page' : undefined}><Icon className="size-4" /><span>{label}</span>{active && <span className="ml-auto size-1.5 rounded-full bg-accent-foreground/80" />}</button> }
function SourceCard({ source, expanded, onToggle }) { return <article className={`source-card ${expanded ? 'source-card-expanded' : ''}`}><button className="flex w-full items-start gap-3 text-left" onClick={onToggle} aria-expanded={expanded}><span className="source-number">{source.id}</span><span className="min-w-0 flex-1"><span className="flex items-center gap-2"><span className="truncate text-sm font-medium text-foreground">{source.title}</span><ChevronDown className={`size-3.5 shrink-0 text-muted-foreground transition-transform ${expanded ? 'rotate-180' : ''}`} /></span><span className="mt-2 flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-muted-foreground"><span className="rounded bg-secondary px-1.5 py-0.5">{source.type}</span><span>{source.updated}</span><strong className="text-accent">Score {Number(source.score || 0).toFixed(2)}</strong></span></span></button>{expanded && <p className="mt-4 border-t border-border pt-3 text-xs leading-5 text-muted-foreground animate-in">“{source.excerpt}”</p>}</article> }

/* ---------- Admin Dashboard ---------- */
function AdminDashboard({ onBack }) {
  const fileRef = useRef(null)
  const [data, setData] = useState({ stats: { documents_indexed: 0, last_indexed: 'N/A' }, documents: [] })
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [query, setQuery] = useState('')
  const [notice, setNotice] = useState('')
  const [hasUploaded, setHasUploaded] = useState(false) // <-- Add this new line

  async function loadDashboard() {
    try {
      const response = await fetch(`${API_BASE}/api/dashboard`)
      if (!response.ok) throw new Error('Dashboard unavailable')
      setData(await response.json())
    } catch {
      setNotice('Could not reach the local backend. Start FastAPI on port 8000 to load live data.')
    }
  }
  useEffect(() => { loadDashboard() }, [])

  const filtered = useMemo(() => (data.documents || []).filter((doc) => (doc.name || '').toLowerCase().includes(query.toLowerCase())), [data.documents, query])

  async function addFiles(files) {
    const pdfs = [...files].filter((file) => file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf'))
    if (!pdfs.length) { setNotice('Only PDF files can be added to the knowledge base.'); return }

    const formData = new FormData()
    pdfs.forEach((file) => formData.append('files', file))

    setUploading(true)
    setHasUploaded(true) // <-- Add this line to permanently show the card for this session
    setNotice('')

    try {
      const response = await fetch(`${API_BASE}/api/upload`, { method: 'POST', body: formData })
      if (!response.ok) throw new Error('Upload failed')
      const result = await response.json()
      setNotice(result.message || `${pdfs.length} PDF queued for indexing.`)
      await loadDashboard()
    } catch {
      setNotice('Upload failed. Confirm the backend is running and accepts PDF files.')
    } finally {
      setUploading(false)
    }
  }

  return (
    <main className="admin-shell">
      <Ambient />
      <header className="admin-topbar">
        <Logo />
        <div className="admin-top-actions">
          <span className="admin-badge"><span className="status-dot" /> Knowledge base</span>
          <button onClick={onBack} className="subtle-button"><MessageSquareText className="size-3.5" /> Return to Copilot</button>
        </div>
      </header>
      <div className="admin-content">
        <div className="admin-heading reveal">
          <div>
            <p className="eyebrow text-accent">Knowledge operations</p>
            <h1 className="mt-3 font-serif text-4xl tracking-tight text-ink md:text-5xl">Dashboard.</h1>
            <p className="mt-4 max-w-xl text-sm leading-6 text-muted-foreground">Curate the source material behind your organization&apos;s compliance intelligence.</p>
          </div>
          <div className="admin-avatar">KB</div>
        </div>
        <div className="admin-stats">
          <div className="stat-card reveal" style={{ animationDelay: '60ms' }}><span className="eyebrow">Documents indexed</span><strong>{data.stats?.documents_indexed ?? 0}</strong><span className="stat-meta"><FileCheck2 className="size-3.5 text-accent" /> Live from backend</span></div>
          <div className="stat-card reveal" style={{ animationDelay: '120ms' }}><span className="eyebrow">Last indexed</span><strong>{data.stats?.last_indexed || 'N/A'}</strong><span className="stat-meta"><Check className="size-3.5 text-accent" /> Registry status</span></div>
          <div className="stat-card reveal" style={{ animationDelay: '180ms' }}><span className="eyebrow">Supported format</span><strong>PDF</strong><span className="stat-meta"><BookOpen className="size-3.5 text-accent" /> Text extraction ready</span></div>
        </div>
        <section className="upload-card reveal" style={{ animationDelay: '240ms' }}>
          <div>
            <p className="eyebrow text-accent">Add source material</p>
            <h2 className="mt-3 font-serif text-2xl tracking-tight text-ink">Upload policy documents.</h2>
            <p className="mt-3 max-w-lg text-sm leading-6 text-muted-foreground">Select or drop PDFs to add them to the knowledge base used by Copilot answers.</p>
            <div className={`dropzone mt-6 ${dragging ? 'dropzone-active' : ''}`} onDragOver={(event) => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); addFiles(event.dataTransfer.files) }}>
              <div className="grid size-12 place-items-center rounded-2xl bg-accent-soft text-accent"><Upload className="size-6" /></div>
              <p className="mt-3 text-sm font-medium text-foreground">Drop PDFs here</p>
              <p className="mt-1 text-xs text-muted-foreground">or choose files from your computer</p>
              <button className="action-button mt-5" onClick={() => fileRef.current?.click()} disabled={uploading}>{uploading ? <><Loader2 className="size-4 animate-spin" /> Uploading...</> : <><Upload className="size-4" /> Select PDFs</>}</button>
              <input ref={fileRef} type="file" accept="application/pdf,.pdf" multiple className="sr-only" onChange={(event) => addFiles(event.target.files)} />
            </div>
            {notice && <p className="mt-4 text-xs text-muted-foreground">{notice}</p>}
          </div>
          {hasUploaded && (
            <div className="pipeline-card animate-in">
              <p className="eyebrow">Ingestion pipeline</p>
              <div className="pipeline-step">
                {/* Step 1 is always active once the card appears */}
                <span className="pipeline-dot pipeline-dot-active" />
                <div><strong>Upload received</strong><p>Files are registered by the API.</p></div>
              </div>
              <div className="pipeline-step">
                {/* Step 2 pulses while uploading, stays solid when done */}
                <span className={`pipeline-dot ${uploading ? 'pipeline-dot-active animate-pulse' : 'pipeline-dot-active'}`} />
                <div><strong>Chunk & embed</strong><p>Pending files are processed asynchronously.</p></div>
              </div>
              <div className="pipeline-step">
                {/* Step 3 lights up only when the upload process is completely finished */}
                <span className={`pipeline-dot ${!uploading ? 'pipeline-dot-active bg-accent' : ''}`} />
                <div><strong>Available to Copilot</strong><p>Indexed chunks become searchable.</p></div>
              </div>
            </div>
          )}
        </section>
        <section className="documents-section reveal" style={{ animationDelay: '300ms' }}>
          <div className="documents-heading">
            <div><p className="eyebrow text-accent">Source registry</p><h2 className="mt-2 font-serif text-2xl tracking-tight text-ink">Knowledge base files.</h2></div>
            <label className="search-field"><span className="sr-only">Search documents</span><FileText className="size-4" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search documents" /></label>
          </div>
          <div className="document-list">
            {filtered.length ? filtered.map((doc) => (
              <div className="document-row" key={`${doc.name}-${doc.date}`}>
                <div className="document-icon"><FileText className="size-4" /></div>
                <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium text-foreground">{doc.name}</p><p className="mt-1 text-xs text-muted-foreground">{doc.size} · {doc.date}</p></div>
                <span className={`status-pill ${doc.status === 'completed' || doc.status === 'Indexed' ? 'status-pill-ready' : ''}`}>{doc.status}</span>
              </div>
            )) : <div className="empty-documents"><FileText className="size-5" /><p>No documents found.</p></div>}
          </div>
        </section>
      </div>
    </main>
  )
}

/* ---------- Copilot ---------- */
export default function Page() {
  const [dashboard, setDashboard] = useState(false)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState(emptyAnswer)
  const [isLoading, setIsLoading] = useState(false)
  const [activeNav, setActiveNav] = useState('Ask Copilot')
  const [expandedSource, setExpandedSource] = useState(null)
  const [sourcesOpen, setSourcesOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const [feedback, setFeedback] = useState(null)
  const [error, setError] = useState('')
  const [history, setHistory] = useState([]) // <-- Add this new state

  async function loadHistory() {
    try {
      // Added { cache: 'no-store' } to completely bypass the browser's aggressive caching
      const res = await fetch(`${API_BASE}/api/history`, { cache: 'no-store' })
      if (res.ok) setHistory(await res.json())
    } catch (e) {
      console.error("Could not load history", e)
    }
  }

  // Load history when the page first opens
  useEffect(() => {
    loadHistory()
  }, [])

  async function ask(nextQuestion = question) {
    if (!nextQuestion.trim() || isLoading) return
    setQuestion(nextQuestion)
    setIsLoading(true)
    setError('')
    setFeedback(null)
    try {
      const response = await fetch(`${API_BASE}/api/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query: nextQuestion.trim() }) })
      if (!response.ok) throw new Error('Chat request failed')
      const result = await response.json()
      setAnswer(result)
      setExpandedSource(result.sources?.[0]?.id || null)
      await loadHistory()
    } catch {
      setError('Unable to connect to the local backend. Start FastAPI on port 8000 and try again.')
    } finally {
      setIsLoading(false)
    }
  }

  function copyAnswer() {
    navigator.clipboard?.writeText(`${answer.summary}\n\n${answer.detail}`)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1600)
  }

  const registry = useMemo(() => {
    const map = new Map()
    const sources = answer.sources || []
    const text = `${answer.summary || ''}\n${answer.detail || ''}`
    let match
    let n = 0
    CITATION_RE.lastIndex = 0
    while ((match = CITATION_RE.exec(text)) !== null) {
      const title = match[1].trim()
      const page = match[2]
      const score = Number.parseFloat(match[3])
      const key = `${title}||${page}`
      if (!map.has(key)) {
        n += 1
        const src = sources.find((s) => Math.abs((s.score || 0) - score) < 0.01) || sources.find((s) => (s.title || '') === title)
        map.set(key, { n, title, page, score, excerpt: src?.excerpt || '' })
      }
    }
    return map
  }, [answer])

  const hasAnswer = Boolean(answer.question || answer.summary)

  if (dashboard) return <AdminDashboard onBack={() => { setDashboard(false); setActiveNav('Ask Copilot') }} />

  return (
    <main className="app-shell">
      <Ambient />
      <aside className="sidebar">
        <div className="sidebar-top"><Logo /></div>
        <div className="workspace-switcher">
          <div className="workspace-mark">A</div>
          <div className="min-w-0 flex-1 text-left"><p className="truncate text-xs font-medium text-foreground">Copilot Corporation</p><p className="mt-0.5 truncate text-[10px] text-muted-foreground">Trust &amp; Safety workspace</p></div>
          <ChevronDown className="size-3.5 text-muted-foreground" />
        </div>
        <nav className="mt-7 flex flex-col gap-1" aria-label="Workspace navigation">
          <NavItem icon={MessageSquareText} label="Ask Copilot" active={activeNav === 'Ask Copilot'} onClick={() => setActiveNav('Ask Copilot')} />
          <NavItem icon={LayoutDashboard} label="Dashboard" active={activeNav === 'Dashboard'} onClick={() => { setActiveNav('Dashboard'); setDashboard(true) }} />
        </nav>
        <div className="mt-9 flex flex-col flex-1 min-h-0">
          <p className="eyebrow px-3">Recent questions</p>
          
          {/* Scrollable container restricted to the sidebar bounds */}
          <div className="mt-3 relative scroll-fade-container flex-1 min-h-0">
            <div className="flex flex-col gap-1 overflow-y-auto h-full no-scrollbar pr-1">
              {history.length ? history.map((item) => (
                <button 
                  key={item.id} 
                  className="recent-item text-left w-full shrink-0" 
                  onClick={() => { 
                    setActiveNav('Ask Copilot')
                    setQuestion(item.query)
                    setAnswer(item.response) 
                    setExpandedSource(item.response.sources?.[0]?.id || null)
                  }}
                >
                  <History className="size-3.5 shrink-0" />
                  <span className="truncate">{item.query}</span>
                </button>
              )) : (
                 <p className="px-3 text-xs text-muted-foreground">No history yet.</p>
              )}
            </div>
          </div>
        </div>
        <div className="mt-auto flex flex-col gap-5">
          <button className="help-link"><CircleHelp className="size-4" /> Help center</button>
          <div className="profile-card"><div className="profile-avatar">JD</div><div className="min-w-0 flex-1"><p className="truncate text-xs font-medium text-foreground">Sarthak Sanjeev</p><p className="mt-0.5 truncate text-[10px] text-muted-foreground">Compliance lead</p></div><ChevronRight className="size-3.5 text-muted-foreground" /></div>
        </div>
      </aside>

      <div className="main-column">
        <header className="topbar">
          <div className="breadcrumbs"><span>Workspace</span><ChevronRight className="size-3" /><strong>Ask Copilot</strong></div>
          <div className="flex items-center gap-2">
            <span className="topbar-actions"><span className="status-dot" /><span>Sources synced</span></span>
            <button className="icon-button lg:hidden" onClick={() => setSourcesOpen((prev) => !prev)} aria-label="Toggle evidence panel"><PanelRight className="size-4" /></button>
          </div>
        </header>

        <div className="content-wrap">
          <section className="hero-section reveal">
            <span className="hero-badge"><Sparkles className="size-3" /> Grounded intelligence</span>
            <h1 className="hero-title">Ask with <em>confidence.</em></h1>
            <p className="hero-sub">Get precise answers grounded in your organization&apos;s policies, standards, and contracts — every claim traced back to its source.</p>

            <div className="composer reveal" style={{ animationDelay: '80ms' }}>
              <div className="composer-inner">
                <label htmlFor="copilot-question" className="composer-label"><span className="dot" /> Ask a policy question</label>
                <textarea
                  id="copilot-question"
                  className="question-input"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) { event.preventDefault(); ask() } }}
                  placeholder="e.g. What is our data retention period for customer records?"
                  rows={3}
                />
                <div className="composer-footer">
                  <span className="composer-hint"><kbd>Enter</kbd> to submit · <kbd>Shift</kbd>+<kbd>Enter</kbd> for new line</span>
                  <button className="submit-button" onClick={() => ask()} disabled={isLoading || !question.trim()}>{isLoading ? <><Loader2 className="size-4 animate-spin" /> Searching</> : <>Ask Copilot <ArrowUp className="size-4" /></>}</button>
                </div>
              </div>
            </div>

            <div className="examples-row">
              <span className="eyebrow">Try</span>
              {exampleQueries.map((item, index) => (
                <button key={item} className="example-chip reveal" style={{ animationDelay: `${140 + index * 60}ms` }} onClick={() => ask(item)}><MessageSquareText className="size-3" /> {item}</button>
              ))}
            </div>

            {error && <p className="mt-5 rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive animate-in">{error}</p>}
          </section>

          <section className="answer-section">
            <div className="section-label">
              <span className="eyebrow">Latest answer</span>
              <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">{hasAnswer ? 'Grounded · just now' : 'Waiting for query'}</span>
            </div>

            {isLoading ? (
              <div className="answer-card">
                <div className="answer-mark"><Loader2 className="size-4 animate-spin" /></div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-col gap-3">
                    <div className="shimmer h-4 w-3/4 rounded" />
                    <div className="shimmer h-4 w-full rounded" />
                    <div className="shimmer h-4 w-5/6 rounded" />
                    <div className="shimmer h-4 w-2/3 rounded" />
                  </div>
                </div>
              </div>
            ) : hasAnswer ? (
              <article className="answer-card reveal">
                <div className="answer-mark"><ShieldCheck className="size-4" /></div>
                <div className="min-w-0 flex-1">
                  {answer.question && <p className="answer-question">{answer.question}</p>}
                  <AnswerProse text={answer.summary} registry={registry} />
                  {answer.detail && <AnswerProse text={answer.detail} registry={registry} />}
                  <div className="answer-footer">
                    <div className="flex items-center gap-1">
                      <button className={`icon-button ${feedback === 'up' ? 'icon-button-active' : ''}`} onClick={() => setFeedback('up')} aria-label="Helpful"><ThumbsUp className="size-3.5" /></button>
                      <button className={`icon-button ${feedback === 'down' ? 'icon-button-active' : ''}`} onClick={() => setFeedback('down')} aria-label="Not helpful"><ThumbsDown className="size-3.5" /></button>
                      <span className="ml-2 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">{registry.size} citation{registry.size === 1 ? '' : 's'}</span>
                    </div>
                    <button className="copy-button" onClick={copyAnswer}>{copied ? <Check className="size-3.5 text-accent" /> : <Copy className="size-3.5" />}{copied ? 'Copied' : 'Copy answer'}</button>
                  </div>
                </div>
              </article>
            ) : (
              <div className="answer-empty reveal">
                <div className="answer-empty-mark"><Quote className="size-5" /></div>
                <p className="font-serif text-lg tracking-tight text-ink">Your grounded answer will appear here.</p>
                <p className="max-w-sm text-sm leading-6 text-muted-foreground">Ask a question above and Copilot will respond with inline citations you can hover to inspect the exact source passage.</p>
              </div>
            )}
          </section>
        </div>
      </div>

      <aside className={`evidence-panel ${sourcesOpen ? '' : 'evidence-panel-collapsed'}`}>
        <div className="evidence-header">
          <div><p className="eyebrow text-accent">Evidence</p><h2 className="mt-2 font-serif text-xl tracking-tight text-ink">Why this answer?</h2></div>
          <button className="icon-button lg:hidden" onClick={() => setSourcesOpen(false)} aria-label="Collapse evidence"><PanelRight className="size-4" /></button>
        </div>
        <div className="confidence-card">
          {/* Primary Confidence Score */}
          <div className="flex items-end justify-between">
            <span className="eyebrow">Confidence</span>
            <strong className="font-serif text-3xl tracking-tight text-ink">{Math.round(answer.confidence?.score || 0)}%</strong>
          </div>
          <div className="confidence-bar mt-4">
            <span style={{ width: `${Math.min(100, answer.confidence?.score || 0)}%` }} />
          </div>
          <div className="mt-3 flex items-start gap-2">
            <Check className="mt-0.5 size-3.5 shrink-0 text-accent" />
            <div>
              <p className="text-xs font-medium text-foreground">{answer.confidence?.classification}</p>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">{answer.confidence?.message}</p>
            </div>
          </div>

          {/* Secondary Citation Accuracy Score */}
          {answer.citation_accuracy !== undefined && (
            <div className="mt-6 border-t border-border pt-5 animate-in">
              <div className="flex items-end justify-between">
                <span className="eyebrow text-muted-foreground">Citation Accuracy</span>
                <strong className="font-mono text-sm tracking-tight text-ink">{answer.citation_accuracy}%</strong>
              </div>
              <div className="confidence-bar mt-2 h-1 bg-secondary/60">
                <span style={{ width: `${Math.min(100, answer.citation_accuracy)}%`, opacity: 0.85 }} />
              </div>
              <p className="mt-2 text-[10px] leading-4 text-muted-foreground">
                Verified against retrieved chunks
              </p>
            </div>
          )}
        </div>
        <div className="mt-7 flex flex-col flex-1 min-h-0">
          <div className="flex items-center justify-between shrink-0"><p className="eyebrow">Source chunks</p><span className="font-mono text-[10px] text-muted-foreground">{answer.sources?.length || 0} found</span></div>
          
          <div className="mt-3 flex flex-col gap-2 overflow-y-auto h-full no-scrollbar pr-1 pb-6">
            {answer.sources?.length ? answer.sources.map((source) => <SourceCard key={source.id} source={source} expanded={expandedSource === source.id} onToggle={() => setExpandedSource(expandedSource === source.id ? null : source.id)} />) : <p className="text-xs leading-5 text-muted-foreground">Run a query to inspect retrieved source chunks and scores.</p>}
          </div>
        </div>
      </aside>

      {!sourcesOpen && <button className="sources-reopen" onClick={() => setSourcesOpen(true)}><PanelRight className="size-4" /> Evidence</button>}
    </main>
  )
}
