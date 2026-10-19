"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useI18n } from "@/lib/i18n";

const ITEMS = [
  { href: "/overview", key: "nav.overview" },
  { href: "/copilot", key: "nav.copilot" },
  { href: "/financing", key: "nav.financing" },
  { href: "/audit", key: "nav.audit" },
  { href: "/connect", key: "nav.connect" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { t } = useI18n();

  return (
    <aside className="flex w-56 shrink-0 flex-col bg-ink p-4 text-white">
      <div className="mb-6 flex items-center gap-2 text-lg font-bold leading-tight">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-teal">↗</span>
        SME Finance Copilot
      </div>
      <nav className="flex flex-col gap-1">
        {ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`rounded-lg px-3 py-2 text-sm ${
              pathname === item.href ? "bg-ink-soft font-semibold" : "hover:bg-ink-soft/60"
            }`}
          >
            {t(item.key)}
          </Link>
        ))}
      </nav>
      <div className="mt-auto rounded-lg bg-ink-soft p-3 text-sm">
        <div className="font-semibold">Sample Café</div>
        <div className="text-white/70">Phnom Penh · USD</div>
        <span className="badge mt-2 bg-warn-bg text-warn">{t("sandbox")}</span>
      </div>
    </aside>
  );
}
