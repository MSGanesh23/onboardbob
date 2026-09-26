import { useState } from 'react'
import { GitBranch, Link, Zap } from 'lucide-react'

export default function Header({ onScan, loading }) {
  const [repoUrl, setRepoUrl] = useState('')
  const [issueUrl, setIssueUrl] = useState('')

  const handleScan = () => {
    if (repoUrl.trim()) onScan({ repoUrl: repoUrl.trim(), issueUrl: issueUrl.trim() })
  }

  return (
    <header className="relative z-10 border-b border-white/10 bg-[#0d1224]/80 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-6 py-5">
        {/* Title row */}
        <div className="flex items-center gap-3 mb-6">
          <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-violet-600/20 border border-violet-500/30">
            <Zap size={18} className="text-violet-400" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white">
            Onboard<span className="text-violet-400">Bob</span>
          </h1>
          <span className="ml-2 text-xs text-slate-500 border border-slate-700 rounded px-2 py-0.5">
            v1.0
          </span>
        </div>

        {/* Input row */}
        <div className="flex flex-col sm:flex-row gap-3">
          {/* Repo URL */}
          <div className="flex-1 relative">
            <GitBranch
              size={15}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none"
            />
            <input
              type="text"
              value={repoUrl}
              onChange={e => setRepoUrl(e.target.value)}
              placeholder="https://github.com/owner/repo"
              className="w-full bg-[#141929] border border-white/10 rounded-lg pl-9 pr-4 py-2.5
                         text-sm text-slate-200 placeholder:text-slate-600
                         focus:outline-none focus:border-violet-500/60 focus:ring-1 focus:ring-violet-500/30
                         transition"
            />
          </div>

          {/* Issue URL */}
          <div className="flex-1 relative">
            <Link
              size={15}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none"
            />
            <input
              type="text"
              value={issueUrl}
              onChange={e => setIssueUrl(e.target.value)}
              placeholder="https://github.com/owner/repo/issues/42"
              className="w-full bg-[#141929] border border-white/10 rounded-lg pl-9 pr-4 py-2.5
                         text-sm text-slate-200 placeholder:text-slate-600
                         focus:outline-none focus:border-cyan-500/60 focus:ring-1 focus:ring-cyan-500/30
                         transition"
            />
          </div>

          {/* CTA */}
          <button
            onClick={handleScan}
            disabled={loading || !repoUrl.trim()}
            className="flex items-center gap-2 px-6 py-2.5 rounded-lg font-semibold text-sm
                       bg-gradient-to-r from-violet-600 to-indigo-600
                       hover:from-violet-500 hover:to-indigo-500
                       disabled:opacity-40 disabled:cursor-not-allowed
                       text-white shadow-lg shadow-violet-900/40
                       transition-all duration-200 whitespace-nowrap"
          >
            {loading ? (
              <>
                <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Scanning…
              </>
            ) : (
              <>
                <Zap size={15} />
                Scan &amp; Onboard
              </>
            )}
          </button>
        </div>
      </div>
    </header>
  )
}
