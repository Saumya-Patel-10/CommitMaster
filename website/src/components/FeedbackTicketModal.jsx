import React, { useState } from 'react';
import { 
  X, Send, Bug, Lightbulb, MessageSquare, Check, Copy, 
  Upload, AlertCircle, Laptop, Cpu, CheckCircle2, Sparkles 
} from 'lucide-react';
import confetti from 'canvas-confetti';

export default function FeedbackTicketModal({ isOpen, onClose, initialContext = '' }) {
  const [tab, setTab] = useState('bug'); // 'bug' | 'feature' | 'feedback'
  const [email, setEmail] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState(initialContext ? `Issue context from AI Support:\n${initialContext}` : '');
  const [appVersion, setAppVersion] = useState('v3.0.1.0');
  const [osBuild, setOsBuild] = useState('Windows 11 24H2 (x64)');
  const [aiEngine, setAiEngine] = useState('LM Studio (Local)');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submittedTicket, setSubmittedTicket] = useState(null);
  const [copiedTicketId, setCopiedTicketId] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!email || !title || !description) return;

    setIsSubmitting(true);
    setTimeout(() => {
      setIsSubmitting(false);
      const ticketId = 'CM-' + Math.floor(1000 + Math.random() * 9000);
      setSubmittedTicket({
        id: ticketId,
        type: tab,
        title,
        email,
        timestamp: new Date().toLocaleTimeString(),
        estimatedTime: 'Under 24 hours'
      });

      // Celebration
      try {
        confetti({
          particleCount: 70,
          spread: 60,
          origin: { y: 0.7 }
        });
      } catch (err) {
        // ignore if not supported
      }
    }, 700);
  };

  const copyTicketId = () => {
    if (!submittedTicket) return;
    navigator.clipboard.writeText(submittedTicket.id);
    setCopiedTicketId(true);
    setTimeout(() => setCopiedTicketId(false), 2000);
  };

  const handleReset = () => {
    setSubmittedTicket(null);
    setTitle('');
    setDescription('');
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-xl rounded-2xl glass-card border border-zinc-700/80 shadow-2xl overflow-hidden bg-zinc-950/95">
        
        {/* Header */}
        <div className="p-5 border-b border-zinc-800 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400">
              <MessageSquare className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-zinc-100">
                CommitMaster Support Desk & Feedback
              </h3>
              <p className="text-[11px] text-zinc-400 font-mono">Direct ticket dispatch to Saumya Patel</p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-400 hover:text-zinc-100 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6">
          {submittedTicket ? (
            /* SUCCESS STATE */
            <div className="text-center py-6">
              <div className="w-12 h-12 rounded-full bg-emerald-500/20 border border-emerald-500/40 text-emerald-400 flex items-center justify-center mx-auto mb-4">
                <CheckCircle2 className="w-6 h-6" />
              </div>

              <h4 className="text-lg font-bold text-zinc-100 mb-1">
                Ticket Successfully Dispatched!
              </h4>
              <p className="text-xs text-zinc-400 max-w-sm mx-auto mb-6">
                We've logged your ticket and sent a confirmation receipt to <strong className="text-zinc-200">{submittedTicket.email}</strong>.
              </p>

              {/* Ticket ID Card */}
              <div className="p-4 rounded-xl bg-zinc-900 border border-zinc-800 inline-flex flex-col items-center gap-2 mb-8">
                <span className="text-[10px] font-mono uppercase text-zinc-500 tracking-wider">Your Tracking Reference</span>
                <div className="flex items-center gap-3">
                  <span className="text-xl font-mono font-extrabold text-emerald-400 tracking-wider">
                    #{submittedTicket.id}
                  </span>
                  <button
                    onClick={copyTicketId}
                    className="p-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white transition-colors"
                    title="Copy Ticket ID"
                  >
                    {copiedTicketId ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
                  </button>
                </div>
                <span className="text-[10px] text-zinc-500 font-mono">Expected Response: {submittedTicket.estimatedTime}</span>
              </div>

              <div>
                <button
                  onClick={handleReset}
                  className="px-6 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-bold text-xs transition-colors"
                >
                  Done
                </button>
              </div>
            </div>
          ) : (
            /* SUBMISSION FORM */
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Category Tab Selector */}
              <div className="grid grid-cols-3 gap-2">
                {[
                  { id: 'bug', label: 'Report Bug', icon: Bug, color: 'text-red-400' },
                  { id: 'feature', label: 'Feature Insight', icon: Lightbulb, color: 'text-amber-400' },
                  { id: 'feedback', label: 'General Feedback', icon: MessageSquare, color: 'text-cyan-400' }
                ].map(item => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setTab(item.id)}
                    className={`flex items-center justify-center gap-1.5 p-2 rounded-xl border text-xs font-medium transition-all ${
                      tab === item.id
                        ? 'border-emerald-500/60 bg-emerald-950/40 text-emerald-300'
                        : 'border-zinc-800 bg-zinc-900/40 text-zinc-400 hover:bg-zinc-800/40'
                    }`}
                  >
                    <item.icon className={`w-3.5 h-3.5 ${item.color}`} />
                    <span>{item.label}</span>
                  </button>
                ))}
              </div>

              {/* Title Input */}
              <div>
                <label className="block text-[11px] font-mono text-zinc-400 uppercase tracking-wider mb-1">
                  Subject / Summary
                </label>
                <input
                  type="text"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder={tab === 'bug' ? 'e.g. Cursor.exe notification not triggering after closing' : 'e.g. Add support for Windsurf IDE'}
                  className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-3 py-2 text-xs text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500/60"
                />
              </div>

              {/* Email Input */}
              <div>
                <label className="block text-[11px] font-mono text-zinc-400 uppercase tracking-wider mb-1">
                  Your Developer Email (for reply)
                </label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="developer@company.com"
                  className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-3 py-2 text-xs text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500/60"
                />
              </div>

              {/* System Metadata Helper Strip */}
              <div className="grid grid-cols-3 gap-2 p-2.5 rounded-xl bg-zinc-900/60 border border-zinc-800/80 text-[11px] font-mono">
                <div>
                  <span className="text-zinc-500 block text-[9px]">APP VERSION</span>
                  <select 
                    value={appVersion} 
                    onChange={(e) => setAppVersion(e.target.value)}
                    className="bg-transparent text-zinc-300 focus:outline-none cursor-pointer"
                  >
                    <option value="v3.0.1.0">v3.0.1 (Store)</option>
                    <option value="v3.0.0.0">v3.0.0 (Direct)</option>
                    <option value="v2.5.0">v2.5 (Legacy)</option>
                  </select>
                </div>

                <div>
                  <span className="text-zinc-500 block text-[9px]">OS BUILD</span>
                  <span className="text-zinc-300 truncate block">Win 11 x64</span>
                </div>

                <div>
                  <span className="text-zinc-500 block text-[9px]">AI PROVIDER</span>
                  <select 
                    value={aiEngine} 
                    onChange={(e) => setAiEngine(e.target.value)}
                    className="bg-transparent text-zinc-300 focus:outline-none cursor-pointer"
                  >
                    <option value="LM Studio">LM Studio</option>
                    <option value="Ollama">Ollama</option>
                    <option value="AST Heuristics">AST Fallback</option>
                    <option value="OpenAI / Claude">Cloud AI</option>
                  </select>
                </div>
              </div>

              {/* Description Input */}
              <div>
                <label className="block text-[11px] font-mono text-zinc-400 uppercase tracking-wider mb-1">
                  Detailed Description & Steps
                </label>
                <textarea
                  rows={4}
                  required
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Describe what occurred, steps to reproduce, or the feature workflow you'd love to see..."
                  className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-3 py-2 text-xs text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500/60 resize-none font-mono"
                />
              </div>

              {/* Privacy Notice */}
              <div className="flex items-center gap-2 text-[10px] text-zinc-500">
                <AlertCircle className="w-3.5 h-3.5 text-zinc-500 flex-shrink-0" />
                <span>Never share passwords or unredacted API keys. Logs are kept strictly confidential.</span>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 rounded-xl text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-bold text-xs transition-colors shadow-lg shadow-emerald-500/20 disabled:opacity-50"
                >
                  {isSubmitting ? (
                    <span>Dispatching...</span>
                  ) : (
                    <>
                      <Send className="w-3.5 h-3.5" />
                      <span>Submit Ticket</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          )}
        </div>

      </div>
    </div>
  );
}
