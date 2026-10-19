const STYLES: Record<string, string> = {
  read_only: "bg-brand-line2 text-brand-sub",
  suggest: "bg-brand-blue50 text-brand-blue",
  needs_approval: "bg-brand-amber50 text-brand-amber",
  ok: "bg-brand-blue50 text-brand-blue",
  done: "bg-brand-blue50 text-brand-blue",
  approved: "bg-brand-blue50 text-brand-blue",
  held: "bg-brand-amber50 text-brand-amber",
  needs_approval_status: "bg-brand-amber50 text-brand-amber",
  blocked: "bg-brand-red50 text-brand-red700",
  ignored: "bg-brand-red50 text-brand-red700",
  error: "bg-brand-red50 text-brand-red700",
  declined: "bg-brand-line2 text-brand-sub",
};

export default function TierBadge({ value }: { value: string }) {
  return (
    <span className={`badge whitespace-nowrap ${STYLES[value] ?? "bg-brand-line2"}`}>
      {value.replace("_", " ")}
    </span>
  );
}
