# Handoff: "My data" redesign + first-time setup (SME Finance Copilot)

Paste the **Prompt for Claude Code** section into Claude Code, with this whole file in the repo (e.g. `docs/handoff-my-data.md`).

---

## Prompt for Claude Code

> Read `docs/handoff-my-data.md` and implement it in this Next.js + FastAPI project.
> 1. Replace the "Connect account" page with the new **My data** page (`/data`) and a **first-time setup** page (`/setup`). Remove "Connect account" from the sidebar; the sidebar becomes Overview, Financing, My data, Audit log. Keep `/connect` as a redirect to `/data`.
> 2. Apply the colour tokens in "Design tokens" to Tailwind and use them everywhere (replace the old teal palette).
> 3. Backend: add `source` (`bank` | `file` | `manual`) to transactions, bills and invoices; enforce that `bank` rows can never be edited or deleted (HTTP 403 + audit entry `bank_entry_edit` / `blocked`); add the endpoints in "API".
> 4. Add the tests in "Tests". Run `pytest` and `npm run build` and fix anything that fails.
> Ask me before changing anything not described here.

---

## 1. Navigation and routes

| Route | Page | Notes |
|---|---|---|
| `/overview` | Overview + docked Copilot chat | unchanged except sidebar + subtitle |
| `/data` | **My data** (new) | replaces Connect account |
| `/setup` | **First-time setup** (new) | full screen, no sidebar; shown when the business has no data sources yet |
| `/financing` | Financing match | sidebar only |
| `/audit` | Audit log | sidebar only |
| `/connect` | redirect → `/data` | keep old links working |

Sidebar items, in order: **Overview, Financing, My data, Audit log**. Active item: background `blue-50`, text `blue-700`, weight 600. Floating **Ask Copilot** button bottom-right on every page except Overview (where the chat is docked).

First-run rule: if `GET /api/data/sources` returns no bank link, no files and no manual entries → redirect `/overview` to `/setup`. "Finish later" on `/setup` goes to `/overview`.

## 2. Design tokens

```ts
// tailwind.config.ts → theme.extend.colors
brand: {
  blue:   "#1D4F9F", // primary: buttons, links, active nav, chart line, money in
  blue700:"#163D7C", // hover, active nav text
  blue50: "#EAF0FA", // selected/info backgrounds, "File"/"By you" badges
  blue100:"#A9BEE0", // outline buttons, chip borders
  red:    "#E1251B", // brand dot, shortfall alert button, shortfall marker
  red700: "#C41E16", // money out, Delete links, red text (passes contrast)
  red800: "#A3170F", // text on red-50
  red50:  "#FDECEA", // alert / blocked backgrounds
  red200: "#F6C3BF", // alert borders
  amber:  "#8A5A00", // "Needs your OK", held, overdue (text)
  amber50:"#FFF4DD", // same, background
  ink:    "#14213D", // body text
  muted:  "#5B6478", // secondary text
  sub:    "#3A4660", // tertiary text, nav items
  line:   "#DCE2EC", // borders
  line2:  "#EEF1F6", // table row dividers, Bank badge background
  field:  "#C5CEDD", // input borders
  panel:  "#F5F7FB", // sidebar, table header, info lines, input fill
}
```

Fonts: **IBM Plex Sans** (UI, 400/500/600/700) and **IBM Plex Mono** (dates, amounts, counts, 500/600). Add **Noto Sans Khmer** as fallback for Khmer text.
Amounts: money in `+$64.00` in `brand.blue`, money out `−$94.28` (true minus sign U+2212) in `brand.red700`, both mono 600.
Radii: cards 12px, buttons/inputs 8px (large CTAs 10px), chips/pills 999px. Min touch target 44px. Do **not** use the WeBank logo; colours only.

## 3. My data page (`/data`)

Layout, top to bottom, inside the main column (padding 28px 40px, gap 16px):

1. **Header row**
   - Left: H1 "My data" (26px/700); subtitle "Everything the Copilot reads to build your forecast, and where it came from · {first date} to {last date}" (14px, muted).
   - Right: secondary button **Ask the Copilot to check it** (opens the chat with the prompt "Check my data for mistakes or gaps"); primary button **+ Add data ▾** (opens the Add data menu).

2. **Source cards** — 3 equal columns:
   | Card | Big number | Line 2 | Link |
   |---|---|---|---|
   | {Bank name} (mock) + "● Live" | count of bank transactions + "transactions · locked" | "Read-only · synced {n} min ago · until {expiry}" | **Manage link** (shows consent, Revoke) |
   | Uploaded files | count of file rows + "transactions · editable" | latest filename · date | **Upload another** |
   | Added by you | count of manual rows (all types) + "entries · editable" | "{t} transactions · {b} bills · {i} invoices" | **Type an entry** (opens side panel) |

