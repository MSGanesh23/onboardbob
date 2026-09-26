import { Map, CheckCircle2, Circle, BookOpen } from 'lucide-react'

function EntryItem({ name, type, checked }) {
  return (
    <li className="flex items-center gap-2.5 text-xs py-1.5 border-b border-white/5 last:border-0">
      {checked ? (
        <CheckCircle2 size={13} className="text-emerald-400 shrink-0" />
      ) : (
        <Circle size={13} className="text-slate-600 shrink-0" />
      )}
      <span className="font-mono text-slate-300 flex-1">{name}</span>
      <span className="text-[10px] text-slate-600 border border-slate-700 rounded px-1.5 py-0.5 bg-slate-800/50">
        {type}
      </span>
    </li>
  )
}

function TourStep({ index, description }) {
  return (
    <li className="flex items-start gap-3">
      <span className="flex items-center justify-center w-5 h-5 rounded-full bg-violet-600/20 border border-violet-500/30 text-[10px] font-bold text-violet-400 shrink-0 mt-0.5">
        {index}
      </span>
      <span className="text-xs text-slate-400 leading-relaxed">{description}</span>
    </li>
  )
}

export default function OnboardingChecklist({ entryPoints, tourSteps }) {
  const entries = entryPoints ?? []
  const tour = tourSteps ?? []

  return (
    <div className="glass-card flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        <div className="flex items-center justify-center w-7 h-7 rounded-md bg-emerald-500/20 border border-emerald-500/30">
          <Map size={14} className="text-emerald-400" />
        </div>
        <h2 className="text-sm font-semibold text-white tracking-wide">Onboarding Checklist</h2>
      </div>

      {entries.length === 0 && tour.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center text-slate-600 gap-3">
          <Map size={36} strokeWidth={1} />
          <p className="text-xs text-center">Entry points and reading tour<br />appear after scanning</p>
        </div>
      ) : (
        <div className="flex-1 min-h-0 overflow-y-auto space-y-5">
          {/* Entry Points */}
          {entries.length > 0 && (
            <section>
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
                Discovered Entry Points
              </p>
              <ul>
                {entries.map((ep, i) => (
                  <EntryItem key={i} name={ep.name} type={ep.type} checked={ep.checked} />
                ))}
              </ul>
            </section>
          )}

          {/* Architectural Reading Tour */}
          {tour.length > 0 && (
            <section>
              <div className="flex items-center gap-1.5 mb-2">
                <BookOpen size={12} className="text-slate-500" />
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                  Architectural Reading Tour
                </p>
              </div>
              <ol className="space-y-2.5">
                {tour.map((step, i) => (
                  <TourStep key={i} index={i + 1} description={step} />
                ))}
              </ol>
            </section>
          )}
        </div>
      )}
    </div>
  )
}
