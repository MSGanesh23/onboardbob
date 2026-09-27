import { useState, useRef } from 'react'
import axios from 'axios'
import Header from './components/Header'
import ArchitectureGraph from './components/ArchitectureGraph'
import DocDriftCard from './components/DocDriftCard'
import OnboardingChecklist from './components/OnboardingChecklist'
import IssueNavigator from './components/IssueNavigator'

// ---------------------------------------------------------------------------
// Mock data used when the backend is not available (development mode)
// ---------------------------------------------------------------------------
const MOCK_GRAPH = `flowchart TD
    A[main.py\\nEntry Point] --> B[FastAPI App]
    B --> C[/api/scan-repo\\nRouter]
    B --> D[/api/issue\\nRouter]
    C --> E[RepoScanner\\nService]
    D --> F[GitHubClient\\nService]
    E --> G[(File System)]
    F --> H[(GitHub API)]
    E --> I[DocAnalyzer\\nModule]
    I --> J[DriftScorer]
    style A fill:#6d28d9,color:#fff
    style B fill:#1e293b,color:#e2e8f0
    style C fill:#1e1b4b,color:#a78bfa
    style D fill:#164e63,color:#67e8f9
    style E fill:#1e293b,color:#e2e8f0
    style F fill:#1e293b,color:#e2e8f0
    style I fill:#1e293b,color:#e2e8f0
    style J fill:#7c2d12,color:#fde68a`

