"use client";

// UI strings live in messages/en.json; pages read them with t("key").

import { createContext, useContext, type ReactNode } from "react";
import en from "../../messages/en.json";

const DICT: Record<string, string> = en;

type Ctx = { t: (key: string) => string };
const I18nContext = createContext<Ctx | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const t = (key: string) => DICT[key] ?? key;
  return <I18nContext.Provider value={{ t }}>{children}</I18nContext.Provider>;
}

export function useI18n(): Ctx {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used inside I18nProvider");
  return ctx;
}
