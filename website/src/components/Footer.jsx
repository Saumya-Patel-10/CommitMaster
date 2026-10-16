import { GitCommit, Heart, Shield, FileText } from 'lucide-react';

export default function Footer({ onOpenFeedback, onOpenChat }) {
  return (
    <footer className="border-t border-zinc-800/80 bg-zinc-950 py-12 text-xs text-zinc-500">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-12">
          
          {/* Brand Col */}
          <div className="md:col-span-2">
            <div className="flex items-center gap-2 mb-3">
              <div className="w-6 h-6 rounded-lg bg-emerald-500 flex items-center justify-center text-zinc-950 font-bold">
                <GitCommit className="w-4 h-4" />
              </div>
              <span className="text-zinc-200 font-bold text-sm tracking-tight">CommitMaster</span>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400">v3.0.1</span>
            </div>
            <p className="text-zinc-400 max-w-sm leading-relaxed mb-4 text-xs">
              Privacy-first Git session companion and developer monitor for Windows 11. Designed to run 100% offline with zero cloud telemetry.
            </p>
            <div className="text-[11px] font-mono text-zinc-500">
              Developed & Published by <span className="text-zinc-300">Saumya Patel</span>
            </div>
          </div>

          {/* Quick Links */}
          <div>
            <div className="text-zinc-200 font-semibold mb-3 uppercase tracking-wider text-[11px] font-mono">
              Product & Store
            </div>
            <ul className="space-y-2">
              <li><a href="#download" className="hover:text-zinc-300 transition-colors">Microsoft Store Release</a></li>
              <li><a href="#download" className="hover:text-zinc-300 transition-colors">Direct MSIX Bundle</a></li>
              <li><a href="#download" className="hover:text-zinc-300 transition-colors">Standalone Portable EXE</a></li>
              <li><a href="#interactive-demo" className="hover:text-zinc-300 transition-colors">Interactive Demo</a></li>
              <li><a href="#architecture" className="hover:text-zinc-300 transition-colors">20-Point Security Specs</a></li>
            </ul>
          </div>

          {/* Support & Community */}
          <div>
            <div className="text-zinc-200 font-semibold mb-3 uppercase tracking-wider text-[11px] font-mono">
              Help & Feedback
            </div>
            <ul className="space-y-2">
              <li>
                <button onClick={onOpenChat} className="hover:text-emerald-400 transition-colors flex items-center gap-1.5">
                  <span>CommitMaster AI Assistant</span>
                </button>
              </li>
              <li>
                <button onClick={onOpenFeedback} className="hover:text-amber-400 transition-colors flex items-center gap-1.5">
                  <span>Open Ticket / Suggest Insight</span>
                </button>
              </li>
              <li><a href="#faq" className="hover:text-zinc-300 transition-colors">Documentation & FAQ</a></li>
              <li><a href="https://github.com/Saumya-Patel-10/CommitMaster" target="_blank" rel="noreferrer" className="hover:text-zinc-300 transition-colors flex items-center gap-1">
                <span>GitHub Repository</span>
              </a></li>
              <li><a href="#download" className="hover:text-zinc-300 transition-colors">Windows SmartScreen Notice</a></li>
            </ul>
          </div>

        </div>

        {/* Bottom Bar */}
        <div className="border-t border-zinc-900 pt-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-[11px]">
          <div>
            © {new Date().getFullYear()} Saumya Patel. CommitMaster is open source under the MIT License.
          </div>
          <div className="flex items-center gap-4 text-zinc-500">
            <span className="flex items-center gap-1">
              <Shield className="w-3.5 h-3.5 text-emerald-400" />
              <span>Certified Windows App</span>
            </span>
            <span>•</span>
            <span>Zero Cloud Telemetry</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
