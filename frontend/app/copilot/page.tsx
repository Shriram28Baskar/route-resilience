"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Send, Bot, User, Sparkles, RefreshCw, Network } from "lucide-react";
import { chatWithCopilot } from "@/lib/api";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

const STARTERS = [
  "Which nodes are most critical to Bengaluru's road network?",
  "What happens if the top-3 gatekeeper nodes flood simultaneously?",
  "How does MST healing improve network connectivity?",
  "Which areas would lose hospital access if the main arterial is blocked?",
  "Explain the Resilience Index and what a score below 0.7 means.",
  "What infrastructure investments would most improve network resilience?",
];

export default function CopilotPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = useCallback(async (text?: string) => {
    const content = (text ?? input).trim();
    if (!content || loading) return;

    const userMsg: Message = { id: Date.now().toString(), role: "user", content, timestamp: new Date() };
    setMessages(prev => [...prev, userMsg]);
    setInput("");
    setLoading(true);
    setError(null);

    const history = messages.map(m => ({ role: m.role, content: m.content }));

    try {
      const res = await chatWithCopilot(content, history);
      const assistantMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: res.reply,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, assistantMsg]);
    } catch (e: any) {
      setError(e.message);
      setMessages(prev => prev.slice(0, -1)); // remove optimistic user msg
    } finally {
      setLoading(false);
    }
  }, [input, loading, messages]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };

  const clear = () => { setMessages([]); setError(null); };

  return (
    <div className="h-screen flex flex-col bg-[#0B0F1A]">
      {/* Header */}
      <div className="border-b border-white/8 bg-[#111827] px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-[#00E5B4]/10 flex items-center justify-center">
            <Sparkles className="w-4 h-4 text-[#00E5B4]" />
          </div>
          <div>
            <h1 className="font-display font-semibold text-sm">Urban Planning Copilot</h1>
            <p className="text-xs text-[#6B7280]">Grounded in live graph metrics via Groq LLaMA-3 70B</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 text-xs text-[#22C55E] bg-[#22C55E]/10 px-2 py-1 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-[#22C55E]" />
            Context-aware
          </div>
          <button onClick={clear} className="p-2 text-[#6B7280] hover:text-white rounded-lg hover:bg-white/5 transition-colors">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {messages.length === 0 && (
          <div className="max-w-2xl mx-auto">
            {/* Welcome */}
            <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
              className="text-center mb-10">
              <div className="w-14 h-14 rounded-2xl bg-[#00E5B4]/10 flex items-center justify-center mx-auto mb-4">
                <Network className="w-7 h-7 text-[#00E5B4]" />
              </div>
              <h2 className="font-display text-xl font-bold mb-2">Ask about your road network</h2>
              <p className="text-[#6B7280] text-sm max-w-md mx-auto">
                I have access to live graph metrics, centrality scores, simulation results, and hospital accessibility data for your AOI.
              </p>
            </motion.div>

            {/* Starter prompts */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {STARTERS.map((s, i) => (
                <motion.button
                  key={i}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.05 }}
                  onClick={() => send(s)}
                  className="text-left p-4 bg-[#111827] border border-white/8 rounded-xl text-sm text-[#6B7280] hover:text-white hover:border-[#00E5B4]/20 hover:bg-[#1C2333] transition-all"
                >
                  {s}
                </motion.button>
              ))}
            </div>
          </div>
        )}

        <div className="max-w-3xl mx-auto space-y-4 w-full">
          <AnimatePresence initial={false}>
            {messages.map(msg => (
              <motion.div
                key={msg.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}
              >
                {/* Avatar */}
                <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
                  msg.role === "user" ? "bg-[#00E5B4]/15" : "bg-[#1C2333] border border-white/8"
                }`}>
                  {msg.role === "user"
                    ? <User className="w-4 h-4 text-[#00E5B4]" />
                    : <Bot className="w-4 h-4 text-[#6B7280]" />}
                </div>

                {/* Bubble */}
                <div className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                  msg.role === "user"
                    ? "bg-[#00E5B4]/10 border border-[#00E5B4]/15 text-white rounded-tr-sm"
                    : "bg-[#111827] border border-white/8 text-[#E5E7EB] rounded-tl-sm"
                }`}>
                  <MessageContent content={msg.content} />
                  <div className="text-xs text-[#6B7280] mt-2">
                    {msg.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </div>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>

          {/* Loading indicator */}
          {loading && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-3">
              <div className="w-8 h-8 rounded-full bg-[#1C2333] border border-white/8 flex items-center justify-center shrink-0">
                <Bot className="w-4 h-4 text-[#6B7280]" />
              </div>
              <div className="bg-[#111827] border border-white/8 rounded-2xl rounded-tl-sm px-4 py-3">
                <div className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#00E5B4] animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-[#00E5B4] animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-[#00E5B4] animate-bounce" style={{ animationDelay: "300ms" }} />
                </div>
              </div>
            </motion.div>
          )}
        </div>

        <div ref={bottomRef} />
      </div>

      {error && (
        <div className="mx-auto max-w-3xl w-full px-4 mb-2">
          <div className="bg-[#FF4444]/10 border border-[#FF4444]/20 rounded-xl px-4 py-3 text-[#FF4444] text-xs">{error}</div>
        </div>
      )}

      {/* Input area */}
      <div className="border-t border-white/8 bg-[#111827] p-4">
        <div className="max-w-3xl mx-auto flex items-end gap-3">
          <div className="flex-1 bg-[#0B0F1A] border border-white/8 rounded-xl px-4 py-3 focus-within:border-[#00E5B4]/30 transition-colors">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={e => { setInput(e.target.value); e.target.style.height = "auto"; e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`; }}
              onKeyDown={handleKeyDown}
              placeholder="Ask about network criticality, disaster scenarios, infrastructure priorities…"
              className="w-full bg-transparent text-white text-sm resize-none outline-none placeholder:text-[#6B7280] max-h-40 min-h-[24px]"
              rows={1}
            />
          </div>
          <button
            onClick={() => send()}
            disabled={!input.trim() || loading}
            className="w-11 h-11 bg-[#00E5B4] text-[#0B0F1A] rounded-xl flex items-center justify-center hover:bg-[#00B38A] transition-colors disabled:opacity-40 shrink-0"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
        <p className="text-center text-xs text-[#6B7280] mt-2">
          Shift+Enter for new line · Enter to send · Context injected from live graph state
        </p>
      </div>
    </div>
  );
}

// Render markdown-ish formatting for assistant messages
function MessageContent({ content }: { content: string }) {
  // Basic bold + code formatting
  const parts = content.split(/(`[^`]+`|\*\*[^*]+\*\*)/g);
  return (
    <div className="space-y-2">
      {content.split("\n\n").map((para, i) => (
        <p key={i} className="leading-relaxed">
          {para.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).map((chunk, j) => {
            if (chunk.startsWith("`") && chunk.endsWith("`")) {
              return <code key={j} className="bg-white/8 px-1 py-0.5 rounded text-xs font-mono text-[#00E5B4]">{chunk.slice(1, -1)}</code>;
            }
            if (chunk.startsWith("**") && chunk.endsWith("**")) {
              return <strong key={j} className="font-semibold text-white">{chunk.slice(2, -2)}</strong>;
            }
            return <span key={j}>{chunk}</span>;
          })}
        </p>
      ))}
    </div>
  );
}
