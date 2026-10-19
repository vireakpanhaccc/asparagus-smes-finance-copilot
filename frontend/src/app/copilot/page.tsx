"use client";

import CopilotChat from "@/components/CopilotChat";

// Full-screen view of the same conversation that is docked on Overview.
export default function CopilotPage() {
  return (
    <div className="mx-auto h-[calc(100vh-4.5rem)] max-w-3xl p-4 lg:h-screen lg:p-8">
      <div className="h-full overflow-hidden rounded-2xl border-[1.5px] border-ink-soft bg-white">
        <CopilotChat />
      </div>
    </div>
  );
}
