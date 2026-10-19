const STYLES: Record<string, string> = {
  read_only: "bg-black/5 text-black/70",
  suggest: "bg-teal-light text-teal",
  needs_approval: "bg-warn-bg text-warn",
  ok: "bg-teal-light text-teal",
  done: "bg-teal-light text-teal",
  approved: "bg-teal-light text-teal",
  held: "bg-warn-bg text-warn",
  needs_approval_status: "bg-warn-bg text-warn",
  blocked: "bg-danger-bg text-danger",
  ignored: "bg-danger-bg text-danger",
  error: "bg-danger-bg text-danger",
  declined: "bg-black/5 text-black/70",
};

export default function TierBadge({ value }: { value: string }) {
  return (
    <span className={`badge whitespace-nowrap ${STYLES[value] ?? "bg-black/5"}`}>
      {value.replace("_", " ")}
    </span>
  );
}
