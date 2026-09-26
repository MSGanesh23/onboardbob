import { useEffect, useRef } from 'react'
import mermaid from 'mermaid'
import { GitFork, Loader2 } from 'lucide-react'

mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  darkMode: true,
  themeVariables: {
    background: 'transparent',
    primaryColor: '#6d28d9',
    primaryTextColor: '#e2e8f0',
    primaryBorderColor: '#7c3aed',
    lineColor: '#64748b',
    secondaryColor: '#1e293b',
    tertiaryColor: '#0f172a',
    edgeLabelBackground: '#1e293b',
    clusterBkg: '#1e1b4b',
    titleColor: '#a78bfa',
    nodeTextColor: '#e2e8f0',
  },
})

export default function ArchitectureGraph({ graph }) {
  const containerRef = useRef(null)
  const renderIdRef = useRef(0)

  useEffect(() => {
    if (!graph || !containerRef.current) return

    const id = ++renderIdRef.current
    const el = containerRef.current
    el.innerHTML = ''

    const svgId = `mermaid-graph-${id}-${Date.now()}`

    mermaid
      .render(svgId, graph)
      .then(({ svg }) => {
        if (renderIdRef.current !== id) return
        el.innerHTML = svg
        // Make SVG responsive
        const svgEl = el.querySelector('svg')
        if (svgEl) {
          svgEl.style.width = '100%'
          svgEl.style.height = 'auto'
          svgEl.style.maxWidth = '100%'
        }
      })
      .catch(err => {
        console.error('Mermaid render error', err)
        el.innerHTML = `<pre class="text-red-400 text-xs p-4 overflow-auto">${graph}</pre>`
      })
  }, [graph])

  return (
    <div className="glass-card h-full flex flex-col">
      {/* Card Header */}
      <div className="flex items-center gap-2 mb-4">
        <div className="flex items-center justify-center w-7 h-7 rounded-md bg-indigo-500/20 border border-indigo-500/30">
          <GitFork size={14} className="text-indigo-400" />
        </div>
        <h2 className="text-sm font-semibold text-white tracking-wide">Architecture Graph</h2>
        {graph && (
          <span className="ml-auto text-xs text-emerald-400 border border-emerald-500/30 rounded px-2 py-0.5 bg-emerald-500/10">
            live
          </span>
        )}
      </div>

      {/* Graph area */}
      <div className="flex-1 min-h-0 flex items-center justify-center">
        {!graph ? (
          <div className="flex flex-col items-center gap-3 text-slate-600">
            <GitFork size={40} strokeWidth={1} />
            <p className="text-xs text-center">
              Scan a repository to visualize<br />its architecture flowchart
            </p>
          </div>
        ) : (
          <div
            ref={containerRef}
            className="w-full overflow-auto"
          />
        )}
      </div>

      {/* Loading overlay when graph is set but ref hasn't rendered yet */}
      {graph && !containerRef.current?.innerHTML && (
        <div className="absolute inset-0 flex items-center justify-center">
          <Loader2 size={24} className="text-indigo-400 animate-spin" />
        </div>
      )}
    </div>
  )
}
