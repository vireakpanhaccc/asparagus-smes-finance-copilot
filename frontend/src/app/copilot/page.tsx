"use client";

import { useEffect, useRef, useState } from "react";
import ApprovalCard from "@/components/ApprovalCard";
import RescuePlanCard from "@/components/RescuePlanCard";
import TierBadge from "@/components/TierBadge";
import { apiPost, type ApprovalCard as Card, type ChatResponse, type RescuePlan } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type Msg = {
  role: "user" | "assistant" | "system";
  text: string;
  cards?: Card[];
  plan?: RescuePlan | null;
};

const RESCUE_PROMPT = "Build a rescue plan for my cash shortfall and prepare the actions.";
const SUGGESTIONS = [
  RESCUE_PROMPT,
  "I'm worried about December. Can I cover rent and payroll?",
  "Which customers pay late?",
  "Why are supplier costs up?",
];

export default function CopilotPage() {
  const { t } = useI18n();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [trace, setTrace] = useState<ChatResponse["tool_trace"]>([]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const autoAsked = useRef(false);

  // The Overview banner links here with ?ask=rescue to start the plan straight away.
  useEffect(() => {
    if (autoAsked.current) return; // React strict mode runs effects twice in dev
    autoAsked.current = true;
    if (new URLSearchParams(window.location.search).get("ask") === "rescue") send(RESCUE_PROMPT);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function send(text: string) {
    if (!text.trim()) return;
    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
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

  return (
    <div className="grid max-w-6xl gap-5 lg:grid-cols-3">
      <section className="card flex min-h-[70vh] flex-col lg:col-span-2">
        <h1 className="text-2xl font-bold">{t("copilot.title")}</h1>
        <p className="mb-4 text-sm text-black/60">{t("copilot.subtitle")}</p>

        <div className="flex-1 space-y-3 overflow-y-auto">
          {messages.map((m, i) => (
            <div key={i} className={m.role === "user" ? "text-right" : ""}>
              <div
                className={`inline-block max-w-[85%] whitespace-pre-wrap rounded-xl px-4 py-2 text-left text-sm ${
                  m.role === "user" ? "bg-ink text-white" : m.role === "system" ? "bg-danger-bg" : "bg-paper"
                }`}
              >
                {m.text}
              </div>
              {m.plan && (
                <div className="mt-2 max-w-[85%]">
                  <RescuePlanCard plan={m.plan} />
                </div>
              )}
              {m.cards?.map((c) => (
                <div key={c.action_id} className="mt-2 max-w-[85%]">
                  <ApprovalCard
                    card={c}
                    onDone={(msg) => setMessages((ms) => [...ms, { role: "system", text: msg }])}
                  />
                </div>
              ))}
            </div>
          ))}
          {busy && <p className="text-sm text-black/50">Thinking…</p>}
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button key={s} className="btn-outline rounded-full text-xs" onClick={() => send(s)}>
              {s}
            </button>
          ))}
        </div>
        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          <input
            className="flex-1 rounded-lg border border-black/15 px-3 py-2 text-sm"
            placeholder={t("copilot.placeholder")}
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
          <button className="btn bg-ink text-white" disabled={busy}>
            {t("copilot.send")}
          </button>
        </form>
      </section>

      <aside className="space-y-4">
        <div className="card">
          <h2 className="mb-3 font-semibold">{t("copilot.did")}</h2>
          {trace.length === 0 && <p className="text-sm text-black/50">No tool calls yet.</p>}
          <ul className="space-y-2">
            {trace.map((tr, i) => (
              <li key={i} className="flex items-center justify-between gap-2 text-sm">
                <code className="font-mono text-xs">{tr.tool}</code>
                <TierBadge value={tr.status === "needs_approval" ? "held" : tr.tier} />
              </li>
            ))}
          </ul>
        </div>
        <div className="card text-sm">
          <h2 className="mb-2 font-semibold">Permission tiers</h2>
          <p><b>Read-only</b> · looks at your data. Acts freely.</p>
          <p className="mt-1"><b>Suggest</b> · drafts and recommends. Nothing leaves the app.</p>
          <p className="mt-1">
            <b>Needs approval</b> · sends, submits or moves money. The server refuses it without
            your recorded approval.
          </p>
        </div>
      </aside>
    </div>
  );
}
