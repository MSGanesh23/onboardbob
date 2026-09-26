import { BotMessageSquare, FileCode, ExternalLink, Loader2, GitBranch, CheckCircle2, ChevronDown, ChevronUp } from 'lucide-react'
import { useState } from 'react'

export default function IssueNavigator({ issue, impactedFiles, onExecuteFix, fixResult }) {
  const [executing, setExecuting] = useState(false)
  const [done, setDone] = useState(false)
  const [execError, setExecError] = useState(null)
  const [showModal, setShowModal] = useState(false)
  const [showAllFiles, setShowAllFiles] = useState(false)

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
    <>
      {/* Disclaimer Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md mx-4 bg-[#141929] border border-white/10 rounded-xl shadow-2xl p-6">
            <h3 className="text-base font-bold text-white mb-3">
              ⚠️ AI Agent Fix Disclaimer
            </h3>
            <p className="text-sm text-slate-300 leading-relaxed mb-6">
              This action will generate an automated code fix and PyTest test suite draft on a new
              Git branch. AI can occasionally make mistakes—please review all code changes and test
              output before merging.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowModal(false)}
                className="px-4 py-2 rounded-lg text-sm font-semibold text-slate-300
                           bg-slate-700/60 hover:bg-slate-600/60 border border-white/10
                           transition-all duration-150"
              >
                Cancel
              </button>
              <button
                onClick={() => { setShowModal(false); handleExecute() }}
                className="px-4 py-2 rounded-lg text-sm font-semibold text-white
                           bg-gradient-to-r from-cyan-600 to-teal-600
                           hover:from-cyan-500 hover:to-teal-500
                           shadow-lg shadow-cyan-900/30
                           transition-all duration-150"
              >
                Proceed with AI Fix
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="glass-card flex flex-col h-full">
        {/* Header */}
        <div className="flex items-center gap-2 mb-5">
          <div className="flex items-center justify-center w-8 h-8 rounded-md bg-cyan-500/20 border border-cyan-500/30">
            <BotMessageSquare size={16} className="text-cyan-400" />
          </div>
          <h2 className="text-base font-semibold text-white tracking-wide">Issue Navigator</h2>
          {issue?.number && (
            <a
              href={issue.url}
              target="_blank"
              rel="noreferrer"
              className="ml-auto flex items-center gap-1 text-sm text-cyan-400 hover:text-cyan-300 transition"
            >
              #{issue.number}
              <ExternalLink size={13} />
            </a>
          )}
        </div>

        {!issue ? (
          <div className="flex-1 flex flex-col items-center justify-center text-slate-600 gap-3">
            <BotMessageSquare size={40} strokeWidth={1} />
            <p className="text-sm text-center">Provide a GitHub Issue URL<br />to load the spec here</p>
          </div>
        ) : (
          <div className="flex-1 min-h-0 overflow-y-auto flex flex-col gap-5">
            {/* Issue spec */}
            <section>
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
                Issue Spec
              </p>
              <h3 className="text-base font-semibold text-white mb-1.5">{issue.title}</h3>
              <p className="text-sm text-slate-400 leading-relaxed line-clamp-5">
                {issue.body ?? 'No description provided.'}
              </p>
            </section>

            {/* Impacted files */}
            {impactedFiles && impactedFiles.length > 0 && (
              <section>
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
                  Impacted Target Files
                </p>
                <ul className="space-y-2">
                  {impactedFiles.slice(0, showAllFiles ? impactedFiles.length : 5).map((file, i) => (
                    <li
                      key={i}
                      className="flex items-center gap-2 text-sm bg-slate-800/50 border border-white/5
                                 rounded-md px-3 py-2 font-mono text-slate-300"
                    >
                      <FileCode size={13} className="text-slate-500 shrink-0" />
                      {file}
                    </li>
                  ))}
                </ul>
                {impactedFiles.length > 5 && (
                  <button
                    onClick={() => setShowAllFiles(prev => !prev)}
                    className="mt-2.5 flex items-center gap-1.5 text-xs font-semibold text-cyan-400
                               hover:text-cyan-300 transition-colors duration-150"
                  >
                    {showAllFiles ? (
                      <><ChevronUp size={13} /> See Less</>
                    ) : (
                      <><ChevronDown size={13} /> See More ({impactedFiles.length - 5} remaining)</>
                    )}
                  </button>
                )}
              </section>
            )}

            {/* CTA */}
            <div className="mt-auto pt-2 flex flex-col gap-3">
              {/* Success banner – shown when fix result arrives */}
              {(done && fixResult) && (
                <div className="flex flex-col gap-2 text-sm bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-4 py-3">
                  <div className="flex items-center gap-2 text-emerald-400 font-semibold">
                    <CheckCircle2 size={15} className="shrink-0" />
                    Fix executed successfully
                  </div>
                  <div className="flex items-center gap-1.5 text-slate-300 font-mono">
                    <GitBranch size={13} className="text-cyan-400 shrink-0" />
                    <span className="text-cyan-300">{fixResult.branch}</span>
                  </div>
                  {fixResult.pytest_output && (
                    <div className="mt-1">
                      <span className="text-emerald-400 font-semibold">✓ PyTest:</span>
                      <pre className="mt-1 text-xs text-slate-400 bg-slate-900/60 rounded p-2 max-h-32 overflow-y-auto whitespace-pre-wrap break-all">
                        {fixResult.pytest_output}
                      </pre>
                    </div>
                  )}
                </div>
              )}

              {/* Error banner */}
              {execError && (
                <div className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                  ⚠ {execError}
                </div>
              )}

              {!done && (
                <button
                  onClick={() => setShowModal(true)}
                  disabled={executing}
                  className="w-full flex items-center justify-center gap-2 px-5 py-3 rounded-lg
                             font-semibold text-base text-white
                             bg-gradient-to-r from-cyan-600 to-teal-600
                             hover:from-cyan-500 hover:to-teal-500
                             disabled:opacity-40 disabled:cursor-not-allowed
                             shadow-lg shadow-cyan-900/30
                             transition-all duration-200"
                >
                  {executing ? (
                    <>
                      <Loader2 size={16} className="animate-spin" />
                      Executing Fix…
                    </>
                  ) : (
                    <>
                      ✨ Fix using AI
                    </>
                  )}
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </>
  )
}
