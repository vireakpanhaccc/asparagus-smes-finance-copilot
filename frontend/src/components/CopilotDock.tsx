"use client";

import { useEffect, useRef, useState } from "react";
import CopilotChat from "@/components/CopilotChat";
import { apiGet, money, type Forecast } from "@/lib/api";
import { useCopilot } from "@/lib/copilot";
import { useI18n } from "@/lib/i18n";

// The Copilot as a round bot button in the corner. The chat stays hidden until the owner
// taps it. Desktop (lg+): a floating panel above the button, which can be expanded to fill
// the right side of the screen (never over the sidebar). Below lg: a bottom sheet.
export default function CopilotDock() {
  const { t } = useI18n();
  const { open, setOpen } = useCopilot();
  const [expanded, setExpanded] = useState(false);
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
      {/* Always mounted so it can animate; hidden from focus and screen readers while closed. */}
      <div
        className={`fixed inset-0 z-30 bg-[rgba(20,33,61,0.42)] transition-opacity duration-300 motion-reduce:transition-none lg:hidden ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        aria-hidden="true"
      />

      <aside
        ref={panel}
        aria-label="Copilot chat"
        aria-hidden={!open}
        className={[
          // mobile: bottom sheet that slides up
          "fixed inset-x-0 bottom-0 z-40 flex h-[85vh] flex-col overflow-hidden rounded-t-[20px] bg-white shadow-2xl",
          // desktop: floating panel that grows out of the bot button
          "lg:inset-x-auto lg:bottom-24 lg:right-6 lg:origin-bottom-right lg:rounded-2xl lg:border-[1.5px] lg:border-brand-ink",
          // expanded: the right side of the screen, full height, clear of the 220px sidebar
          expanded
            ? "lg:h-[calc(100vh-7.5rem)] lg:w-[min(48rem,calc(100vw-280px))]"
            : "lg:h-[min(640px,calc(100vh-8rem))] lg:w-[380px]",
          "transition-[opacity,transform,visibility,width,height] duration-300 ease-out motion-reduce:transition-none",
          open
            ? "visible translate-y-0 opacity-100 lg:scale-100"
            : "invisible translate-y-full opacity-0 lg:translate-y-3 lg:scale-95",
        ].join(" ")}
      >
        <div className="flex justify-center pt-2 lg:hidden" aria-hidden="true">
          <div className="h-1 w-10 rounded-full bg-brand-field" />
        </div>
        <div className="flex min-h-0 flex-1 flex-col">
          <CopilotChat
            greeting={greeting}
            headerAction={
              <>
                {/* Desktop only: on phones the chat is already a tall bottom sheet. */}
                <button
                  aria-label={expanded ? "Shrink chat" : "Expand chat"}
                  title={expanded ? "Shrink chat" : "Expand chat"}
                  aria-pressed={expanded}
                  onClick={() => setExpanded(!expanded)}
                  className="hidden h-11 w-11 place-items-center rounded-lg border border-brand-line bg-white lg:grid"
                >
                  <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    {expanded ? (
                      <path d="M9.5 2.5v4h4M6.5 13.5v-4h-4M9.5 6.5l4-4M6.5 9.5l-4 4" />
                    ) : (
                      <path d="M9.5 2.5h4v4M6.5 13.5h-4v-4M13.5 2.5l-4 4M2.5 13.5l4-4" />
                    )}
                  </svg>
                </button>
                <button
                  aria-label={t("copilot.close")}
                  onClick={() => setOpen(false)}
                  className="grid h-11 w-11 place-items-center rounded-lg border border-brand-line bg-white"
                >
                  <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                    <path d="M3 3l10 10M13 3L3 13" />
                  </svg>
                </button>
              </>
            }
          />
        </div>
      </aside>

      {/* Round bot logo. The bot and the X cross-fade and turn into each other. On mobile it
          fades out while the sheet is open (the sheet has its own close button). */}
      <button
        ref={button}
        onClick={() => setOpen(!open)}
        aria-label={open ? t("copilot.close") : t("copilot.open")}
        aria-expanded={open}
        title={t("copilot.open")}
        className={`fixed bottom-6 right-4 z-50 grid h-14 w-14 place-items-center rounded-full bg-brand-blue text-white shadow-[0_6px_18px_rgba(0,0,0,0.22)] transition-[transform,opacity,background-color] duration-300 hover:scale-105 hover:bg-brand-blue700 active:scale-95 motion-reduce:transition-none lg:right-6 ${
          open ? "pointer-events-none scale-90 opacity-0 lg:pointer-events-auto lg:scale-100 lg:opacity-100" : ""
        }`}
      >
        <svg
          aria-hidden="true" width="28" height="28" viewBox="0 0 28 28" fill="none" stroke="currentColor"
          strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
          className={`absolute transition-[transform,opacity] duration-300 motion-reduce:transition-none ${
            open ? "rotate-90 scale-50 opacity-0" : "rotate-0 scale-100 opacity-100"
          }`}
        >
          <rect x="5" y="9" width="18" height="12" rx="4" />
          <path d="M14 9V5.5M11 5.5h6" />
          <circle cx="10.5" cy="15" r="1.2" fill="currentColor" stroke="none" />
          <circle cx="17.5" cy="15" r="1.2" fill="currentColor" stroke="none" />
          <path d="M12 18.2h4" />
        </svg>
        <svg
          aria-hidden="true" width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor"
          strokeWidth="2" strokeLinecap="round"
          className={`absolute transition-[transform,opacity] duration-300 motion-reduce:transition-none ${
            open ? "rotate-0 scale-100 opacity-100" : "-rotate-90 scale-50 opacity-0"
          }`}
        >
          <path d="M5 5l10 10M15 5L5 15" />
        </svg>
      </button>
    </>
  );
}
