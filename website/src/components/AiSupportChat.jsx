import React, { useState, useRef, useEffect } from 'react';
import { 
  MessageSquare, Sparkles, X, Send, Bot, User, CornerDownLeft, 
  HelpCircle, ArrowRight, ShieldCheck, Ticket
} from 'lucide-react';
import { AI_KNOWLEDGE, QUICK_SUGGESTIONS } from '../data/aiKnowledge';

export default function AiSupportChat({ isOpen, onClose, onOpenTicketWithContext }) {
  const [messages, setMessages] = useState([
    {
      id: 'msg-1',
      sender: 'bot',
      text: "👋 Hi! I'm the **CommitMaster Support Assistant**. How can I help you today? Ask me about configuring LM Studio/Ollama, setting up multi-IDE notifications, GitHub push security, or troubleshooting Windows toasts."
    }
  ]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
    }
  }, [messages, isOpen]);

  const findBestAnswer = (query) => {
    const q = query.toLowerCase();

    // Check knowledge base
    let bestMatch = null;
    let maxScore = 0;

    for (const item of AI_KNOWLEDGE) {
      let score = 0;
      for (const kw of item.keywords) {
        if (q.includes(kw)) score += 2;
      }
      if (score > maxScore) {
        maxScore = score;
        bestMatch = item;
      }
    }

    if (bestMatch && maxScore >= 2) {
      return bestMatch.answer;
    }

    // Default intelligent fallbacks
    if (q.includes('price') || q.includes('cost') || q.includes('free') || q.includes('license')) {
      return "CommitMaster is released under the **MIT Open-Source License**. The source code, local SQLite engine, and standalone direct packages are completely free. If you find it valuable, you can support development via the Microsoft Store version!";
    }

    if (q.includes('mac') || q.includes('linux') || q.includes('apple')) {
      return "Currently, CommitMaster is crafted exclusively for **Windows 11 and Windows 10 (x64)** to take full native advantage of Fluent procedural textures, the Windows Process Tree API, and Windows Notification Shields. A cross-platform Electron/Tauri port is on the future roadmap!";
    }

    return "That's a great question! While CommitMaster's primary documentation covers local AI endpoints (LM Studio/Ollama), multi-IDE monitoring, and CWE-798 secret scanning, you can also open a support ticket or share an insight directly with Saumya Patel using the **'Create Ticket'** button below.";
  };

  const handleSend = (userText = null) => {
    const textToSend = userText || input;
    if (!textToSend.trim()) return;

    const userMsg = {
      id: 'usr-' + Date.now(),
      sender: 'user',
      text: textToSend
    };

    setMessages(prev => [...prev, userMsg]);
    if (!userText) setInput('');
    setIsTyping(true);

    setTimeout(() => {
      const reply = findBestAnswer(textToSend);
      setMessages(prev => [
        ...prev,
        {
          id: 'bot-' + Date.now(),
          sender: 'bot',
          text: reply
        }
      ]);
      setIsTyping(false);
    }, 600);
  };

  const handleQuickChip = (suggestion) => {
    handleSend(suggestion);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed bottom-6 right-6 z-50 w-full max-w-md sm:w-[420px] h-[580px] rounded-2xl glass-card border border-emerald-500/40 shadow-2xl flex flex-col overflow-hidden animate-in fade-in slide-in-from-bottom-6 duration-200">
      
      {/* Chat Header */}
      <div className="p-4 bg-zinc-900/90 border-b border-zinc-800 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400">
            <Bot className="w-4 h-4" />
          </div>
          <div>
            <div className="text-xs font-bold text-zinc-100 flex items-center gap-1.5">
              <span>CommitMaster AI Support</span>
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            </div>
            <div className="text-[10px] text-zinc-400 font-mono">100% Automated RAG Assistant</div>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={() => onOpenTicketWithContext(messages[messages.length - 1]?.text)}
            className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-400 hover:text-amber-300 transition-colors"
            title="Escalate to Support Ticket"
          >
            <Ticket className="w-4 h-4" />
          </button>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-400 hover:text-zinc-100 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Messages Scroll Area */}
      <div className="flex-1 p-4 overflow-y-auto space-y-3.5 text-xs">
        {messages.map(m => (
          <div
            key={m.id}
            className={`flex gap-2.5 ${m.sender === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {m.sender === 'bot' && (
              <div className="w-6 h-6 rounded-md bg-emerald-950/60 border border-emerald-800/40 flex items-center justify-center text-emerald-400 flex-shrink-0 mt-0.5">
                <Sparkles className="w-3.5 h-3.5" />
              </div>
            )}

            <div
              className={`max-w-[85%] rounded-xl p-3 leading-relaxed ${
                m.sender === 'user'
                  ? 'bg-emerald-500 text-zinc-950 font-medium'
                  : 'bg-zinc-900/90 text-zinc-200 border border-zinc-800'
              }`}
            >
              <div className="whitespace-pre-line">
                {m.text}
              </div>

              {m.sender === 'bot' && m.id !== 'msg-1' && (
                <div className="mt-3 pt-2 border-t border-zinc-800/60 flex items-center justify-between text-[10px] text-zinc-400">
                  <span>Helpful?</span>
                  <button
                    onClick={() => onOpenTicketWithContext(m.text)}
                    className="text-amber-400 hover:underline flex items-center gap-1"
                  >
                    <Ticket className="w-3 h-3" /> Still need help? Open Ticket
                  </button>
                </div>
              )}
            </div>

            {m.sender === 'user' && (
              <div className="w-6 h-6 rounded-md bg-zinc-800 flex items-center justify-center text-zinc-300 flex-shrink-0 mt-0.5">
                <User className="w-3.5 h-3.5" />
              </div>
            )}
          </div>
        ))}

        {isTyping && (
          <div className="flex gap-2 items-center text-zinc-500 text-xs font-mono">
            <Sparkles className="w-3 h-3 text-emerald-400 animate-spin" />
            <span>Consulting knowledge base...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Quick Questions */}
      <div className="px-3 py-2 bg-zinc-950/90 border-t border-zinc-900 flex gap-1.5 overflow-x-auto no-scrollbar">
        {QUICK_SUGGESTIONS.slice(0, 3).map((s, idx) => (
          <button
            key={idx}
            onClick={() => handleQuickChip(s)}
            className="flex-shrink-0 px-2.5 py-1 rounded-full bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-[11px] text-zinc-300 hover:text-emerald-300 transition-colors"
          >
            {s}
          </button>
        ))}
      </div>

      {/* Input Field */}
      <div className="p-3 bg-zinc-900/95 border-t border-zinc-800">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex items-center gap-2"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask anything about CommitMaster..."
            className="flex-1 bg-zinc-950 border border-zinc-800 rounded-xl px-3 py-2 text-xs text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500/60"
          />
          <button
            type="submit"
            disabled={!input.trim()}
            className="p-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-zinc-950 disabled:opacity-40 disabled:hover:bg-emerald-500 transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>

    </div>
  );
}
