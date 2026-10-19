"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

// "+ Add data" popover: type an entry, upload a file, or link another bank.
// role=menu; closes on Esc or a click outside.
export default function AddDataMenu({ onType, onUpload }: { onType: () => void; onUpload: () => void }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onDown = (e: PointerEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onDown);
    };
  }, [open]);

  const item = "block w-full rounded-lg px-3 py-2.5 text-left hover:bg-brand-panel";
  const sub = "mt-0.5 block text-xs font-normal text-brand-muted";

  return (
    <div ref={box} className="relative">
      <button className="btn-primary" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        + Add data ▾
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-30 mt-2 w-[min(360px,calc(100vw-2rem))] rounded-xl border border-brand-line bg-white p-1.5 shadow-xl">
          <button role="menuitem" className={item} onClick={() => { setOpen(false); onType(); }}>
            <span className="text-sm font-semibold">Type an entry</span>
            <span className={sub}>Cash sales, a bill to pay, an invoice to collect</span>
          </button>
          <button role="menuitem" className={item} onClick={() => { setOpen(false); onUpload(); }}>
            <span className="text-sm font-semibold">Upload a file</span>
            <span className={sub}>CSV from any bank · all-or-nothing check · template included</span>
          </button>
          <Link role="menuitem" href="/setup?step=bank" className={`${item} !text-brand-ink`} onClick={() => setOpen(false)}>
            <span className="text-sm font-semibold">Link another bank</span>
            <span className={sub}>Syncs automatically · read-only</span>
          </Link>
        </div>
      )}
    </div>
  );
}
