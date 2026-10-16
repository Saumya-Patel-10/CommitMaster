import React, { useState } from 'react';
import { Download, Sparkles, Copy, Check, Terminal, Shield, Cpu, Clock, CheckCircle2, ArrowRight } from 'lucide-react';

export default function Hero({ onOpenChat }) {
  const [copied, setCopied] = useState(false);
  const command = 'winget install SaumyaPatel.CommitMaster';

  const copyCommand = () => {
    navigator.clipboard.writeText(command);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <section className="relative pt-12 pb-20 overflow-hidden">
      {/* Background radial glow */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-gradient-to-b from-emerald-500/10 via-cyan-500/5 to-transparent blur-3xl pointer-events-none -z-10" />

      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        {/* Status Pill Badge */}
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-emerald-500/30 bg-emerald-950/30 text-emerald-300 text-xs font-mono mb-8 backdrop-blur-md">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
          <span>Windows 11 Certified • Version 3.0.1 Live on Microsoft Store</span>
        </div>

        {/* Main Headline */}
        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold text-zinc-100 tracking-tight leading-[1.15] mb-6">
          Your AI Git Copilot for Windows 11 <br className="hidden sm:inline" />
          <span className="bg-gradient-to-r from-emerald-400 via-teal-300 to-cyan-400 bg-clip-text text-transparent">
            That Never Leaks Your Code.
          </span>
        </h1>

        {/* Sub-headline */}
        <p className="max-w-2xl mx-auto text-base sm:text-lg text-zinc-400 leading-relaxed mb-10">
          Tracks active IDE closures across <span className="text-zinc-200 font-medium">VS Code, Cursor & PyCharm</span>. Catches uncommitted changes in 2 seconds, validates AST syntax & blocks CWE-798 secret leaks, then writes Conventional Commits with <span className="text-emerald-400 font-medium">100% offline local AI</span>.
        </p>

        {/* Action Buttons */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-10">
          {/* Microsoft Store Button */}
          <a
            href="https://apps.microsoft.com/"
            target="_blank"
            rel="noreferrer"
            className="w-full sm:w-auto inline-flex items-center justify-center gap-3 px-6 py-3.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-medium text-sm shadow-lg shadow-blue-600/25 transition-all duration-200 hover:-translate-y-0.5"
          >
            <svg className="w-5 h-5 fill-current" viewBox="0 0 24 24">
              <path d="M0 0h11.4v11.4H0V0zm12.6 0H24v11.4H12.6V0zM0 12.6h11.4V24H0V12.6zm12.6 0H24V24H12.6V12.6z"/>
            </svg>
            <div className="text-left">
              <div className="text-[10px] uppercase tracking-wider text-blue-200 font-mono">Available on</div>
              <div className="font-semibold text-sm">Microsoft Store</div>
            </div>
          </a>

          {/* Direct MSIX / EXE Download Button */}
          <a
            href="#download"
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2.5 px-6 py-3.5 rounded-xl bg-zinc-900 hover:bg-zinc-800 border border-zinc-700/80 text-zinc-100 font-medium text-sm transition-all duration-200 hover:-translate-y-0.5"
          >
            <Download className="w-4 h-4 text-emerald-400" />
            <span>Direct MSIX & Portable EXE</span>
          </a>

          {/* Chat with AI Trigger */}
          <button
            onClick={onOpenChat}
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-3.5 rounded-xl bg-zinc-950 hover:bg-zinc-900 border border-emerald-900/60 text-emerald-300 font-medium text-sm transition-all duration-200"
          >
            <Sparkles className="w-4 h-4 text-emerald-400" />
            <span>Ask Support AI</span>
          </button>
        </div>

        {/* Winget Terminal Snippet */}
        <div className="inline-flex items-center gap-3 px-4 py-2 rounded-xl bg-zinc-900/90 border border-zinc-800 text-xs font-mono text-zinc-300 shadow-inner">
          <Terminal className="w-3.5 h-3.5 text-zinc-500" />
          <span className="text-emerald-400 select-all">{command}</span>
          <button
            onClick={copyCommand}
            className="p-1 rounded hover:bg-zinc-800 text-zinc-400 hover:text-zinc-100 transition-colors"
            title="Copy to clipboard"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
        </div>

        {/* Key Metrics / Highlights Strip */}
        <div className="mt-14 grid grid-cols-2 sm:grid-cols-4 gap-4 max-w-4xl mx-auto border-t border-zinc-800/80 pt-8 text-left">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <Cpu className="w-4 h-4" />
            </div>
            <div>
              <div className="text-sm font-semibold text-zinc-200">100% Local AI</div>
              <div className="text-xs text-zinc-500">LM Studio & Ollama Native</div>
            </div>
          </div>

          <div className="flex items-start gap-3">
            <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              <Clock className="w-4 h-4" />
            </div>
            <div>
              <div className="text-sm font-semibold text-zinc-200">2s Exit Grace</div>
              <div className="text-xs text-zinc-500">Multi-IDE Session Watcher</div>
            </div>
          </div>

          <div className="flex items-start gap-3">
            <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20">
              <Shield className="w-4 h-4" />
            </div>
            <div>
              <div className="text-sm font-semibold text-zinc-200">CWE-798 Blocker</div>
              <div className="text-xs text-zinc-500">AST & API Key Defense</div>
            </div>
          </div>

          <div className="flex items-start gap-3">
            <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <CheckCircle2 className="w-4 h-4" />
            </div>
            <div>
              <div className="text-sm font-semibold text-zinc-200">Dual Sync</div>
              <div className="text-xs text-zinc-500">Zero-Config + Cloud Server</div>
            </div>
          </div>
        </div>

      </div>
    </section>
  );
}
