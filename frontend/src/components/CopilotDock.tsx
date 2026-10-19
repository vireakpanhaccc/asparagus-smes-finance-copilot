"use client";

import { useEffect, useRef, useState } from "react";
import CopilotChat from "@/components/CopilotChat";
import { apiGet, money, type Forecast } from "@/lib/api";
import { useCopilot } from "@/lib/copilot";
import { useI18n } from "@/lib/i18n";

// The Copilot as a round bot button in the corner. The chat stays hidden until the owner
// taps it. Desktop (lg+): a floating panel above the button. Below lg: a bottom sheet.
export default function CopilotDock() {
  const { t } = useI18n();
  const { open, setOpen } = useCopilot();
  const [greeting, setGreeting] = useState<string | undefined>();
  const panel = useRef<HTMLElement>(null);
  const button = useRef<HTMLButtonElement>(null);

  // The greeting names the shortfall, so every page shows the same heads-up. Refreshed on
  // open so it reflects data added since the last look; falls back to the generic text.
  useEffect(() => {
    if (!open) return;
    apiGet<Forecast>("/forecast")
      .then((f) => {
        const w = f.weeks.find((x) => x.shortfall);
        setGreeting(
          w
            ? `Hi! Heads up: your cash may dip to ${money(w.lowest_balance_cents)} in the week of ${w.week_start}. Want me to work out how to cover it?`
            : undefined,
        );
      })
      .catch(() => setGreeting(undefined));
  }, [open]);

  // Esc or a tap anywhere outside the panel and the bot button closes the chat.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onPointerDown = (e: PointerEvent) => {
      const target = e.target as Node;
      if (panel.current?.contains(target) || button.current?.contains(target)) return;
      setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [open, setOpen]);

  return (
    <>
      {open && (
        <div className="fixed inset-0 z-30 bg-[rgba(20,20,18,0.42)] lg:hidden" aria-hidden="true" />
      )}

      {open && (
        <aside
          ref={panel}
          aria-label="Copilot chat"
          className={[
            // mobile: bottom sheet
            "fixed inset-x-0 bottom-0 z-40 flex h-[85vh] flex-col overflow-hidden rounded-t-[20px] bg-white shadow-2xl",
            // desktop: floating panel above the bot button
            "lg:inset-x-auto lg:bottom-24 lg:right-6 lg:h-[min(640px,calc(100vh-8rem))] lg:w-[380px] lg:rounded-2xl lg:border-[1.5px] lg:border-ink-soft",
          ].join(" ")}
        >
          <div className="flex justify-center pt-2 lg:hidden" aria-hidden="true">
            <div className="h-1 w-10 rounded-full bg-[#c9c9c4]" />
          </div>
          <div className="flex min-h-0 flex-1 flex-col">
            <CopilotChat
              greeting={greeting}
              headerAction={
                <button
                  aria-label={t("copilot.close")}
                  onClick={() => setOpen(false)}
                  className="grid h-11 w-11 place-items-center rounded-lg border border-line bg-white"
                >
                  <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                    <path d="M3 3l10 10M13 3L3 13" />
                  </svg>
                </button>
              }
            />
          </div>
        </aside>
      )}

      {/* Round bot logo. On mobile it hides while the sheet is open (the sheet has its own close). */}
      <button
        ref={button}
        onClick={() => setOpen(!open)}
        aria-label={open ? t("copilot.close") : t("copilot.open")}
        aria-expanded={open}
        title={t("copilot.open")}
        className={`fixed bottom-6 right-4 z-50 h-14 w-14 place-items-center rounded-full bg-teal text-white shadow-[0_6px_18px_rgba(0,0,0,0.22)] transition-transform hover:scale-105 hover:bg-teal-dark lg:right-6 ${
          open ? "hidden lg:grid" : "grid"
        }`}
      >
        {open ? (
          <svg aria-hidden="true" width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M5 5l10 10M15 5L5 15" />
          </svg>
        ) : (
          <svg aria-hidden="true" width="28" height="28" viewBox="0 0 28 28" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <rect x="5" y="9" width="18" height="12" rx="4" />
            <path d="M14 9V5.5M11 5.5h6" />
            <circle cx="10.5" cy="15" r="1.2" fill="currentColor" stroke="none" />
            <circle cx="17.5" cy="15" r="1.2" fill="currentColor" stroke="none" />
            <path d="M12 18.2h4" />
          </svg>
        )}
      </button>
    </>
  );
}
