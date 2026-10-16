import React, { useState, useEffect } from 'react';
import { 
  Play, ShieldAlert, ShieldCheck, Check, Sparkles, Terminal, 
  Layers, BellRing, Laptop, Cpu, X, RefreshCw, AlertTriangle
} from 'lucide-react';

export default function InteractiveDemo() {
  const [activeTab, setActiveTab] = useState('textures');

  // Texture state
  const [activeTexture, setActiveTexture] = useState('tech-dots');

  // IDE Simulation State
  const [runningIdes, setRunningIdes] = useState({
    'Code.exe': true,
    'Cursor.exe': true,
    'Antigravity IDE.exe': true,
    'pycharm64.exe': false,
  });
  const [simulatingExit, setSimulatingExit] = useState(null);
  const [showToast, setShowToast] = useState(false);
  const [toastRepo, setToastRepo] = useState('CommitMaster');

  // Security Inspector State
  const [hasSecret, setHasSecret] = useState(true);
  const [hasSyntaxError, setHasSyntaxError] = useState(false);
  const [inspecting, setInspecting] = useState(false);
  const [inspectVerdict, setInspectVerdict] = useState(null);

  // AI Diff Generator State
  const [aiProvider, setAiProvider] = useState('lmstudio');
  const [generatingAi, setGeneratingAi] = useState(false);
  const [aiResult, setAiResult] = useState({
    title: 'feat(auth): add PBKDF2 600k iteration hashing and rate limiter',
    description: '- Encrypt session tokens with AES-256-GCM\n- Lockout IP after 5 failed brute-force attempts for 15 mins\n- Exclude raw password hashes from REST serializations',
    provider: 'LM Studio (Local Qwen 2.5 Coder 7B)'
  });

  const handleCloseIde = (ideName) => {
    setRunningIdes(prev => ({ ...prev, [ideName]: false }));
    setSimulatingExit(ideName);
    setShowToast(false);

    // 2 second grace timer
    setTimeout(() => {
      setSimulatingExit(null);
      setToastRepo('SaumyaPatel/CommitMaster');
      setShowToast(true);
    }, 1800);
  };

  const handleRestartIde = (ideName) => {
    setRunningIdes(prev => ({ ...prev, [ideName]: true }));
    if (simulatingExit === ideName) setSimulatingExit(null);
  };

  const handleRunInspection = () => {
    setInspecting(true);
    setInspectVerdict(null);
    setTimeout(() => {
      setInspecting(false);
      if (hasSecret) {
        setInspectVerdict({
          status: 'BLOCKED',
          rule: 'CWE-798: Hardcoded Credential Detected',
          details: 'Found GitHub Personal Access Token pattern `ghp_xxxx` on line 14 of `config.py`. Staging aborted.'
        });
      } else if (hasSyntaxError) {
        setInspectVerdict({
          status: 'BLOCKED',
          rule: 'AST Syntax Validation Failed',
          details: 'SyntaxError: unexpected EOF while parsing on line 42 of `server.py`. Fix syntax before staging.'
        });
      } else {
        setInspectVerdict({
          status: 'PASSED',
          rule: 'Clean Pre-Commit Audit',
          details: 'Zero credentials detected. Python AST, JSON schemas, and merge conflict markers 100% verified.'
        });
      }
    }, 600);
  };

  const handleGenerateAiCommit = () => {
    setGeneratingAi(true);
    setTimeout(() => {
      setGeneratingAi(false);
      if (aiProvider === 'lmstudio') {
        setAiResult({
          title: 'refactor(watcher): optimize multi-IDE polling interval to 2000ms',
          description: '- Independent process trees for VS Code, Cursor and Antigravity\n- Add memory-efficient LRU cache for procedural canvas redraws\n- 100% offline local inference via LM Studio (127.0.0.1:1234)',
          provider: 'LM Studio (Local Offline)'
        });
      } else if (aiProvider === 'ollama') {
        setAiResult({
          title: 'fix(security): prevent CWE-798 secret leak in Git staging area',
          description: '- Regex scanner for AWS keys (AKIA*) and GitHub PATs (ghp_*)\n- Block git add when uncommitted merge conflicts remain\n- Local inference via Ollama localhost:11434',
          provider: 'Ollama (Local Offline)'
        });
      } else {
        setAiResult({
          title: 'feat(ui): implement procedural Tech Dots and Circuit Mesh textures',
          description: '- Pure Canvas procedural texture generation\n- Dynamic Fluent UI accent switching\n- AST heuristic Conventional Commit fallback engine',
          provider: 'Heuristic AST Engine (Offline Fallback)'
        });
      }
    }, 700);
  };

  // Procedural canvas CSS patterns for demo
  const getTextureStyle = () => {
    switch (activeTexture) {
      case 'tech-dots':
        return {
          backgroundImage: 'radial-gradient(rgba(16, 185, 129, 0.25) 1.5px, transparent 1.5px)',
          backgroundSize: '16px 16px',
          backgroundColor: '#09090b'
        };
      case 'circuit-mesh':
        return {
          backgroundImage: 'linear-gradient(rgba(14, 165, 233, 0.15) 1px, transparent 1px), linear-gradient(90deg, rgba(14, 165, 233, 0.15) 1px, transparent 1px)',
          backgroundSize: '24px 24px',
          backgroundColor: '#070d14'
        };
      case 'carbon-weave':
        return {
          backgroundImage: 'radial-gradient(black 15%, transparent 16%), radial-gradient(black 15%, transparent 16%)',
          backgroundPosition: '0 0, 10px 10px',
          backgroundSize: '20px 20px',
          backgroundColor: '#121217'
        };
      case 'blueprint':
        return {
          backgroundImage: 'linear-gradient(rgba(59, 130, 246, 0.2) 1px, transparent 1px), linear-gradient(90deg, rgba(59, 130, 246, 0.2) 1px, transparent 1px)',
          backgroundSize: '32px 32px',
          backgroundColor: '#0a101f'
        };
      case 'hexagon':
        return {
          backgroundImage: 'radial-gradient(rgba(168, 85, 247, 0.25) 1px, transparent 1px)',
          backgroundSize: '20px 20px',
          backgroundColor: '#110c1c'
        };
      default:
        return { backgroundColor: '#09090b' };
    }
  };

  return (
    <section id="interactive-demo" className="py-20 border-t border-zinc-800/80 bg-zinc-950/60 relative">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        
        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto mb-12">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-zinc-700 bg-zinc-900/80 text-zinc-300 text-xs font-mono mb-4">
            <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
            <span>Interactive Simulator</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-bold text-zinc-100 tracking-tight mb-4">
            Test CommitMaster Features Live in Your Browser
          </h2>
          <p className="text-zinc-400 text-sm sm:text-base">
            Experience the core innovations of CommitMaster before downloading: procedural tactile textures, 2-second IDE exit tracking, pre-commit secret interception, and offline AI diff generation.
          </p>
        </div>

        {/* Tab Switcher */}
        <div className="flex flex-wrap justify-center gap-2 mb-8">
          {[
            { id: 'textures', label: '🎨 7 Procedural Textures', icon: Layers },
            { id: 'ide-tracker', label: '🔔 Multi-IDE Session Monitor', icon: BellRing },
            { id: 'security', label: '🛡️ Pre-Commit Security Inspector', icon: ShieldAlert },
            { id: 'ai-diff', label: '🤖 Offline AI Commit Generator', icon: Cpu }
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2 text-xs sm:text-sm font-medium rounded-xl border transition-all ${
                activeTab === tab.id
                  ? 'border-emerald-500 bg-emerald-950/40 text-emerald-300 shadow-sm shadow-emerald-500/10'
                  : 'border-zinc-800 bg-zinc-900/60 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              <span>{tab.label}</span>
            </button>
          ))}
        </div>

        {/* Interactive Container Box */}
        <div className="glass-card rounded-2xl border border-zinc-800 overflow-hidden shadow-2xl relative min-h-[460px]">
          
          {/* TAB 1: PROCEDURAL TEXTURES */}
          {activeTab === 'textures' && (
            <div className="p-6 sm:p-8">
              <div className="flex flex-col lg:flex-row gap-8 items-start">
                <div className="lg:w-1/3">
                  <h3 className="text-lg font-bold text-zinc-100 mb-2">Procedural Surface Textures</h3>
                  <p className="text-xs text-zinc-400 mb-6 leading-relaxed">
                    CommitMaster features 7 dynamically generated tactile textures rendered natively via procedural Canvas algorithms with an in-memory LRU cache for butter-smooth 60fps rendering.
                  </p>
                  
                  <div className="space-y-2">
                    {[
                      { id: 'tech-dots', name: 'Tech Dot Matrix', desc: 'Developer coordinate grid' },
                      { id: 'circuit-mesh', name: 'Circuit Mesh', desc: 'Silicon bus lines & micro traces' },
                      { id: 'carbon-weave', name: 'Carbon Weave', desc: 'Diagonal composite tactile weave' },
                      { id: 'blueprint', name: 'Blueprint Grid', desc: 'Isometric engineering coordinate' },
                      { id: 'hexagon', name: 'Hexagon Mesh', desc: 'Cyber honeycomb wireframe' },
                    ].map(tex => (
                      <button
                        key={tex.id}
                        onClick={() => setActiveTexture(tex.id)}
                        className={`w-full text-left p-3 rounded-xl border text-xs transition-all ${
                          activeTexture === tex.id
                            ? 'border-emerald-500/60 bg-emerald-950/40 text-emerald-200'
                            : 'border-zinc-800 bg-zinc-900/40 text-zinc-400 hover:bg-zinc-800/50'
                        }`}
                      >
                        <div className="font-semibold text-zinc-200">{tex.name}</div>
                        <div className="text-[11px] text-zinc-500">{tex.desc}</div>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Live Canvas Mockup */}
                <div className="lg:w-2/3 w-full">
                  <div 
                    className="w-full h-80 rounded-xl border border-zinc-700/60 p-6 flex flex-col justify-between transition-all duration-300 relative overflow-hidden shadow-inner"
                    style={getTextureStyle()}
                  >
                    {/* Header simulating desktop window */}
                    <div className="flex items-center justify-between border-b border-white/10 pb-4">
                      <div className="flex items-center gap-2">
                        <div className="w-3 h-3 rounded-full bg-red-500/80" />
                        <div className="w-3 h-3 rounded-full bg-amber-500/80" />
                        <div className="w-3 h-3 rounded-full bg-emerald-500/80" />
                        <span className="text-xs font-mono text-zinc-300 ml-2">CommitMaster v3.0 — Fluent Procedural Window</span>
                      </div>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-black/40 text-emerald-300 border border-emerald-500/20">
                        Texture: {activeTexture}
                      </span>
                    </div>

                    {/* Window Content Simulation */}
                    <div className="my-auto bg-zinc-950/80 backdrop-blur-md rounded-xl p-5 border border-white/10 max-w-md">
                      <div className="text-xs text-emerald-400 font-mono mb-1">● IDE Session Active</div>
                      <div className="text-sm font-semibold text-zinc-100">Tracking 4 Active Git Repositories</div>
                      <p className="text-xs text-zinc-400 mt-1">
                        Procedural textures provide depth without slowing down window drag or rendering cycles.
                      </p>
                    </div>

                    <div className="text-[11px] font-mono text-zinc-400 flex justify-between items-center bg-black/40 px-3 py-1.5 rounded-lg border border-white/5">
                      <span>FPS: 60 (LRU Image Cached)</span>
                      <span>Render: Native Canvas Procedural</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: MULTI-IDE SESSION TRACKER */}
          {activeTab === 'ide-tracker' && (
            <div className="p-6 sm:p-8">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-center">
                <div>
                  <h3 className="text-lg font-bold text-zinc-100 mb-2">Multi-IDE Session Tracking & 2s Exit Grace</h3>
                  <p className="text-xs text-zinc-400 mb-6 leading-relaxed">
                    Unlike simple tray daemons that poll a single window title, CommitMaster concurrently tracks distinct IDE executables (<code className="text-emerald-400">Code.exe</code>, <code className="text-emerald-400">Cursor.exe</code>, <code className="text-emerald-400">Antigravity IDE.exe</code>). Closing one editor triggers a 2-second check for uncommitted changes in that project!
                  </p>

                  <div className="text-xs font-semibold text-zinc-300 mb-3 uppercase tracking-wider font-mono">
                    Simulate Closing an IDE Process:
                  </div>

                  <div className="grid grid-cols-2 gap-3 mb-6">
                    {Object.entries(runningIdes).map(([ide, isRunning]) => (
                      <div key={ide} className="p-3 rounded-xl border border-zinc-800 bg-zinc-900/60 flex items-center justify-between">
                        <div>
                          <div className="text-xs font-semibold text-zinc-200">{ide}</div>
                          <div className={`text-[10px] font-mono ${isRunning ? 'text-emerald-400' : 'text-zinc-500'}`}>
                            {isRunning ? '● Process Running' : '○ Terminated'}
                          </div>
                        </div>
                        {isRunning ? (
                          <button
                            onClick={() => handleCloseIde(ide)}
                            className="px-2.5 py-1 text-xs rounded-lg bg-red-950/40 hover:bg-red-900/50 text-red-300 border border-red-800/60 transition-colors"
                          >
                            Simulate Exit
                          </button>
                        ) : (
                          <button
                            onClick={() => handleRestartIde(ide)}
                            className="px-2.5 py-1 text-xs rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 transition-colors flex items-center gap-1"
                          >
                            <RefreshCw className="w-3 h-3" /> Re-open
                          </button>
                        )}
                      </div>
                    ))}
                  </div>

                  {simulatingExit && (
                    <div className="flex items-center gap-2 p-3 rounded-xl bg-amber-950/30 border border-amber-800/50 text-amber-300 text-xs font-mono animate-pulse">
                      <Clock className="w-4 h-4 text-amber-400" />
                      <span>{simulatingExit} closed. 2-second exit grace timer counting down...</span>
                    </div>
                  )}
                </div>

                {/* Windows 11 Toast Simulator Display */}
                <div className="h-full flex items-center justify-center p-4 bg-zinc-900/40 rounded-xl border border-zinc-800/80 min-h-[300px] relative">
                  {showToast ? (
                    <div className="w-full max-w-sm rounded-xl bg-zinc-900/95 border border-emerald-500/50 p-4 shadow-2xl backdrop-blur-xl animate-in fade-in slide-in-from-bottom-4 duration-300">
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <div className="w-6 h-6 rounded bg-emerald-500 flex items-center justify-center text-zinc-950">
                            <BellRing className="w-3.5 h-3.5" />
                          </div>
                          <div>
                            <div className="text-xs font-bold text-zinc-100">CommitMaster Reminder</div>
                            <div className="text-[10px] text-zinc-400 font-mono">Windows 11 Notification Shield</div>
                          </div>
                        </div>
                        <button 
                          onClick={() => setShowToast(false)}
                          className="text-zinc-500 hover:text-zinc-300"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>

                      <p className="text-xs text-zinc-300 mb-3 leading-snug">
                        There are files which haven't been committed in <strong className="text-emerald-400">[{toastRepo}]</strong>. Would you like to review and generate a commit now?
                      </p>

                      <div className="flex gap-2">
                        <button 
                          onClick={() => { setActiveTab('ai-diff'); setShowToast(false); }}
                          className="flex-1 py-1.5 px-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-bold text-xs text-center transition-colors"
                        >
                          Review & Commit
                        </button>
                        <button 
                          onClick={() => setShowToast(false)}
                          className="py-1.5 px-3 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs transition-colors"
                        >
                          Dismiss
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="text-center text-zinc-500 text-xs">
                      <BellRing className="w-8 h-8 mx-auto mb-2 opacity-30" />
                      <div>Click "Simulate Exit" on any IDE to test the 2-second reminder</div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: PRE-COMMIT SECURITY INSPECTOR */}
          {activeTab === 'security' && (
            <div className="p-6 sm:p-8">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-center">
                <div>
                  <h3 className="text-lg font-bold text-zinc-100 mb-2">Pre-Commit Health & Vulnerability Inspector</h3>
                  <p className="text-xs text-zinc-400 mb-6 leading-relaxed">
                    CommitMaster validates AST syntax for Python, JSON, and YAML, blocks unresolved merge conflict markers, and searches for CWE-798 hardcoded credentials before git staging.
                  </p>

                  <div className="space-y-3 mb-6">
                    <label className="flex items-center gap-3 p-3 rounded-xl border border-zinc-800 bg-zinc-900/40 text-xs cursor-pointer hover:bg-zinc-900/60">
                      <input 
                        type="checkbox" 
                        checked={hasSecret} 
                        onChange={(e) => setHasSecret(e.target.checked)} 
                        className="rounded border-zinc-700 text-emerald-500 focus:ring-0" 
                      />
                      <div>
                        <div className="font-semibold text-zinc-200">Include Hardcoded Secret (CWE-798)</div>
                        <div className="text-zinc-500 text-[11px] font-mono">e.g. ghp_49819283921093120391209310</div>
                      </div>
                    </label>

                    <label className="flex items-center gap-3 p-3 rounded-xl border border-zinc-800 bg-zinc-900/40 text-xs cursor-pointer hover:bg-zinc-900/60">
                      <input 
                        type="checkbox" 
                        checked={hasSyntaxError} 
                        onChange={(e) => setHasSyntaxError(e.target.checked)} 
                        className="rounded border-zinc-700 text-emerald-500 focus:ring-0" 
                      />
                      <div>
                        <div className="font-semibold text-zinc-200">Include Broken Python AST Syntax</div>
                        <div className="text-zinc-500 text-[11px] font-mono">e.g. Unclosed parentheses or invalid def syntax</div>
                      </div>
                    </label>
                  </div>

                  <button
                    onClick={handleRunInspection}
                    disabled={inspecting}
                    className="w-full flex items-center justify-center gap-2 py-3 px-4 rounded-xl bg-zinc-100 hover:bg-white text-zinc-950 font-bold text-xs transition-colors"
                  >
                    {inspecting ? (
                      <RefreshCw className="w-4 h-4 animate-spin text-zinc-950" />
                    ) : (
                      <ShieldCheck className="w-4 h-4 text-emerald-600" />
                    )}
                    <span>Run Pre-Commit Inspection Audit</span>
                  </button>
                </div>

                {/* Audit Verdict Box */}
                <div className="p-6 rounded-xl border border-zinc-800 bg-zinc-900/50 min-h-[260px] flex flex-col justify-center">
                  {inspectVerdict ? (
                    <div className={`p-4 rounded-xl border ${
                      inspectVerdict.status === 'BLOCKED'
                        ? 'border-red-500/40 bg-red-950/20 text-red-200'
                        : 'border-emerald-500/40 bg-emerald-950/20 text-emerald-200'
                    }`}>
                      <div className="flex items-center gap-2 font-bold text-sm mb-2">
                        {inspectVerdict.status === 'BLOCKED' ? (
                          <AlertTriangle className="w-5 h-5 text-red-400" />
                        ) : (
                          <ShieldCheck className="w-5 h-5 text-emerald-400" />
                        )}
                        <span>{inspectVerdict.status}: {inspectVerdict.rule}</span>
                      </div>
                      <p className="text-xs leading-relaxed text-zinc-300">
                        {inspectVerdict.details}
                      </p>
                    </div>
                  ) : (
                    <div className="text-center text-zinc-500 text-xs">
                      <ShieldAlert className="w-8 h-8 mx-auto mb-2 opacity-30" />
                      <div>Toggle flags on the left and click "Run Pre-Commit Inspection Audit"</div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: OFFLINE AI COMMIT GENERATOR */}
          {activeTab === 'ai-diff' && (
            <div className="p-6 sm:p-8">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
                <div>
                  <h3 className="text-lg font-bold text-zinc-100 mb-2">100% Offline AI Conventional Commits</h3>
                  <p className="text-xs text-zinc-400 mb-6 leading-relaxed">
                    CommitMaster analyzes git diffs on your local machine using LM Studio or Ollama. Code is never uploaded to external servers. If the model is offline, the AST heuristic engine produces a compliant Conventional Commit fallback.
                  </p>

                  <div className="mb-4">
                    <div className="text-xs font-semibold text-zinc-300 mb-2">Select Provider:</div>
                    <div className="grid grid-cols-3 gap-2">
                      {[
                        { id: 'lmstudio', name: 'LM Studio', type: 'Local (127.0.0.1)' },
                        { id: 'ollama', name: 'Ollama', type: 'Local (11434)' },
                        { id: 'heuristic', name: 'AST Heuristic', type: 'Zero-AI Offline' }
                      ].map(p => (
                        <button
                          key={p.id}
                          onClick={() => setAiProvider(p.id)}
                          className={`p-2.5 rounded-xl border text-left text-xs transition-all ${
                            aiProvider === p.id
                              ? 'border-emerald-500/70 bg-emerald-950/40 text-emerald-300'
                              : 'border-zinc-800 bg-zinc-900/40 text-zinc-400 hover:bg-zinc-800/40'
                          }`}
                        >
                          <div className="font-semibold text-zinc-200">{p.name}</div>
                          <div className="text-[10px] text-zinc-500">{p.type}</div>
                        </button>
                      ))}
                    </div>
                  </div>

                  <button
                    onClick={handleGenerateAiCommit}
                    disabled={generatingAi}
                    className="w-full flex items-center justify-center gap-2 py-3 px-4 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-bold text-xs transition-colors shadow-lg shadow-emerald-500/20"
                  >
                    {generatingAi ? (
                      <RefreshCw className="w-4 h-4 animate-spin" />
                    ) : (
                      <Sparkles className="w-4 h-4" />
                    )}
                    <span>Generate Commit from Active Diff</span>
                  </button>
                </div>

                {/* AI Output Terminal Box */}
                <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4 font-mono text-xs">
                  <div className="flex items-center justify-between border-b border-zinc-800 pb-2 mb-3">
                    <span className="text-zinc-500">commitmaster-ai --summarize-diff</span>
                    <span className="text-[10px] text-emerald-400">{aiResult.provider}</span>
                  </div>

                  <div className="text-zinc-400 mb-3">
                    <span className="text-emerald-400 font-bold">{'> git commit -m '}</span>
                    <span className="text-zinc-100 font-semibold">"{aiResult.title}"</span>
                  </div>

                  <div className="p-3 rounded-lg bg-zinc-900/60 border border-zinc-800/80 text-zinc-300 whitespace-pre-line text-[11px] leading-relaxed">
                    {aiResult.description}
                  </div>

                  <div className="mt-3 flex items-center gap-2 text-[10px] text-zinc-500">
                    <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                    <span>0 bytes uploaded. Processed strictly on host CPU/GPU.</span>
                  </div>
                </div>
              </div>
            </div>
          )}

        </div>

      </div>
    </section>
  );
}
