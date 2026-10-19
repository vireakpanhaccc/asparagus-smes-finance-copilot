// Thin client for the FastAPI backend. All money values from the API are in cents.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Demo-only owner token. Known risk (security report): a real product would use a
// session cookie from proper login, never a token shipped to the browser.
const OWNER_TOKEN = process.env.NEXT_PUBLIC_OWNER_TOKEN ?? "demo-owner-token";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}/api${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Owner-Token": OWNER_TOKEN,
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(await errorText(res));
  return res.json() as Promise<T>;
}

// FastAPI sends either a string or a list of field errors; show both readably.
async function errorText(res: Response): Promise<string> {
  const body = await res.json().catch(() => ({}));
  const detail = body.detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => `${String(d.loc?.at(-1) ?? "")}: ${d.msg ?? ""}`)
      .join("; ");
  }
  return detail ?? `Request failed: ${res.status}`;
}

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_URL}/api${path}`, {
    method: "POST",
    headers: { "X-Owner-Token": OWNER_TOKEN }, // no Content-Type: the browser sets the boundary
    body: form,
  });
  if (!res.ok) throw new Error(await errorText(res));
  return res.json() as Promise<T>;
}

export const apiGet = <T>(path: string) => request<T>(path);
export const apiPost = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });
export const apiDelete = <T>(path: string) => request<T>(path, { method: "DELETE" });

// EventSource cannot send headers, so the live stream takes the token as a query
// parameter. Known risk (security report): it can appear in server logs.
export const streamUrl = (path: string) =>
  `${API_URL}/api${path}?token=${encodeURIComponent(OWNER_TOKEN)}`;

// A plain <a href> cannot send the owner token, so downloads go through fetch.
export async function apiDownload(path: string, filename: string): Promise<void> {
  const res = await fetch(`${API_URL}/api${path}`, {
    headers: { "X-Owner-Token": OWNER_TOKEN },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Download failed: ${res.status}`);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export const money = (cents: number, digits = 0) =>
  (cents < 0 ? "−$" : "$") +
  (Math.abs(cents) / 100).toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });

// ---- response types (keep in sync with backend) --------------------------

export type ForecastWeek = {
  week_start: string;
  end_balance_cents: number;
  lowest_balance_cents: number;
  shortfall: boolean;
  scheduled_bills: { date: string; counterparty: string; amount_cents: number }[];
};

export type Forecast = {
  as_of: string;
  current_balance_cents: number;
  weeks: ForecastWeek[];
  shortfall_weeks: string[];
  note: string;
};

export type Analysis = {
  last_30_days: {
    money_in_cents: number;
    money_out_cents: number;
    net_cents: number;
    margin_pct: number | null;
  };
  spend_by_category_cents: Record<string, number>;
  margin_trend: { month: string; net_cents: number; margin_pct: number | null }[];
  supplier_cost_change_8w_pct: number | null;
};

export type ApprovalCard = {
  action_id: string;
  tool: string;
  payload: Record<string, unknown>;
  payload_hash: string;
};

export type RescuePlan = {
  needed: boolean;
  safety_buffer_cents: number;
  before: { lowest_balance_cents: number; lowest_week: string; shortfall_weeks: string[] };
  after?: {
    lowest_balance_cents: number;
    lowest_week: string;
    shortfall_weeks: string[];
    closes_gap: boolean;
  };
  steps: {
    step: number;
    kind: string;
    title: string;
    how: string;
    cost_cents: number;
    assumption: string;
    lowest_after_cents: number;
    improves_lowest_by_cents: number;
  }[];
  backup: { when: string; title: string; how: string; cost_cents: number } | null;
  weeks: { week_start: string; before_cents: number; after_cents: number }[];
  note: string;
};

export type ChatResponse = {
  conversation_id: string;
  reply: string;
  tool_trace: { tool: string; tier: string; status: string }[];
  plan: RescuePlan | null;
  approval_cards: ApprovalCard[];
};

export type FinancingOption = {
  product_id: string;
  name: string;
  kind: string;
  label: string;
  amount_cents: number;
  total_cost_cents: number;
  monthly_payment_cents: number;
  payment_to_margin_pct: number;
  why_it_fits: string[];
  watch_out: string[];
};

export type AuditEntry = {
  id: number;
  ts: string;
  actor: string;
  action: string;
  tier: string;
  result: string;
  detail: string;
};