const MOCK_DATA = {
  graph: MOCK_GRAPH,
  driftScore: 42,
  missingDocs: [
    'src/services/repo_scanner.py::scan_directory()',
    'src/models/code_graph.py::CodeNode.__repr__()',
    'src/utils/file_helpers.py::normalize_path()',
  ],
  entryPoints: [
    { name: 'main.py', type: 'entrypoint', checked: true },
    { name: 'src/routers/scan.py', type: 'router', checked: true },
    { name: 'src/routers/issue.py', type: 'router', checked: true },
    { name: 'src/models/code_graph.py', type: 'model', checked: false },
    { name: 'src/models/doc_drift.py', type: 'model', checked: false },
  ],
  tourSteps: [
    'Start with main.py to understand the FastAPI bootstrap and middleware.',
    'Explore src/routers/ — scan.py handles repository ingestion, issue.py fetches GitHub specs.',
    'Read src/services/repo_scanner.py to understand how file trees are parsed.',
    'Study src/models/ to learn the data schemas passed between layers.',
    'Review src/services/doc_analyzer.py to see how drift scores are calculated.',
  ],
  issue: {
    number: 42,
    url: 'https://github.com/example/onboardbob/issues/42',
    title: 'Improve drift scorer to handle nested class methods',
    body: 'The current DocAnalyzer only checks top-level functions for missing docstrings. '
      + 'Nested methods inside classes are silently skipped, causing the drift score to be '
      + 'underreported. We should recurse into class bodies and add missing entries to the '
      + 'alerts list.',
  },
  impactedFiles: [
    'src/services/doc_analyzer.py',
    'src/models/doc_drift.py',
    'tests/test_doc_analyzer.py',
  ],
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------
const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export default function App() {
  const _lastRepoName = useRef(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const [graph, setGraph] = useState(null)
  const [svgImage, setSvgImage] = useState(null)
  const [aiSummary, setAiSummary] = useState(null)
  const [driftScore, setDriftScore] = useState(null)
  const [missingDocs, setMissingDocs] = useState(null)
  const [setupGuide, setSetupGuide] = useState(null)
  const [entryPoints, setEntryPoints] = useState(null)
  const [tourSteps, setTourSteps] = useState(null)
  const [issue, setIssue] = useState(null)
  const [impactedFiles, setImpactedFiles] = useState(null)
  const [fixResult, setFixResult] = useState(null)

  const handleScan = async ({ repoUrl, issueUrl }) => {
    setLoading(true)
    setError(null)

    try {
      // Step 1: Clone the repo
      const cloneRes = await axios.post(`${API_BASE}/api/clone-repo`, {
        repo_url: repoUrl,
        issue_url: issueUrl,
      })
      const repo_name   = cloneRes.data.repo_name
      _lastRepoName.current = repo_name
      const issueData   = cloneRes.data.issue ?? null
      const issueTitleV = issueData?.title ?? ''
      const issueBodyV  = issueData?.body  ?? ''

      // Step 2: Scan the repo for the architecture graph
      const scanRes = await axios.post(`${API_BASE}/api/scan-repo`, { repo_name })
      const scanData = scanRes.data

      // Step 3: Get doc drift score, missing docstrings, and Gemini AI features
      const driftRes = await axios.post(`${API_BASE}/api/doc-drift`, {
        repo_name,
        issue_title: issueTitleV,
        issue_body: issueBodyV,
      })
      const driftData = driftRes.data

      setGraph(scanData.graph ?? scanData.mermaid ?? null)
      setSvgImage(scanData.svg_image ?? null)
      // Prefer top-level ai_summary from scan, fall back to drift report
      setAiSummary(
        scanData.ai_summary || driftData.ai_summary || null
      )
      setDriftScore(driftData.drift_score ?? driftData.driftScore ?? null)
      setMissingDocs(driftData.missing_docstrings ?? driftData.missing_docs ?? driftData.missingDocs ?? [])
      setSetupGuide(driftData.ai_setup_guide ?? [])
      // Prefer top-level response fields, then knowledge_graph sub-keys
      setEntryPoints(scanData.entry_points ?? (scanData.knowledge_graph ?? {}).entry_points ?? null)
      setTourSteps(scanData.tour_steps ?? (scanData.knowledge_graph ?? {}).tour_steps ?? null)

      if (issueData) {
        setIssue(issueData)
        setImpactedFiles(cloneRes.data.impacted_files ?? cloneRes.data.impactedFiles ?? [])
      }
      // Clear any previous fix result on new scan
      setFixResult(null)
    } catch (err) {
      const message =
        err.response?.data?.detail ?? err.response?.data?.message ?? err.message ?? 'Unknown error'
      setError(`Backend error: ${message}`)
    } finally {
      setLoading(false)
    }
  }

  const handleExecuteFix = async () => {
    if (!issue) return
    // repo_name is the last path segment of the issue URL's repo, or derive from state
    // We stored it in a ref-free way: re-derive from the last clone response.
    // Since we don't store repo_name in state, pass it via closure using a ref.
    const repoName = _lastRepoName.current
    if (!repoName) return
    const res = await axios.post(`${API_BASE}/api/execute-fix`, {
      repo_name: repoName,
      issue_title: issue?.title ?? '',
      issue_body: issue?.body ?? '',
    })
    setFixResult(res.data)
  }

  return (
    <div className="min-h-screen bg-[#0a0f1e] text-white flex flex-col">
      {/* Ambient glow blobs */}
      <div
        aria-hidden
        className="pointer-events-none fixed top-0 left-1/4 w-[600px] h-[600px] rounded-full
                   bg-violet-900/20 blur-[120px] -translate-y-1/2"
      />
      <div
        aria-hidden
        className="pointer-events-none fixed bottom-0 right-1/4 w-[500px] h-[500px] rounded-full
                   bg-cyan-900/15 blur-[100px] translate-y-1/2"
      />

      {/* Header */}
      <Header onScan={handleScan} loading={loading} />

      {/* Error banner */}
      {error && (
        <div className="max-w-[1400px] mx-auto w-full px-7 mt-5">
          <div className="text-base text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-5 py-3">
            ⚠ {error}
          </div>
        </div>
      )}


      {/* Dashboard — 4-section vertical layout */}
      <main className="flex-1 max-w-[1400px] mx-auto w-full px-7 py-7 space-y-6">
        {/* Section 1 (Top Center): Architecture Graph — centered full-width */}
        <div className="w-full min-h-[440px]">
          <ArchitectureGraph graph={graph} svgImage={svgImage} />
        </div>

        {/* Section 2 (Middle): AI Onboarding Plan & Project Setup Guide */}
        <div className="w-full min-h-[340px]">
          <OnboardingChecklist
            entryPoints={entryPoints}
            tourSteps={tourSteps}
            aiSummary={aiSummary}
            setupGuide={setupGuide}
          />
        </div>

        {/* Section 3 (Lower Middle): Documentation Drift Health */}
        <div className="w-full min-h-[380px]">
          <DocDriftCard driftScore={driftScore} missingDocs={missingDocs} />
        </div>

        {/* Section 4 (Bottom): GitHub Issue Spec, Impacted Files, Execute Fix */}
        <div className="w-full min-h-[300px]">
          <IssueNavigator
            issue={issue}
            impactedFiles={impactedFiles}
            onExecuteFix={handleExecuteFix}
            fixResult={fixResult}
          />
        </div>
      </main>

      {/* Footer */}
      <footer className="text-center text-sm text-slate-700 py-5 border-t border-white/5">
        OnboardBob Dashboard • Built with React + Vite + Tailwind CSS
      </footer>
    </div>
  )
}
