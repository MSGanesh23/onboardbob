import { BotMessageSquare, FileCode, ExternalLink, Play, Loader2, GitBranch, CheckCircle2 } from 'lucide-react'
import { useState } from 'react'

export default function IssueNavigator({ issue, impactedFiles, onExecuteFix, fixResult }) {
  const [executing, setExecuting] = useState(false)
  const [done, setDone] = useState(false)
  const [execError, setExecError] = useState(null)

  const handleExecute = async () => {
    if (!onExecuteFix) return
    setExecuting(true)
    setExecError(null)
    try {
      await onExecuteFix()
      setDone(true)
    } catch (err) {
      setExecError(err.response?.data?.detail ?? err.message ?? 'Execution failed')
    } finally {
      setExecuting(false)
    }
  }

  return (
    <div className="glass-card flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        <div className="flex items-center justify-center w-7 h-7 rounded-md bg-cyan-500/20 border border-cyan-500/30">
          <BotMessageSquare size={14} className="text-cyan-400" />
        </div>
        <h2 className="text-sm font-semibold text-white tracking-wide">Issue Navigator</h2>
        {issue?.number && (
          <a
            href={issue.url}
            target="_blank"
            rel="noreferrer"
            className="ml-auto flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300 transition"
          >
            #{issue.number}
            <ExternalLink size={11} />
          </a>
        )}
      </div>

      {!issue ? (
        <div className="flex-1 flex flex-col items-center justify-center text-slate-600 gap-3">
          <BotMessageSquare size={36} strokeWidth={1} />
          <p className="text-xs text-center">Provide a GitHub Issue URL<br />to load the spec here</p>
        </div>
      ) : (
        <div className="flex-1 min-h-0 overflow-y-auto flex flex-col gap-4">
          {/* Issue spec */}
          <section>
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-1.5">
              Issue Spec
            </p>
            <h3 className="text-sm font-semibold text-white mb-1">{issue.title}</h3>
            <p className="text-xs text-slate-400 leading-relaxed line-clamp-5">
              {issue.body ?? 'No description provided.'}
            </p>
          </section>

          {/* Impacted files */}
          {impactedFiles && impactedFiles.length > 0 && (
            <section>
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
                Impacted Target Files
              </p>
              <ul className="space-y-1.5">
                {impactedFiles.map((file, i) => (
                  <li
                    key={i}
                    className="flex items-center gap-2 text-xs bg-slate-800/50 border border-white/5
                               rounded-md px-3 py-2 font-mono text-slate-300"
                  >
                    <FileCode size={12} className="text-slate-500 shrink-0" />
                    {file}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* CTA */}
          <div className="mt-auto pt-2 flex flex-col gap-2">
            {/* Success banner – shown when fix result arrives */}
            {(done && fixResult) && (
              <div className="flex flex-col gap-1.5 text-xs bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-4 py-3">
                <div className="flex items-center gap-2 text-emerald-400 font-semibold">
                  <CheckCircle2 size={14} className="shrink-0" />
                  Fix executed successfully
                </div>
                <div className="flex items-center gap-1.5 text-slate-300 font-mono">
                  <GitBranch size={12} className="text-cyan-400 shrink-0" />
                  <span className="text-cyan-300">{fixResult.branch}</span>
                </div>
                {fixResult.pytest_output && (
                  <div className="mt-1">
                    <span className="text-emerald-400 font-semibold">✓ PyTest:</span>
                    <pre className="mt-1 text-[10px] text-slate-400 bg-slate-900/60 rounded p-2 max-h-28 overflow-y-auto whitespace-pre-wrap break-all">
                      {fixResult.pytest_output}
                    </pre>
                  </div>
                )}
              </div>
            )}

            {/* Error banner */}
            {execError && (
              <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                ⚠ {execError}
              </div>
            )}

            {!done && (
              <button
                onClick={handleExecute}
                disabled={executing}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg
                           font-semibold text-sm text-white
                           bg-gradient-to-r from-cyan-600 to-teal-600
                           hover:from-cyan-500 hover:to-teal-500
                           disabled:opacity-40 disabled:cursor-not-allowed
                           shadow-lg shadow-cyan-900/30
                           transition-all duration-200"
              >
                {executing ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    Executing Fix…
                  </>
                ) : (
                  <>
                    <Play size={14} />
                    Execute Fix via Bob Agent Mode
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
