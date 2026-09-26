import { useEffect, useRef, useState } from 'react'
import mermaid from 'mermaid'
import { GitFork, Loader2, Maximize2, X } from 'lucide-react'

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

/**
 * Render a Mermaid diagram into *el*, making the resulting SVG fill the
 * container width while keeping its aspect ratio.
 */
async function renderGraph(el, graph, renderId, renderIdRef) {
  el.innerHTML = ''

  const sanitized = graph
    .replace(/\\n/g, ' ')
    .replace(/(\[[^\]]*)\n([^\]]*\])/g, '$1 $2')

  const svgId = `mermaid-graph-${renderId}-${Date.now()}`

  const { svg } = await mermaid.render(svgId, sanitized)
  if (renderIdRef.current !== renderId) return

  el.innerHTML = svg
  const svgEl = el.querySelector('svg')
  if (svgEl) {
    svgEl.style.width = '100%'
    svgEl.style.height = 'auto'
    svgEl.style.maxWidth = '100%'
  }
}

export default function ArchitectureGraph({ graph }) {
  const containerRef = useRef(null)
  const modalContainerRef = useRef(null)
  const renderIdRef = useRef(0)
  const modalRenderIdRef = useRef(0)
  const [fullscreen, setFullscreen] = useState(false)

  // Render into the inline card container
  useEffect(() => {
    if (!graph || !containerRef.current) return

    const id = ++renderIdRef.current
    renderGraph(containerRef.current, graph, id, renderIdRef).catch(err => {
      console.error('Mermaid render error (card)', err)
      if (containerRef.current) {
        containerRef.current.innerHTML =
          '<p class="text-xs text-slate-500 p-4 text-center">Unable to render architecture graph.</p>'
      }
    })
  }, [graph])

  // Render into the modal container whenever it opens
  useEffect(() => {
    if (!fullscreen || !graph || !modalContainerRef.current) return

    const id = ++modalRenderIdRef.current
    renderGraph(modalContainerRef.current, graph, id, modalRenderIdRef).catch(err => {
      console.error('Mermaid render error (modal)', err)
      if (modalContainerRef.current) {
        modalContainerRef.current.innerHTML =
          '<p class="text-xs text-slate-500 p-4 text-center">Unable to render architecture graph.</p>'
      }
    })
  }, [fullscreen, graph])

  // Close modal on Escape key
  useEffect(() => {
    if (!fullscreen) return
    const onKey = (e) => { if (e.key === 'Escape') setFullscreen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [fullscreen])

  return (
    <>
      {/* ------------------------------------------------------------------ */}
      {/* Inline card                                                          */}
      {/* ------------------------------------------------------------------ */}
      <div className="glass-card h-full flex flex-col">
        {/* Card Header */}
        <div className="flex items-center gap-2 mb-4">
          <div className="flex items-center justify-center w-7 h-7 rounded-md bg-indigo-500/20 border border-indigo-500/30">
            <GitFork size={14} className="text-indigo-400" />
          </div>
          <h2 className="text-sm font-semibold text-white tracking-wide">Architecture Graph</h2>

          <div className="ml-auto flex items-center gap-2">
            {graph && (
              <span className="text-xs text-emerald-400 border border-emerald-500/30 rounded px-2 py-0.5 bg-emerald-500/10">
                live
              </span>
            )}
            {graph && (
              <button
                onClick={() => setFullscreen(true)}
                title="Expand Diagram"
                className="flex items-center gap-1 text-xs text-slate-400 hover:text-white
                           border border-slate-700 hover:border-slate-500 rounded px-2 py-0.5
                           bg-slate-800/60 hover:bg-slate-700/60 transition-colors"
              >
                <Maximize2 size={11} />
                <span>Expand</span>
              </button>
            )}
          </div>
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

      {/* ------------------------------------------------------------------ */}
      {/* Fullscreen modal overlay                                             */}
      {/* ------------------------------------------------------------------ */}
      {fullscreen && (
        <div
          className="fixed inset-0 z-50 flex flex-col bg-[#07090f]/95 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-label="Architecture Graph — fullscreen"
        >
          {/* Modal header */}
          <div className="flex items-center gap-3 px-6 py-4 border-b border-white/10 shrink-0">
            <div className="flex items-center justify-center w-7 h-7 rounded-md bg-indigo-500/20 border border-indigo-500/30">
              <GitFork size={14} className="text-indigo-400" />
            </div>
            <h2 className="text-sm font-semibold text-white tracking-wide">Architecture Graph</h2>
            <span className="text-xs text-emerald-400 border border-emerald-500/30 rounded px-2 py-0.5 bg-emerald-500/10">
              live
            </span>
            <button
              onClick={() => setFullscreen(false)}
              title="Close (Esc)"
              className="ml-auto flex items-center gap-1.5 text-xs text-slate-400 hover:text-white
                         border border-slate-700 hover:border-slate-500 rounded px-2.5 py-1
                         bg-slate-800/60 hover:bg-slate-700/60 transition-colors"
            >
              <X size={12} />
              <span>Close</span>
            </button>
          </div>

          {/* Zoomable / scrollable graph area */}
          <div className="flex-1 overflow-auto p-6">
            <div
              ref={modalContainerRef}
              className="w-full min-h-full flex items-center justify-center"
            />
          </div>
        </div>
      )}
    </>
  )
}