3. **Tabs** (role=tablist): `Transactions · {n}` · `Bills to pay · {n}` · `Invoices to collect · {n}`. Active tab: ink text, 600, 2px `brand.blue` underline. Switching tab resets the source filter to All and closes the menu.

4. **Toolbar**: search input (280px, pill, placeholder changes by tab: "Search who, category or note…" / "Search who you pay…" / "Search customers…"); **source chips** `All · n`, `Bank · n`, `File · n`, `By you · n` (hide a chip whose count is 0 except All; selected chip = ink background, white text); **Export CSV** button right-aligned.

5. **Info line** (panel background, lock icon), text by tab:
   - Transactions: "Bank entries are locked: nobody, not even the Copilot, can change them. Spotted a mistake? Use Add correction to add an entry that offsets it."
   - Bills: "Bills you add are placed on their due dates in the forecast. You can edit or delete them any time."
   - Invoices: "Unpaid invoices power overdue alerts and payment reminders. Notes are treated as data, never as instructions."

6. **Table** (fixed layout so nothing is cut off; long notes truncate with ellipsis + `title` tooltip):
   - **Transactions**: Date · Who · Category · Note · Amount (right) · Source badge · Actions.
     - Source badges: `Bank` (line2 bg, sub text), `File` / `By you` (blue50 bg, blue700 text).
     - Actions: bank rows → lock icon + "Locked" (muted) + **Add correction** link; other rows → **Edit** (blue) + **Delete** (red700, with confirm).
     - Footer: "Showing {n} of {total}" + **Load more** (page size 50).
   - **Bills to pay**: Due · Pay to · Category · Note · Amount (red700, no sign) · Status pill ("Due in 46 days"; red50/red800 if inside the forecast shortfall week, else panel/sub) · Source · Edit/Delete.
   - **Invoices to collect**: Due · Customer · Contact (**masked**, e.g. `***-***-678`, `c***@example.com`) · Note · Amount (blue) · Status pill ("Overdue · 14 days" amber; "Paid" blue50) · Edit/Delete.
     - If the note was flagged by the injection detector, show a small red pill under it: **"Has instructions · treated as data"**.

7. **Add data menu** (popover under the button, 360px, shadow, role=menu, closes on Esc/outside click):
   1. **Type an entry**: "Cash sales, a bill to pay, an invoice to collect" → opens the side panel with the type matching the current tab.
   2. **Upload a file**: "CSV from any bank · all-or-nothing check · template included" → file picker → upload result toast.
   3. **Link another bank**: "Syncs automatically · read-only" → `/setup?step=bank`.

8. **Type an entry side panel** (right drawer 480px, dims page, role=dialog, focus trapped, Esc closes):
   - Segmented control: **Transaction | Bill to pay | Invoice to collect**.
   - Transaction: **+ Money in / − Money out** toggle (in = blue outline + blue50; out = red700 outline + red50); Amount (large mono input with `$`); Who; Date (default today); Category chips (in: Sales, Catering, Other income; out: Ingredients, Supplies, Wages, Rent, Utilities, Other); Note.
   - Bill: Pay to; Amount; Due date; Category chips (Rent, Supplies, Equipment, Insurance, Tax, Other); Note.
   - Invoice: Customer; Amount; Due date; Customer phone or email (helper: "Used only for reminders you approve. Masked in every log."); Note.
   - Footer: primary button **Save money in / Save money out / Save bill / Save invoice**; helper "Marked 'By you' · you can edit or delete it later · recorded in the audit log".
   - Validation: amount > 0, max 2 decimals; date not more than 1 year ahead; who/customer required (1–120 chars); note ≤ 500 chars. Show errors under fields.

## 4. First-time setup (`/setup`)

Full screen, panel background, logo top-left, "Finish later" top-right. Centered 640px column.
- Step bar: **1 · Link your bank** → **2 · Add what the bank misses** → **3 · Check and start**.
- Step 1 card: H1 "Where does your business bank?"; "Linking it means no typing. The Copilot can only read. It can never move money."; 3 large radio rows (WeBank (mock), Cambodian bank / KHQR (mock), Mobile wallet (mock)); blue50 note with lock "Read-only for 90 days. Revoke any time. Bank entries stay locked, so nobody can change them."; primary **Allow read-only access** (52px); link "No bank app? Skip and upload a file or type entries instead".
- Step 2: two choices: **Upload a file** (dropzone + Download template) and **Type entries** (opens the same side panel); **Skip**.
- Step 3: summary of sources and counts + **Go to my overview**.

