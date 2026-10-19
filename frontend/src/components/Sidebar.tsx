"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useI18n } from "@/lib/i18n";

const ITEMS = [
  { href: "/overview", key: "nav.overview" },
  { href: "/financing", key: "nav.financing" },
  { href: "/audit", key: "nav.audit" },
  { href: "/connect", key: "nav.connect" },
];

export default function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { t } = useI18n();

  return (
    <nav aria-label="Main" className="flex h-full flex-col gap-1.5 p-4">
      <div className="mb-5 flex items-center gap-2.5">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-teal text-white">↗</span>
        <span className="text-[15px] font-bold leading-tight">SME Finance Copilot</span>
      </div>
      {ITEMS.map((item) => {
        const active = pathname === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={`rounded-lg px-3 py-2.5 text-sm ${
              active
                ? "border border-line bg-white font-semibold text-ink"
                : "border border-transparent text-ink-soft hover:bg-white/60 hover:text-ink"
            }`}
          >
            {t(item.key)}
          </Link>
        );
      })}
      <div className="mt-auto rounded-lg border border-dashed border-[#b8b8b3] p-3 text-xs text-muted">
        <div className="font-semibold text-ink">Sample Café</div>
        <div>Phnom Penh · USD</div>
        <div className="mt-1">{t("sandbox")}</div>
      </div>
    </nav>
  );
}
