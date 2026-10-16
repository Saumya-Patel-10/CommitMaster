import React, { useState } from 'react';
import { 
  Download, ShieldCheck, Check, Copy, ExternalLink, HelpCircle, 
  ChevronDown, ChevronUp, Package, HardDrive, AlertCircle, Laptop
} from 'lucide-react';

export default function DownloadSection() {
  const [copiedSha, setCopiedSha] = useState('');
  const [showSmartScreenGuide, setShowSmartScreenGuide] = useState(false);

  const msixSha = 'ca864b446f996b18e1d384312b72a2569870ed98140ccff52e42077ce2bba9ce';
  const exeSha = '6fea0f0a2d932dafc9749ea347fd095438a8b8d390707dc854d93d62ad57b99d';
  const githubReleaseBase = 'https://github.com/Saumya-Patel-10/CommitMaster/releases/latest/download';

  const copyChecksum = (hash, label) => {
    navigator.clipboard.writeText(hash);
    setCopiedSha(label);
    setTimeout(() => setCopiedSha(''), 2000);
  };

  return (
    <section id="download" className="py-20 border-t border-zinc-800/80 bg-zinc-950 relative">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        
        {/* Title */}
        <div className="text-center max-w-2xl mx-auto mb-14">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-blue-500/30 bg-blue-950/30 text-blue-300 text-xs font-mono mb-4">
            <Package className="w-3.5 h-3.5 text-blue-400" />
            <span>Distribution & Packages</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-bold text-zinc-100 tracking-tight mb-4">
            Get CommitMaster for Windows 11 & 10
          </h2>
          <p className="text-zinc-400 text-sm sm:text-base">
            Choose the official Microsoft Store release for automatic silent updates, or download direct MSIX / standalone portable packages for offline developer workstations.
          </p>
        </div>

        {/* Download Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-12">
          
          {/* Card 1: Microsoft Store */}
          <div className="glass-card rounded-2xl p-6 sm:p-8 border border-blue-500/30 relative flex flex-col justify-between hover:border-blue-500/50 transition-all shadow-lg shadow-blue-500/5">
            <div className="absolute top-4 right-4 px-2.5 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20 text-[10px] font-mono uppercase tracking-wider">
              Recommended
            </div>

            <div>
              <div className="w-12 h-12 rounded-xl bg-blue-600/20 border border-blue-500/40 flex items-center justify-center mb-6 text-blue-400">
                <svg className="w-7 h-7 fill-current" viewBox="0 0 24 24">
                  <path d="M0 0h11.4v11.4H0V0zm12.6 0H24v11.4H12.6V0zM0 12.6h11.4V24H0V12.6zm12.6 0H24V24H12.6V12.6z"/>
                </svg>
              </div>

              <h3 className="text-xl font-bold text-zinc-100 mb-2">Microsoft Store Certified Release</h3>
              <p className="text-xs text-zinc-400 mb-6 leading-relaxed">
                Packaged through Windows App SDK / MSIX with AppContainer security. Certified by Microsoft Partner Center.
              </p>

              <ul className="space-y-2.5 text-xs text-zinc-300 mb-8">
                <li className="flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                  <span>Automatic background delta updates via Store engine</span>
                </li>
                <li className="flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                  <span>Zero Windows SmartScreen warning prompts</span>
                </li>
                <li className="flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                  <span>Sandboxed registry & file system isolation</span>
                </li>
                <li className="flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                  <span>Version 3.0.1.0 • Publisher: Saumya Patel</span>
                </li>
              </ul>
            </div>

            <div>
              <a
                href="https://apps.microsoft.com/"
                target="_blank"
                rel="noreferrer"
                className="w-full flex items-center justify-center gap-2 py-3 px-4 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs transition-colors shadow-lg shadow-blue-600/30"
              >
                <span>Install from Microsoft Store</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
              <div className="text-center text-[11px] text-zinc-500 mt-2 font-mono">
                App ID: SaumyaPatel.CommitMaster
              </div>
            </div>
          </div>

          {/* Card 2: Direct Downloads */}
          <div className="glass-card rounded-2xl p-6 sm:p-8 border border-zinc-800 flex flex-col justify-between hover:border-zinc-700 transition-all">
            <div>
              <div className="w-12 h-12 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center mb-6 text-emerald-400">
                <HardDrive className="w-6 h-6" />
              </div>

              <h3 className="text-xl font-bold text-zinc-100 mb-2">Direct Offline Downloads</h3>
              <p className="text-xs text-zinc-400 mb-6 leading-relaxed">
                Direct installation packages for air-gapped workstations, corporate firewalls, or portable flash drives.
              </p>

              {/* Direct Buttons */}
              <div className="space-y-3 mb-6">
                {/* Standalone EXE Button (Primary recommended direct download) */}
                <div className="p-3.5 rounded-xl border border-zinc-800 bg-zinc-900/40 flex items-center justify-between">
                  <div>
                    <div className="text-xs font-semibold text-zinc-200">CommitMaster.exe (Standalone)</div>
                    <div className="text-[11px] text-zinc-500 font-mono">Single Win32 Executable • 41.3 MB</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <a 
                      href={`${githubReleaseBase}/CommitMaster.exe`}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold transition-colors shadow-md shadow-emerald-600/20"
                    >
                      <Download className="w-3.5 h-3.5 text-zinc-950" />
                      <span>Download</span>
                    </a>
                  </div>
                </div>

                {/* Checksum EXE */}
                <div className="flex items-center justify-between text-[11px] font-mono text-zinc-500 px-1">
                  <span className="truncate max-w-[240px]">SHA256: {exeSha.slice(0, 16)}...</span>
                  <button 
                    onClick={() => copyChecksum(exeSha, 'exe')}
                    className="text-cyan-400 hover:underline flex items-center gap-1"
                  >
                    {copiedSha === 'exe' ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                    <span>{copiedSha === 'exe' ? 'Copied' : 'Copy Hash'}</span>
                  </button>
                </div>

                {/* MSIX Button */}
                <div className="p-3.5 rounded-xl border border-zinc-800 bg-zinc-900/40 flex items-center justify-between mt-3">
                  <div>
                    <div className="text-xs font-semibold text-zinc-200">CommitMaster.msix</div>
                    <div className="text-[11px] text-zinc-500 font-mono">Signed Package • 41.2 MB</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <a 
                      href={`${githubReleaseBase}/CommitMaster.msix`}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-medium transition-colors"
                    >
                      <Download className="w-3.5 h-3.5 text-emerald-400" />
                      <span>Download</span>
                    </a>
                  </div>
                </div>

                {/* Checksum MSIX */}
                <div className="flex items-center justify-between text-[11px] font-mono text-zinc-500 px-1">
                  <span className="truncate max-w-[240px]">SHA256: {msixSha.slice(0, 16)}...</span>
                  <button 
                    onClick={() => copyChecksum(msixSha, 'msix')}
                    className="text-emerald-400 hover:underline flex items-center gap-1"
                  >
                    {copiedSha === 'msix' ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                    <span>{copiedSha === 'msix' ? 'Copied' : 'Copy Hash'}</span>
                  </button>
                </div>
              </div>
            </div>

            {/* SmartScreen guidance trigger */}
            <button
              onClick={() => setShowSmartScreenGuide(!showSmartScreenGuide)}
              className="w-full flex items-center justify-between py-2 px-3 rounded-lg bg-zinc-900 text-zinc-400 hover:text-zinc-200 text-xs font-medium border border-zinc-800 transition-colors"
            >
              <div className="flex items-center gap-2">
                <HelpCircle className="w-3.5 h-3.5 text-amber-400" />
                <span>Windows SmartScreen Notice for Direct Downloads</span>
              </div>
              {showSmartScreenGuide ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
          </div>

        </div>

        {/* SmartScreen Collapsible Guide */}
        {showSmartScreenGuide && (
          <div className="p-5 rounded-2xl bg-amber-950/20 border border-amber-800/40 text-xs text-zinc-300 mb-12 animate-in fade-in duration-200">
            <div className="flex items-center gap-2 font-bold text-amber-300 text-sm mb-2">
              <AlertCircle className="w-4 h-4 text-amber-400" />
              <span>How to pass "Windows protected your PC" (SmartScreen) on Direct Downloads</span>
            </div>
            <p className="mb-3 leading-relaxed">
              When downloading direct Win32 or MSIX files outside the Microsoft Store, Windows Defender SmartScreen displays a blue advisory banner until community reputation is accumulated for the binary hash.
            </p>
            <ol className="list-decimal list-inside space-y-1 text-zinc-400 font-mono text-[11px]">
              <li>When the blue banner appears, click <strong className="text-zinc-100">"More info"</strong>.</li>
              <li>Click <strong className="text-emerald-400">"Run anyway"</strong> to launch the verified CommitMaster installer.</li>
              <li>You can verify the downloaded binary against the SHA-256 checksums provided above using <code className="text-zinc-300">Get-FileHash CommitMaster.msix</code> in PowerShell.</li>
            </ol>
          </div>
        )}

        {/* System Requirements Table */}
        <div className="border border-zinc-800/80 rounded-2xl p-6 bg-zinc-900/30">
          <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-zinc-400 mb-4">
            <Laptop className="w-4 h-4 text-emerald-400" />
            <span>Target Platform & System Requirements</span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
            <div className="p-3 rounded-xl bg-zinc-900/60 border border-zinc-800/60">
              <div className="text-zinc-500 font-mono text-[10px]">OPERATING SYSTEM</div>
              <div className="font-semibold text-zinc-200 mt-0.5">Windows 11 / 10</div>
              <div className="text-zinc-500 text-[11px]">Build 19041 or higher (x64)</div>
            </div>

            <div className="p-3 rounded-xl bg-zinc-900/60 border border-zinc-800/60">
              <div className="text-zinc-500 font-mono text-[10px]">GIT ENGINE</div>
              <div className="font-semibold text-zinc-200 mt-0.5">Git for Windows</div>
              <div className="text-zinc-500 text-[11px]">Git 2.25+ in system PATH</div>
            </div>

            <div className="p-3 rounded-xl bg-zinc-900/60 border border-zinc-800/60">
              <div className="text-zinc-500 font-mono text-[10px]">LOCAL AI (OPTIONAL)</div>
              <div className="font-semibold text-zinc-200 mt-0.5">LM Studio / Ollama</div>
              <div className="text-zinc-500 text-[11px]">Or built-in AST heuristics</div>
            </div>

            <div className="p-3 rounded-xl bg-zinc-900/60 border border-zinc-800/60">
              <div className="text-zinc-500 font-mono text-[10px]">DISK FOOTPRINT</div>
              <div className="font-semibold text-zinc-200 mt-0.5">&lt; 85 MB Storage</div>
              <div className="text-zinc-500 text-[11px]">Self-contained runtime</div>
            </div>
          </div>
        </div>

      </div>
    </section>
  );
}
