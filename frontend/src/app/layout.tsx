import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import AppShell from "@/components/AppShell";
import { CopilotProvider } from "@/lib/copilot";
import { I18nProvider } from "@/lib/i18n";
import "./globals.css";

export const metadata: Metadata = {
  title: "SME Finance Copilot",
  description: "SME finance copilot with approval-gated actions (sandbox).",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <I18nProvider>
          <CopilotProvider>
            <AppShell>{children}</AppShell>
          </CopilotProvider>
        </I18nProvider>
      </body>
    </html>
  );
}
