import { Map, CheckCircle2, Circle, BookOpen, Sparkles, Terminal } from 'lucide-react'

// Badge colour mapping per entry-point type
const TYPE_STYLES = {
  entrypoint: 'text-violet-300 border-violet-500/40 bg-violet-500/10',
  router:     'text-indigo-300 border-indigo-500/40 bg-indigo-500/10',
  model:      'text-amber-300  border-amber-500/40  bg-amber-500/10',
}

function EntryBadge({ type }) {
  const cls = TYPE_STYLES[type] ?? 'text-slate-400 border-slate-600 bg-slate-800/50'
  return (
    <span className={`text-[10px] border rounded px-1.5 py-0.5 font-medium ${cls}`}>
      {type}
    </span>
  )
}

function EntryItem({ name, type, checked }) {
  return (
    <li className="flex items-center gap-2.5 text-xs py-1.5 border-b border-white/5 last:border-0">
      {checked ? (
        <CheckCircle2 size={13} className="text-emerald-400 shrink-0" />
      ) : (
        <Circle size={13} className="text-slate-600 shrink-0" />
      )}
      <span className="font-mono text-slate-300 flex-1 truncate" title={name}>{name}</span>
      <EntryBadge type={type} />
    </li>
  )
}

function TourStep({ index, description }) {
  const text = description.replace(/^\d+\.\s*/, '')
  return (
    <li className="flex items-start gap-3">
      <span className="flex items-center justify-center w-5 h-5 rounded-full bg-violet-600/20 border border-violet-500/30 text-[10px] font-bold text-violet-400 shrink-0 mt-0.5">
        {index}
      </span>
      <span className="text-xs text-slate-400 leading-relaxed">{text}</span>
    </li>
  )
}

function SetupStep({ index, text }) {
  // Detect prefix emoji or label for colour hints
  const isInstall = text.includes('Install:') || text.includes('install')
  const isEnv     = text.includes('Env setup:') || text.includes('export') || text.includes('.env')
  const isTest    = text.includes('Run tests:') || text.includes('pytest') || text.includes('npm test')

  const accent = isInstall
    ? 'text-cyan-300 bg-cyan-500/10 border-cyan-500/30'
    : isEnv
    ? 'text-amber-300 bg-amber-500/10 border-amber-500/30'
    : isTest
    ? 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30'
    : 'text-slate-300 bg-slate-800/40 border-slate-700/40'

  return (
    <li className={`flex items-start gap-2 text-xs rounded-md px-3 py-2 border ${accent}`}>
      <Terminal size={11} className="shrink-0 mt-0.5 opacity-60" />
      <span className="font-mono break-all leading-relaxed">{text}</span>
    </li>
  )
}

export default function OnboardingChecklist({ entryPoints, tourSteps, aiSummary, setupGuide }) {
  const entries = entryPoints ?? []
  const tour    = tourSteps   ?? []
  const guide   = setupGuide  ?? []

  const hasContent = entries.length > 0 || tour.length > 0 || aiSummary || guide.length > 0

  return (
    <div className="glass-card flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        <div className="flex items-center justify-center w-7 h-7 rounded-md bg-emerald-500/20 border border-emerald-500/30">
          <Map size={14} className="text-emerald-400" />
        </div>
        <h2 className="text-sm font-semibold text-white tracking-wide">
          AI Onboarding Plan &amp; Project Setup Guide
        </h2>

        {/* Legend */}
        {entries.length > 0 && (
          <div className="ml-auto flex items-center gap-2">
            <EntryBadge type="entrypoint" />
            <EntryBadge type="router" />
            <EntryBadge type="model" />
          </div>
        )}
      </div>

      {!hasContent ? (
        <div className="flex-1 flex flex-col items-center justify-center text-slate-600 gap-3">
          <Map size={36} strokeWidth={1} />
          <p className="text-xs text-center">AI onboarding plan and project setup<br />appear after scanning</p>
        </div>
      ) : (
        <div className="flex-1 min-h-0 overflow-y-auto space-y-5">

          {/* Section A: Project Purpose & Summary */}
          {aiSummary && (
            <section>
              <div className="flex items-center gap-1.5 mb-2">
                <Sparkles size={12} className="text-violet-400" />
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                  Project Purpose &amp; Summary
                </p>
              </div>
              <p className="text-xs text-slate-300 leading-relaxed bg-violet-500/10 border border-violet-500/20 rounded-md px-3 py-2.5">
                {aiSummary}
              </p>
            </section>
          )}

          {/* Section B: Step-by-Step Setup Tips */}
          {guide.length > 0 && (
            <section>
              <div className="flex items-center gap-1.5 mb-2">
                <Terminal size={12} className="text-slate-500" />
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                  Step-by-Step Setup Tips
                </p>
              </div>
              <ul className="space-y-1.5">
                {guide.map((step, i) => (
                  <SetupStep key={i} index={i + 1} text={step} />
                ))}
              </ul>
            </section>
          )}

          {/* Section C: Discovered Entry Points & Reading Tour */}
          {(entries.length > 0 || tour.length > 0) && (
            <section>
              <div className="flex items-center gap-1.5 mb-2">
                <BookOpen size={12} className="text-slate-500" />
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                  Discovered Entry Points &amp; Reading Tour
                </p>
              </div>

              {entries.length > 0 && (
                <ul className="mb-3">
                  {entries.map((ep, i) => (
                    <EntryItem key={i} name={ep.name} type={ep.type} checked={ep.checked ?? (ep.type === 'entrypoint')} />
                  ))}
                </ul>
              )}

              {tour.length > 0 && (
                <ol className="space-y-2.5">
                  {tour.map((step, i) => (
                    <TourStep key={i} index={i + 1} description={step} />
                  ))}
                </ol>
              )}
            </section>
          )}

        </div>
      )}
    </div>
  )
}
