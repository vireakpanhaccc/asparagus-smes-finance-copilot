"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import ApprovalCard from "@/components/ApprovalCard";
import RescuePlanCard from "@/components/RescuePlanCard";
import TierBadge from "@/components/TierBadge";
import { RESCUE_PROMPT, useCopilot } from "@/lib/copilot";
import { useI18n } from "@/lib/i18n";

const SUGGESTIONS = [
  { label: "How can I cover the gap?", prompt: RESCUE_PROMPT },
  { label: "Who owes me money?", prompt: "Which customers owe me money or pay late?" },
  { label: "Why are my costs up?", prompt: "Why are my supplier costs up?" },
];

const BOT = "self-start max-w-[88%] rounded-[14px_14px_14px_4px] bg-[#f1f1ee] px-3 py-2.5 text-[13px] leading-snug";
const USER = "self-end max-w-[80%] rounded-[14px_14px_4px_14px] bg-ink-soft px-3 py-2.5 text-[13px] text-white";

// The conversation itself: header slot, messages, suggestions, input. Used inside the
// docked bot on Overview and as the full-screen view on /copilot.
export default function CopilotChat({ greeting, headerAction }: { greeting?: string; headerAction?: ReactNode }) {
  const { t } = useI18n();
  const { messages, trace, busy, send, addSystem } = useCopilot();
  const [input, setInput] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [messages, busy]);

  function submit(text: string) {
    if (!text.trim()) return;
    setInput("");
    void send(text);
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-3 border-b border-line px-4 py-3.5">
        <div className="h-9 w-9 shrink-0 rounded-full bg-teal" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <div className="text-[15px] font-semibold">Copilot</div>
          <div className="text-xs text-muted">{t("copilot.subtitle")}</div>
        </div>
        {headerAction}
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto px-4 py-3.5" aria-live="polite">
        <div className={BOT}>{greeting ?? t("copilot.greeting")}</div>

        {messages.length === 0 && (
          <div className="flex flex-wrap gap-1.5">
            {SUGGESTIONS.map((s) => (
              <button key={s.label} className="chip" disabled={busy} onClick={() => submit(s.prompt)}>
                {s.label}
              </button>
            ))}
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className="flex flex-col gap-2.5">
            <div
              className={`whitespace-pre-wrap ${
                m.role === "user" ? USER : m.role === "system" ? `${BOT} !bg-danger-bg` : BOT
              }`}
            >
              {m.text}
            </div>
            {m.plan && <RescuePlanCard plan={m.plan} />}
            {m.cards?.map((c) => (
              <ApprovalCard key={c.action_id} card={c} onDone={addSystem} />
            ))}
          </div>
        ))}

        {busy && <p className="text-xs text-muted">Thinking…</p>}

        {trace.length > 0 && (
          <details className="text-xs text-muted">
            <summary className="cursor-pointer select-none">
              {t("copilot.steps")} · {trace.length} step{trace.length === 1 ? "" : "s"}
            </summary>
            <ul className="mt-2 space-y-1.5">
              {trace.map((tr, i) => (
                <li key={i} className="flex items-center justify-between gap-2">
                  <code className="font-mono text-[11px] text-ink">{tr.tool}</code>
                  <TierBadge value={tr.status === "needs_approval" ? "held" : tr.tier} />
                </li>
              ))}
            </ul>
          </details>
        )}
        <div ref={bottom} />
      </div>

      <form
        className="flex gap-2 border-t border-line p-3 pb-5 lg:pb-3"
        onSubmit={(e) => {
          e.preventDefault();
          submit(input);
        }}
      >
        <label htmlFor="copilot-input" className="sr-only">
          Ask the Copilot
        </label>
        <input
          id="copilot-input"
          className="h-11 min-w-0 flex-1 rounded-full border border-[#b8b8b3] bg-paper px-3.5 text-[13px]"
          placeholder={t("copilot.placeholder")}
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button className="btn-primary rounded-full text-[13px]" disabled={busy}>
          {t("copilot.send")}
        </button>
      </form>
    </div>
  );
}
