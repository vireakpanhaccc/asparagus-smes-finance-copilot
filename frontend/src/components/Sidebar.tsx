"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useI18n } from "@/lib/i18n";

const ITEMS = [
  { href: "/overview", key: "nav.overview" },
  { href: "/financing", key: "nav.financing" },
  { href: "/data", key: "nav.data" },
  { href: "/audit", key: "nav.audit" },
];

export default function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { t } = useI18n();

  return (
    <nav aria-label="Main" className="flex h-full flex-col gap-1.5 p-4">
      <div className="mb-5 flex items-center gap-2.5">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-blue" aria-hidden="true">
          <span className="h-2.5 w-2.5 rounded-full bg-brand-red" />
        </span>
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
                ? "bg-brand-blue50 font-semibold text-brand-blue700"
                : "text-brand-sub hover:bg-white hover:text-brand-ink"
            }`}
          >
            {t(item.key)}
          </Link>
        );
      })}
      <div className="mt-auto rounded-lg border border-dashed border-brand-field p-3 text-xs text-brand-muted">
        <div className="font-semibold text-brand-ink">Sample Café</div>
        <div>Phnom Penh · USD</div>
        <div className="mt-1">{t("sandbox")}</div>
      </div>
    </nav>
  );
}
