import React, { useState } from 'react';
import { HelpCircle, ChevronDown, ChevronUp, Terminal, Sparkles, BookOpen, Check } from 'lucide-react';

export default function DocsFaq({ onOpenChat }) {
  const [openIdx, setOpenIdx] = useState(0);

  const faqs = [
    {
      q: "Can I run CommitMaster with zero internet connectivity?",
      a: "Yes. CommitMaster is designed offline-first. The Git watcher, pre-commit AST inspector, CWE-798 secret scanner, and local AI generators (LM Studio, Ollama) run entirely against localhost without contacting any remote cloud servers."
    },
    {
      q: "Which IDEs and Code Editors are actively monitored?",
      a: "CommitMaster tracks independent process trees for Visual Studio Code (Code.exe), Cursor (Cursor.exe), Antigravity IDE (Antigravity IDE.exe), PyCharm (pycharm64.exe), IntelliJ IDEA (idea64.exe), and Visual Studio (devenv.exe). When an editor closes, CommitMaster activates a 2-second grace exit watcher."
    },
    {
      q: "How do I connect LM Studio or Ollama?",
      a: "For LM Studio: Start the local server at http://127.0.0.1:1234/v1 and select any coding model (Qwen 2.5 Coder, DeepSeek Coder, or Llama 3.2). In CommitMaster Settings, set Provider to LM Studio. For Ollama, run 'ollama run qwen2.5-coder' in terminal and point the endpoint to http://localhost:11434/v1."
    },
    {
      q: "Why do I see a Windows SmartScreen blue banner on direct downloads?",
      a: "Windows Defender SmartScreen uses cryptographic publisher reputation. New releases accumulate reputation as users run the binary. The package is digitally hashed, and you can verify the SHA-256 checksum in PowerShell using 'Get-FileHash'. Clicking 'More info' -> 'Run anyway' installs the app. Alternatively, the Microsoft Store build bypasses SmartScreen entirely."
    },
    {
      q: "Can I use multiple GitHub accounts on the same computer?",
      a: "Yes! CommitMaster includes a dedicated Multi-Account Profile Manager. You can link personal, freelance, and corporate GitHub accounts, and bind individual Git repositories to specific accounts so commits and pushes always use the intended identity."
    }
  ];

  return (
    <section id="faq" className="py-20 border-t border-zinc-800/80 bg-zinc-950 relative">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        
        {/* Header */}
        <div className="text-center mb-14">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-zinc-700 bg-zinc-900/80 text-zinc-300 text-xs font-mono mb-4">
            <BookOpen className="w-3.5 h-3.5 text-emerald-400" />
            <span>Documentation & FAQ</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-bold text-zinc-100 tracking-tight mb-4">
            Frequently Asked Questions
          </h2>
          <p className="text-zinc-400 text-sm">
            Everything you need to know about installation, privacy, local AI pairing, and IDE tracking.
          </p>
        </div>

        {/* Quickstart 3-Steps Box */}
        <div className="p-6 rounded-2xl border border-zinc-800 bg-zinc-900/40 mb-12">
          <div className="text-xs font-mono uppercase tracking-wider text-emerald-400 font-semibold mb-4">
            3-Step Quickstart Guide
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
            <div className="p-3.5 rounded-xl bg-zinc-900/80 border border-zinc-800">
              <div className="w-5 h-5 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center font-bold mb-2">1</div>
              <div className="font-semibold text-zinc-200">Install & Launch</div>
              <div className="text-zinc-400 mt-1">Get the Microsoft Store release or download the standalone MSIX / portable executable.</div>
            </div>

            <div className="p-3.5 rounded-xl bg-zinc-900/80 border border-zinc-800">
              <div className="w-5 h-5 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center font-bold mb-2">2</div>
              <div className="font-semibold text-zinc-200">Add Git Repositories</div>
              <div className="text-zinc-400 mt-1">Select your workspace folders or let CommitMaster auto-discover active git repos on your disk.</div>
            </div>

            <div className="p-3.5 rounded-xl bg-zinc-900/80 border border-zinc-800">
              <div className="w-5 h-5 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center font-bold mb-2">3</div>
              <div className="font-semibold text-zinc-200">Code with Confidence</div>
              <div className="text-zinc-400 mt-1">Close your IDE anytime. CommitMaster catches unstaged work, scans secrets, and drafts conventional commits.</div>
            </div>
          </div>
        </div>

        {/* FAQ Accordion */}
        <div className="space-y-3 mb-12">
          {faqs.map((faq, idx) => {
            const isOpen = openIdx === idx;
            return (
              <div
                key={idx}
                className="rounded-xl border border-zinc-800 bg-zinc-900/40 overflow-hidden transition-colors"
              >
                <button
                  onClick={() => setOpenIdx(isOpen ? -1 : idx)}
                  className="w-full p-4 text-left flex items-center justify-between text-xs sm:text-sm font-semibold text-zinc-200 hover:text-white transition-colors"
                >
                  <span>{faq.q}</span>
                  {isOpen ? <ChevronUp className="w-4 h-4 text-emerald-400 flex-shrink-0" /> : <ChevronDown className="w-4 h-4 text-zinc-500 flex-shrink-0" />}
                </button>
                {isOpen && (
                  <div className="px-4 pb-4 text-xs text-zinc-400 leading-relaxed border-t border-zinc-800/60 pt-3">
                    {faq.a}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Still have questions CTA */}
        <div className="p-6 rounded-2xl border border-emerald-900/50 bg-emerald-950/20 flex flex-col sm:flex-row items-center justify-between gap-4 text-center sm:text-left">
          <div>
            <div className="text-sm font-bold text-zinc-100 mb-1">
              Have a question not covered here?
            </div>
            <div className="text-xs text-zinc-400">
              Chat with our automated CommitMaster AI assistant trained on the complete codebase.
            </div>
          </div>
          <button
            onClick={onOpenChat}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-bold text-xs transition-colors flex-shrink-0"
          >
            <Sparkles className="w-4 h-4" />
            <span>Ask Support AI</span>
          </button>
        </div>

      </div>
    </section>
  );
}
