import React, { useState } from 'react';
import { ShieldCheck, Database, KeyRound, Network, Lock, Server, Terminal, CheckCircle2 } from 'lucide-react';

export default function ArchitectureSpecs() {
  const [activeTab, setActiveTab] = useState('security');

  const securityPoints = [
    { title: 'Zero Cloud Code Leakage', desc: 'Prompts & diffs stay strictly on local loopback interface (127.0.0.1).' },
    { title: 'CWE-798 Secret Scanner', desc: 'Pre-commit regex pattern matching for GitHub PATs, AWS keys, and OpenAI tokens.' },
    { title: 'AST Syntax Validation', desc: 'Python Abstract Syntax Tree validator catches parser crashes before git commit.' },
    { title: 'Merge Conflict Blocker', desc: 'Rejects staging of unresolved Git merge conflicts (<<<<<<< HEAD).' },
    { title: 'PBKDF2 Password Hashing', desc: '600,000 SHA-256 iterations with cryptographically random 32-byte salts.' },
    { title: 'Brute-Force Lockout', desc: 'Progressive 15-minute authentication lockout after 5 consecutive failed attempts.' },
    { title: 'AES-256-GCM Encryption', desc: 'Authenticated encryption for local stored tokens and credentials.' },
    { title: 'Row-Level Isolation (RLS)', desc: 'WHERE user_id = ? parameterized SQL enforcement across all database queries.' },
    { title: 'SQL Injection Immunity', desc: '100% Parameterized queries with zero string interpolation.' },
    { title: 'Secure Session Tokens', desc: 'Cryptographically random 64-character tokens (secrets.token_hex(32)).' },
    { title: 'Strict Security Headers', desc: 'X-Content-Type-Options: nosniff, X-Frame-Options: DENY, X-XSS-Protection: 1.' },
    { title: 'Windows 11 Notification Shield', desc: 'Guarantees floating bottom-right toasts render even if system tray crashes.' }
  ];

  return (
    <section id="architecture" className="py-20 border-t border-zinc-800/80 bg-zinc-950/80 relative">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        
        {/* Header */}
        <div className="text-center max-w-3xl mx-auto mb-14">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-emerald-500/30 bg-emerald-950/30 text-emerald-300 text-xs font-mono mb-4">
            <Lock className="w-3.5 h-3.5 text-emerald-400" />
            <span>Enterprise Security Audit</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-bold text-zinc-100 tracking-tight mb-4">
            Built with 20-Point Hardened Security
          </h2>
          <p className="text-zinc-400 text-sm sm:text-base">
            Engineered from ground up to satisfy enterprise code governance. Your proprietary intellectual property and credentials never touch unauthorized servers.
          </p>
        </div>

        {/* Security Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-16">
          {securityPoints.map((p, idx) => (
            <div
              key={idx}
              className="glass-card rounded-xl p-4 border border-zinc-800/80 hover:border-zinc-700 transition-colors"
            >
              <div className="flex items-center gap-2 mb-2">
                <ShieldCheck className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                <span className="text-xs font-bold text-zinc-200">{p.title}</span>
              </div>
              <p className="text-[11px] text-zinc-400 leading-relaxed font-mono">
                {p.desc}
              </p>
            </div>
          ))}
        </div>

        {/* Dual Mode Architecture Banner */}
        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6 sm:p-8 flex flex-col lg:flex-row items-center justify-between gap-8">
          <div className="max-w-xl">
            <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded bg-zinc-800 text-zinc-300 text-[11px] font-mono mb-3">
              <Server className="w-3 h-3 text-cyan-400" />
              <span>Dual-Mode Data Architecture</span>
            </div>
            <h3 className="text-xl font-bold text-zinc-100 mb-2">
              Run Standalone Local or Deploy Central Server
            </h3>
            <p className="text-xs text-zinc-400 leading-relaxed">
              By default, CommitMaster operates 100% locally with zero setup on top of a high-performance SQLite database with WAL journaling. For multi-machine developers, deploy the included <code className="text-emerald-400">server.py</code> Flask REST service on Render or Railway to synchronize tracked workspaces across your fleet.
            </p>
          </div>

          <div className="flex flex-col sm:flex-row gap-3 w-full lg:w-auto">
            <div className="p-4 rounded-xl bg-zinc-950 border border-zinc-800 text-left min-w-[200px]">
              <div className="text-[10px] font-mono text-emerald-400">MODE 1 (DEFAULT)</div>
              <div className="text-xs font-bold text-zinc-200 mt-1">Local SQLite WAL</div>
              <div className="text-[11px] text-zinc-500 mt-0.5">Zero network traffic</div>
            </div>

            <div className="p-4 rounded-xl bg-zinc-950 border border-zinc-800 text-left min-w-[200px]">
              <div className="text-[10px] font-mono text-cyan-400">MODE 2 (OPTIONAL)</div>
              <div className="text-xs font-bold text-zinc-200 mt-1">REST Server Sync</div>
              <div className="text-[11px] text-zinc-500 mt-0.5">Multi-device sync</div>
            </div>
          </div>
        </div>

      </div>
    </section>
  );
}
