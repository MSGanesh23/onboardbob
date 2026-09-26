import { useState } from 'react'
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
export default function App() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const [graph, setGraph] = useState(null)
  const [driftScore, setDriftScore] = useState(null)
  const [missingDocs, setMissingDocs] = useState(null)
  const [entryPoints, setEntryPoints] = useState(null)
  const [tourSteps, setTourSteps] = useState(null)
  const [issue, setIssue] = useState(null)
  const [impactedFiles, setImpactedFiles] = useState(null)

  const handleScan = async ({ repoUrl, issueUrl }) => {
    setLoading(true)
    setError(null)

    try {
      // Try real backend first; fall back to mock if it's unreachable
      let scanData, issueData

      try {
        const [scanRes, issueRes] = await Promise.all([
          axios.post('/api/scan-repo', { repo_url: repoUrl }, { timeout: 15000 }),
          issueUrl
            ? axios.post('/api/issue', { issue_url: issueUrl }, { timeout: 10000 })
            : Promise.resolve(null),
        ])
        scanData = scanRes.data
        issueData = issueRes?.data
      } catch {
        // Backend not available — use mock data for demo purposes
        scanData = MOCK_DATA
        issueData = issueUrl ? MOCK_DATA : null
      }

      setGraph(scanData.graph ?? MOCK_GRAPH)
      setDriftScore(scanData.driftScore ?? scanData.drift_score ?? MOCK_DATA.driftScore)
      setMissingDocs(scanData.missingDocs ?? scanData.missing_docs ?? MOCK_DATA.missingDocs)
      setEntryPoints(scanData.entryPoints ?? scanData.entry_points ?? MOCK_DATA.entryPoints)
      setTourSteps(scanData.tourSteps ?? scanData.tour_steps ?? MOCK_DATA.tourSteps)

      if (issueData) {
        setIssue(issueData.issue ?? MOCK_DATA.issue)
        setImpactedFiles(issueData.impactedFiles ?? issueData.impacted_files ?? MOCK_DATA.impactedFiles)
      }
    } catch (err) {
      setError(err.message ?? 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  const handleExecuteFix = async () => {
    // In a real setup this would POST to /api/execute-fix
    await new Promise(r => setTimeout(r, 1800))
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
        <div className="max-w-7xl mx-auto w-full px-6 mt-4">
          <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-2.5">
            ⚠ {error}
          </div>
        </div>
      )}

      {/* Dashboard grid */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-6 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 h-full">
          {/* Architecture Graph — spans 2 columns */}
          <div className="lg:col-span-2 min-h-[420px]">
            <ArchitectureGraph graph={graph} />
          </div>

          {/* Doc Drift */}
          <div className="min-h-[420px]">
            <DocDriftCard driftScore={driftScore} missingDocs={missingDocs} />
          </div>

          {/* Onboarding Checklist */}
          <div className="lg:col-span-2 min-h-[320px]">
            <OnboardingChecklist entryPoints={entryPoints} tourSteps={tourSteps} />
          </div>

          {/* Issue Navigator */}
          <div className="min-h-[320px]">
            <IssueNavigator
              issue={issue}
              impactedFiles={impactedFiles}
              onExecuteFix={handleExecuteFix}
            />
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="text-center text-[11px] text-slate-700 py-4 border-t border-white/5">
        OnboardBob Dashboard • Built with React + Vite + Tailwind CSS
      </footer>
    </div>
  )
}