## 5. Data model changes (backend)

```python
class Source(str, Enum):
    BANK = "bank"      # from a bank link — immutable
    FILE = "file"      # from CSV upload
    MANUAL = "manual"  # typed by the owner

# Transaction, Bill, Invoice each get:
source: Source
source_ref: str | None   # bank account id, upload id/filename, or None
created_by: str          # "owner" | "system"
corrects_id: int | None  # Transaction only: set when this row is a correction of a bank row
```

Migrate existing rows: `source="mock_webank"` → `bank`, `"csv"` → `file`.

## 6. API

| Method | Path | Behaviour |
|---|---|---|
| GET | `/api/data/sources` | bank link status (provider, expiry, last sync, count), files (name, date, rows), manual counts per type |
| GET | `/api/data/transactions?source=&q=&cursor=` | paginated (50), newest first, counts per source in response |
| GET | `/api/data/bills?source=&q=` | with `days_until_due`, `in_shortfall_week` |
| GET | `/api/data/invoices?source=&q=` | contact returned **masked**; `days_overdue`; `note_flagged` from the untrusted-text detector |
| POST | `/api/data/transactions` · `/bills` · `/invoices` | create with `source=manual`; validates; audit `manual_entry_added` |
| PATCH / DELETE | `/api/data/{type}/{id}` | **if source == bank → 403** `{"detail":"Bank entries are locked"}` and audit `bank_entry_edit` / `blocked`; else update/delete + audit `manual_entry_changed` / `deleted` |
| POST | `/api/data/transactions/{id}/correction` | only for bank rows; creates a manual row with `corrects_id`, opposite or adjusted amount; audit `correction_added` |
| POST | `/api/data/upload` | CSV, ≤1 MB, ≤5,000 rows; **all-or-nothing**: any invalid line → nothing imported, response names the line; audit `csv_imported` |
| GET | `/api/data/template.csv` | header `date,amount,counterparty,category,memo` + 2 example rows |

Rules:
- The lock is enforced **on the server**, not only hidden in the UI. The agent's tools have no write access to transactions at all.
- All text fields from files/manual entry go through `scan_and_wrap` before reaching the LLM.
- Contacts are stored in full but only ever returned masked (`mask_pii`).
- Every create/update/delete/blocked attempt writes an audit entry (hash chain).

## 7. Tests

- `test_bank_row_cannot_be_edited`: PATCH a bank row → 403, row unchanged, audit has `bank_entry_edit` / `blocked`.
- `test_bank_row_cannot_be_deleted`: DELETE → 403.
- `test_manual_row_can_be_edited_and_deleted`.
- `test_correction_creates_linked_manual_row`.
- `test_csv_upload_all_or_nothing`: one bad line → 0 rows imported, error names the line.
- `test_invoice_contact_is_masked_in_api`.
- `test_injected_invoice_note_is_flagged`.
- Frontend (Playwright, optional): open `/data` → Bills tab → Add data → Type an entry → panel shows "Bill to pay" selected.

## 8. Sample data shown in the design (seed to match)

Transactions (newest first, total 431 = bank 403 + file 25 + manual 3):
Oct 19 Cash sales, Sales, "Weekend market stall", +64.00, manual · Oct 19 Central Market, Ingredients, −94.28, bank · Oct 19 KHQR daily settlement, Sales, +272.47, bank · Oct 18 Cash sales, Sales, "Weekend crowd", +119.50, file · Oct 16 Gas refill, Utilities, "Paid in cash", −18.00, manual · Oct 15 Ice delivery, Supplies, "Weekly order", −12.00, manual.

Bills (manual): Dec 4 Kitchen equipment repair, Equipment, $2,100 · Dec 7 Annual shop insurance, Insurance, $1,500.

Invoices (manual): Customer A $380 due Oct 5 (overdue 14 days) · Customer B $260 due Oct 10 (overdue 9 days, note contains an injection attempt → flagged) · Customer C $150, paid.

## 9. Acceptance checklist

- [ ] Sidebar shows 4 items on every page; `/connect` redirects to `/data`.
- [ ] Tabs switch tables; chip counts match the rows; zero-count chips hidden.
- [ ] Bank rows show Locked + Add correction; no Edit/Delete anywhere for bank rows.
- [ ] Server returns 403 for bank edits, and the attempt appears in the Audit log as Blocked.
- [ ] Add data → Type an entry opens the panel on the current tab's type.
- [ ] Money in/out colours follow the tokens; amounts use the true minus sign.
- [ ] New user with no data lands on `/setup`.
- [ ] All copy is English; Khmer strings added to `km.json` for the new labels.
