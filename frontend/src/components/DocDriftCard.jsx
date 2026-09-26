import { FileText, AlertTriangle, CheckCircle } from 'lucide-react'

function CircularGauge({ score }) {
  const radius = 44
  const circumference = 2 * Math.PI * radius
  const clampedScore = Math.max(0, Math.min(100, score ?? 0))
  // Low score = good (less drift). High score = bad (more drift).
  const dashOffset = circumference * (1 - clampedScore / 100)

  const color =
    clampedScore < 30
      ? '#10b981' // green – healthy
      : clampedScore < 60
      ? '#f59e0b' // amber – moderate
      : '#ef4444' // red – high drift

  const label =
    clampedScore < 30 ? 'Healthy' : clampedScore < 60 ? 'Moderate' : 'High Drift'

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative w-28 h-28">
        <svg
          viewBox="0 0 100 100"
          className="w-full h-full -rotate-90"
          aria-label={`Documentation drift score: ${clampedScore}`}
        >
          {/* Track */}
          <circle
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            stroke="#1e293b"
            strokeWidth="8"
          />
          {/* Progress */}
          <circle
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            style={{ transition: 'stroke-dashoffset 0.6s ease, stroke 0.4s ease' }}
          />
        </svg>
        {/* Centre label */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-bold text-white leading-none">{clampedScore}</span>
          <span className="text-[10px] text-slate-500 mt-0.5">/ 100</span>
        </div>
      </div>
      <span className="text-xs font-medium" style={{ color }}>
        {label}
      </span>
    </div>
  )
}

export default function DocDriftCard({ driftScore, missingDocs }) {
  const alerts = missingDocs ?? []

  return (
    <div className="glass-card flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        <div className="flex items-center justify-center w-7 h-7 rounded-md bg-amber-500/20 border border-amber-500/30">
          <FileText size={14} className="text-amber-400" />
        </div>
        <h2 className="text-sm font-semibold text-white tracking-wide">Documentation Drift</h2>
      </div>

      {driftScore == null ? (
        <div className="flex-1 flex flex-col items-center justify-center text-slate-600 gap-3">
          <FileText size={36} strokeWidth={1} />
          <p className="text-xs text-center">Drift score appears<br />after scanning a repo</p>
        </div>
      ) : (
        <>
          {/* Gauge */}
          <div className="flex justify-center mb-4">
            <CircularGauge score={driftScore} />
          </div>

          {/* Alerts */}
          <div className="flex-1 min-h-0 overflow-y-auto">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
              Missing Docstrings
            </p>
            {alerts.length === 0 ? (
              <div className="flex items-center gap-2 text-emerald-400 text-xs">
                <CheckCircle size={14} />
                All symbols documented
              </div>
            ) : (
              <ul className="space-y-1.5">
                {alerts.map((item, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 text-xs text-amber-300
                               bg-amber-500/10 border border-amber-500/30 rounded-md px-3 py-2"
                  >
                    <AlertTriangle size={12} className="text-amber-400 mt-0.5 shrink-0" />
                    <span className="font-mono break-all">{item}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  )
}
