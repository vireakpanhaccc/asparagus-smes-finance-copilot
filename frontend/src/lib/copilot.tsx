"use client";

// Chat state shared by the docked bot on Overview and the full-screen /copilot page,
// so the conversation survives moving between pages.

import { createContext, useContext, useState, type ReactNode } from "react";
import { apiPost, type ApprovalCard, type ChatResponse, type RescuePlan } from "@/lib/api";

export type Msg = {
  role: "user" | "assistant" | "system";
  text: string;
  cards?: ApprovalCard[];
  plan?: RescuePlan | null;
};

export type TraceStep = ChatResponse["tool_trace"][number];

export const RESCUE_PROMPT = "Build a rescue plan for my cash shortfall and prepare the actions.";

type Ctx = {
  messages: Msg[];
  trace: TraceStep[];
  busy: boolean;
  open: boolean;
  setOpen: (v: boolean) => void;
  send: (text: string) => Promise<void>;
  addSystem: (text: string) => void;
};

const CopilotContext = createContext<Ctx | null>(null);

export function CopilotProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [trace, setTrace] = useState<TraceStep[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);

  async function send(text: string) {
    if (!text.trim() || busy) return;
    setOpen(true);
    setMessages((m) => [...m, { role: "user", text }]);
    setBusy(true);
    try {
      const res = await apiPost<ChatResponse>("/chat", {
        message: text,
        conversation_id: conversationId,
      });
      setConversationId(res.conversation_id);
      setTrace((tr) => [...tr, ...res.tool_trace]);
      setMessages((m) => [
        ...m,
        { role: "assistant", text: res.reply, cards: res.approval_cards, plan: res.plan },
      ]);
    } catch (e) {
      setMessages((m) => [...m, { role: "system", text: `Error: ${(e as Error).message}` }]);
    } finally {
      setBusy(false);
    }
  }

  const addSystem = (text: string) => setMessages((m) => [...m, { role: "system", text }]);

  return (
    <CopilotContext.Provider value={{ messages, trace, busy, open, setOpen, send, addSystem }}>
      {children}
    </CopilotContext.Provider>
  );
}

export function useCopilot(): Ctx {
  const ctx = useContext(CopilotContext);
  if (!ctx) throw new Error("useCopilot must be used inside CopilotProvider");
  return ctx;
}
