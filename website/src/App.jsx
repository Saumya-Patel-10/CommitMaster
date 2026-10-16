import React, { useState } from 'react';
import Navbar from './components/Navbar';
import Hero from './components/Hero';
import InteractiveDemo from './components/InteractiveDemo';
import DownloadSection from './components/DownloadSection';
import ArchitectureSpecs from './components/ArchitectureSpecs';
import DocsFaq from './components/DocsFaq';
import Footer from './components/Footer';
import AiSupportChat from './components/AiSupportChat';
import FeedbackTicketModal from './components/FeedbackTicketModal';
import { Sparkles, MessageSquare } from 'lucide-react';

export default function App() {
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [isTicketModalOpen, setIsTicketModalOpen] = useState(false);
  const [ticketContext, setTicketContext] = useState('');

  const handleOpenTicketWithContext = (contextText) => {
    setTicketContext(contextText || '');
    setIsTicketModalOpen(true);
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col relative bg-grid-pattern">
      {/* Top Navigation */}
      <Navbar 
        onOpenFeedback={() => setIsTicketModalOpen(true)}
        onOpenChat={() => setIsChatOpen(true)}
      />

      {/* Main Sections */}
      <main className="flex-1">
        <Hero 
          onOpenChat={() => setIsChatOpen(true)}
        />
        
        <InteractiveDemo />

        <DownloadSection />

        <ArchitectureSpecs />

        <DocsFaq 
          onOpenChat={() => setIsChatOpen(true)}
        />
      </main>

      {/* Footer */}
      <Footer 
        onOpenFeedback={() => setIsTicketModalOpen(true)}
        onOpenChat={() => setIsChatOpen(true)}
      />

      {/* Floating Action Button (FAB) for AI Support & Ticket */}
      <div className="fixed bottom-6 right-6 z-40 flex items-center gap-3">
        {/* Ticket Desk Quick Trigger */}
        <button
          onClick={() => setIsTicketModalOpen(true)}
          className="p-3 rounded-full bg-zinc-900/90 hover:bg-zinc-800 border border-zinc-700/80 text-amber-400 shadow-xl backdrop-blur-md transition-all hover:scale-105"
          title="Open Ticket / Suggest Insight"
        >
          <MessageSquare className="w-5 h-5" />
        </button>

        {/* AI Support Chat Floating Trigger */}
        {!isChatOpen && (
          <button
            onClick={() => setIsChatOpen(true)}
            className="flex items-center gap-2.5 px-4 py-3 rounded-full bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-bold text-xs shadow-2xl shadow-emerald-500/30 transition-all hover:scale-105 group"
          >
            <Sparkles className="w-4 h-4 text-zinc-950 group-hover:rotate-12 transition-transform" />
            <span>AI Support</span>
            <span className="w-2 h-2 rounded-full bg-zinc-950 animate-ping" />
          </button>
        )}
      </div>

      {/* Automated AI Support Chat Widget Modal */}
      <AiSupportChat
        isOpen={isChatOpen}
        onClose={() => setIsChatOpen(false)}
        onOpenTicketWithContext={handleOpenTicketWithContext}
      />

      {/* Feedback & Support Ticket Desk Modal */}
      <FeedbackTicketModal
        isOpen={isTicketModalOpen}
        onClose={() => {
          setIsTicketModalOpen(false);
          setTicketContext('');
        }}
        initialContext={ticketContext}
      />
    </div>
  );
}
