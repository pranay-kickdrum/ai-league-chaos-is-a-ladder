import { useRef, useEffect, useState, KeyboardEvent } from 'react';
import { Send } from 'lucide-react';
import ChatMessage from './ChatMessage';
import ApprovalCard from './ApprovalCard';
import type { ChatMessage as ChatMessageType, CheckpointData, ResearchFlight, ResearchHotel } from '../../types';

interface ChatPanelProps {
  messages: ChatMessageType[];
  checkpoint?: CheckpointData;
  onSend: (text: string) => void;
  onCheckpointAction: (action: string, metadata?: Record<string, string>) => void;
  disabled?: boolean;
  initialPrompt?: string;
  selectedTransport?: ResearchFlight;
  selectedHotel?: ResearchHotel;
}

export default function ChatPanel({
  messages,
  checkpoint,
  onSend,
  onCheckpointAction,
  disabled,
  initialPrompt,
  selectedTransport,
  selectedHotel,
}: ChatPanelProps) {
  const [input, setInput] = useState(initialPrompt ?? '');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, checkpoint]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || disabled) return;
    onSend(text);
    setInput('');
  };

  const handleKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-1">
        {messages.length === 0 && (
          <div className="text-center py-12 text-slate-400">
            <p className="text-lg mb-1">Where would you like to go?</p>
            <p className="text-sm">Tell me about your dream trip!</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <ChatMessage key={i} message={msg} />
        ))}
        {checkpoint && (
          <ApprovalCard
            checkpoint={checkpoint}
            onAction={onCheckpointAction}
            selectedTransport={selectedTransport}
            selectedHotel={selectedHotel}
          />
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="border-t border-slate-200 p-3 bg-white">
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder={disabled ? 'Waiting...' : 'Type your message...'}
            disabled={disabled}
            className="flex-1 px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-ocean/30 focus:border-ocean disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={disabled || !input.trim()}
            className="p-2.5 bg-sunset text-white rounded-xl hover:bg-orange-600 disabled:opacity-50 disabled:hover:bg-sunset transition"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
