import { useEffect, useRef, useState } from 'react'
import mermaid from 'mermaid'
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch'
import { GitFork, Loader2, Maximize2, X, ZoomIn, ZoomOut, RotateCcw, ExternalLink } from 'lucide-react'

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

/**
 * Open a new browser tab showing the SVG image at full resolution.
 */
function openSvgInNewTab(svgString) {
  const blob = new Blob([svgString], { type: 'image/svg+xml' })
  const url  = URL.createObjectURL(blob)
  window.open(url, '_blank', 'noopener,noreferrer')
  // Revoke after a short delay to allow the tab to load the image
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

export default function ArchitectureGraph({ graph, svgImage }) {
  const containerRef      = useRef(null)
  const modalContainerRef = useRef(null)
  const renderIdRef       = useRef(0)
  const modalRenderIdRef  = useRef(0)
  const [fullscreen, setFullscreen] = useState(false)

  // Determine display mode: prefer SVG image when available
  const hasSvg     = Boolean(svgImage && svgImage.trim().startsWith('<svg'))
  const hasMermaid = Boolean(graph)

  // Render Mermaid into the inline card container (only when no SVG available)
  useEffect(() => {
    if (hasSvg || !hasMermaid || !containerRef.current) return

    const id = ++renderIdRef.current
    renderGraph(containerRef.current, graph, id, renderIdRef).catch(err => {
      console.error('Mermaid render error (card)', err)
      if (containerRef.current) {
        containerRef.current.innerHTML =
          '<p class="text-xs text-slate-500 p-4 text-center">Unable to render architecture graph.</p>'
      }
    })
  }, [graph, hasSvg, hasMermaid])

  // Render into the modal container whenever it opens (Mermaid fallback mode)
  useEffect(() => {
    if (!fullscreen || hasSvg || !hasMermaid || !modalContainerRef.current) return

    const id = ++modalRenderIdRef.current
    renderGraph(modalContainerRef.current, graph, id, modalRenderIdRef).catch(err => {
      console.error('Mermaid render error (modal)', err)
      if (modalContainerRef.current) {
        modalContainerRef.current.innerHTML =
          '<p class="text-xs text-slate-500 p-4 text-center">Unable to render architecture graph.</p>'
      }
    })
  }, [fullscreen, graph, hasSvg, hasMermaid])

  // Close modal on Escape key
  useEffect(() => {
    if (!fullscreen) return
    const onKey = (e) => { if (e.key === 'Escape') setFullscreen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [fullscreen])

  const hasContent = hasSvg || hasMermaid

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
            {hasContent && (
              <span className="text-xs text-emerald-400 border border-emerald-500/30 rounded px-2 py-0.5 bg-emerald-500/10">
                live
              </span>
            )}
            {hasSvg && (
              <button
                onClick={() => openSvgInNewTab(svgImage)}
                title="Open Full Image"
                className="flex items-center gap-1 text-xs text-slate-400 hover:text-white
                           border border-slate-700 hover:border-slate-500 rounded px-2 py-0.5
                           bg-slate-800/60 hover:bg-slate-700/60 transition-colors"
              >
                <ExternalLink size={11} />
                <span>Open Full Image</span>
              </button>
            )}
            {hasContent && (
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
          {!hasContent ? (
            <div className="flex flex-col items-center gap-3 text-slate-600">
              <GitFork size={40} strokeWidth={1} />
              <p className="text-xs text-center">
                Scan a repository to visualize<br />its architecture flowchart
              </p>
            </div>
          ) : hasSvg ? (
            /* SVG image mode */
            <div
              className="w-full h-auto min-h-[380px] overflow-auto flex items-center justify-center"
              dangerouslySetInnerHTML={{ __html: svgImage }}
              style={{ objectFit: 'contain' }}
            />
          ) : (
            /* Mermaid fallback */
            <div ref={containerRef} className="w-full overflow-auto" />
          )}
        </div>

        {/* Loading overlay */}
        {hasContent && !hasSvg && !containerRef.current?.innerHTML && (
          <div className="absolute inset-0 flex items-center justify-center">
            <Loader2 size={24} className="text-indigo-400 animate-spin" />
          </div>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Fullscreen modal with pan + zoom                                     */}
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
            <p className="ml-2 text-xs text-slate-500 hidden sm:block">
              Scroll to zoom · Drag to pan · Double-click to reset
            </p>
            {hasSvg && (
              <button
                onClick={() => openSvgInNewTab(svgImage)}
                title="Open Full Image"
                className="ml-4 flex items-center gap-1.5 text-xs text-slate-400 hover:text-white
                           border border-slate-700 hover:border-slate-500 rounded px-2.5 py-1
                           bg-slate-800/60 hover:bg-slate-700/60 transition-colors"
              >
                <ExternalLink size={12} />
                <span>Open Full Image</span>
              </button>
            )}
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

          {/* Pan + zoom canvas */}
          <div className="flex-1 overflow-hidden relative">
            <TransformWrapper
              initialScale={1}
              minScale={0.2}
              maxScale={5}
              doubleClick={{ mode: 'reset' }}
              wheel={{ step: 0.1 }}
              panning={{ velocityDisabled: false }}
            >
              {({ zoomIn, zoomOut, resetTransform }) => (
                <>
                  {/* Zoom controls */}
                  <div className="absolute top-4 right-4 z-10 flex flex-col gap-1.5">
                    <button
                      onClick={() => zoomIn()}
                      title="Zoom in"
                      className="flex items-center justify-center w-8 h-8 rounded
                                 bg-slate-800 border border-slate-700 text-slate-300
                                 hover:text-white hover:border-slate-500 transition-colors"
                    >
                      <ZoomIn size={14} />
                    </button>
                    <button
                      onClick={() => zoomOut()}
                      title="Zoom out"
                      className="flex items-center justify-center w-8 h-8 rounded
                                 bg-slate-800 border border-slate-700 text-slate-300
                                 hover:text-white hover:border-slate-500 transition-colors"
                    >
                      <ZoomOut size={14} />
                    </button>
                    <button
                      onClick={() => resetTransform()}
                      title="Reset zoom"
                      className="flex items-center justify-center w-8 h-8 rounded
                                 bg-slate-800 border border-slate-700 text-slate-300
                                 hover:text-white hover:border-slate-500 transition-colors"
                    >
                      <RotateCcw size={13} />
                    </button>
                  </div>

                  {/* The diagram lives inside TransformComponent so pan+zoom apply to it */}
                  <TransformComponent
                    wrapperStyle={{ width: '100%', height: '100%' }}
                    contentStyle={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '2rem' }}
                  >
                    {hasSvg ? (
                      <div
                        dangerouslySetInnerHTML={{ __html: svgImage }}
                        style={{ minWidth: '600px' }}
                      />
                    ) : (
                      <div
                        ref={modalContainerRef}
                        style={{ minWidth: '600px' }}
                      />
                    )}
                  </TransformComponent>
                </>
              )}
            </TransformWrapper>
          </div>
        </div>
      )}
    </>
  )
}
