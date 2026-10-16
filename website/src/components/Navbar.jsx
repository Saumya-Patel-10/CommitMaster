import { GitCommit, Sparkles, MessageSquare, Download, ShieldCheck, ExternalLink } from 'lucide-react';

export default function Navbar({ onOpenFeedback, onOpenChat }) {
  return (
    <header className="sticky top-0 z-40 w-full border-b border-zinc-800/80 bg-zinc-950/80 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <a href="#" className="flex items-center gap-2.5 group">
            <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-emerald-400 to-cyan-500 p-0.5 shadow-lg shadow-emerald-500/20 group-hover:scale-105 transition-transform duration-200">
              <div className="w-full h-full bg-zinc-950 rounded-[10px] flex items-center justify-center">
                <GitCommit className="w-5 h-5 text-emerald-400 group-hover:rotate-12 transition-transform" />
              </div>
            </div>
            <div>
              <span className="font-bold text-base text-zinc-100 tracking-tight flex items-center gap-1.5">
                CommitMaster
                <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  v3.0
                </span>
              </span>
            </div>
          </a>
        </div>

        {/* Center Nav Links */}
        <nav className="hidden md:flex items-center gap-6 text-sm font-medium text-zinc-400">
          <a href="#features" className="hover:text-zinc-100 transition-colors">Features</a>
          <a href="#interactive-demo" className="hover:text-zinc-100 transition-colors">Interactive Demo</a>
          <a href="#download" className="hover:text-zinc-100 transition-colors">Downloads</a>
          <a href="#architecture" className="hover:text-zinc-100 transition-colors">Security & Specs</a>
          <a href="#faq" className="hover:text-zinc-100 transition-colors">Docs & FAQ</a>
        </nav>

        {/* Right Actions */}
        <div className="flex items-center gap-2.5">
          {/* Feedback & Ticket Button */}
          <button
            onClick={onOpenFeedback}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:text-white bg-zinc-900/80 hover:bg-zinc-800 border border-zinc-800 rounded-lg transition-colors"
          >
            <MessageSquare className="w-3.5 h-3.5 text-amber-400" />
            <span>Ticket & Feedback</span>
          </button>

          {/* AI Support Button */}
          <button
            onClick={onOpenChat}
            className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-emerald-300 hover:text-emerald-200 bg-emerald-950/40 hover:bg-emerald-900/40 border border-emerald-800/60 rounded-lg transition-colors"
          >
            <Sparkles className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
            <span>AI Support</span>
          </button>

          {/* Direct Download CTA */}
          <a
            href="#download"
            className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold text-zinc-950 bg-emerald-400 hover:bg-emerald-300 rounded-lg shadow-sm shadow-emerald-500/20 transition-all hover:shadow-emerald-500/30"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Get App</span>
          </a>
        </div>
      </div>
    </header>
  );
}
