import type { ReactNode } from "react";

// Renders the small Markdown subset the model writes (bold, `code`, bullet and numbered
// lists with indented sub-items, headings) as React elements, never as HTML: React escapes
// every string, so model output (which can quote untrusted customer text) cannot inject
// markup or scripts.

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) => {
    if (part.length > 4 && part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    if (part.length > 2 && part.startsWith("`") && part.endsWith("`")) {
      return <code key={i} className="font-mono text-[12px]">{part.slice(1, -1)}</code>;
    }
    return part;
  });
}

type Item = { text: string; sub: string[] };
type List = { ordered: boolean; start: number; items: Item[] };

export default function ChatText({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let list: List | null = null;

  const flush = () => {
    if (!list) return;
    const items = list.items.map((item, i) => (
      <li key={i}>
        {inline(item.text)}
        {item.sub.length > 0 && (
          <ul className="mt-0.5 list-disc space-y-0.5 pl-5">
            {item.sub.map((s, j) => <li key={j}>{inline(s)}</li>)}
          </ul>
        )}
      </li>
    ));
    blocks.push(
      list.ordered ? (
        <ol key={blocks.length} start={list.start} className="list-decimal space-y-1 pl-5">{items}</ol>
      ) : (
        <ul key={blocks.length} className="list-disc space-y-1 pl-5">{items}</ul>
      ),
    );
    list = null;
  };

  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    // "- item" or "1. item"; "-$207" (a negative amount) is not a bullet: it needs a space.
    const bullet = line.match(/^(\s*)[-*•]\s+(.*)$/);
    const numbered = line.match(/^(\s*)(\d+)[.)]\s+(.*)$/);
    // An indented bullet under a list item is that item's sub-point, not a new list, so
    // the numbering carries on (1, 2, 3) instead of restarting after every sub-point.
    if (bullet && bullet[1].length >= 2 && list && list.items.length) {
      list.items[list.items.length - 1].sub.push(bullet[2]);
      continue;
    }
    if (bullet || numbered) {
      const ordered = !bullet;
      if (!list || list.ordered !== ordered) {
        flush();
        list = { ordered, start: numbered ? Number(numbered[2]) : 1, items: [] };
      }
      list.items.push({ text: bullet ? bullet[2] : numbered![3], sub: [] });
      continue;
    }
    if (!line.trim()) continue; // a blank line inside a list keeps the list going
    flush();
    const heading = line.match(/^\s*#{1,6}\s+(.*)$/);
    blocks.push(
      <p key={blocks.length} className={heading ? "font-semibold" : undefined}>
        {inline(heading ? heading[1] : line)}
      </p>,
    );
  }
  flush();
  return <div className="flex flex-col gap-1.5">{blocks}</div>;
}
