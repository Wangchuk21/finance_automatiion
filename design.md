# UX Design Guide for the EMI Dues System

For a finance tool, "beautiful" means calm, clear, and trustworthy. Finance staff will use it monthly, spend most of their time reading numbers, and need to feel safe before pressing Confirm. So aim for clean layouts, strong number readability, and very clear status colors.

## 1. Design principles

1. **Numbers first.** The dashboard should answer "how much is due, how much is overdue, which region is worst" within 3 seconds.
2. **One main action per screen.** Upload, Confirm, Export: each screen has one obvious primary button.
3. **Never surprise the user.** Before anything changes data (upload, close contract, rollback), show a preview and a plain-language summary.
4. **Color means status only.** Don't use red, amber, and green for decoration.
5. **Quiet by default, loud when it matters.** Normal screens are calm. The missing-contract review and wrong-file warnings are the only places that get strong red banners.

## 2. Visual style

**Look:** modern minimal. Lots of white space, soft card shadows, rounded corners (8-12px), thin borders.

**Colors**

| Role | Suggestion |
|---|---|
| Background | `#F7F8FA` (page), `#FFFFFF` (cards) |
| Text | `#111827` (main), `#6B7280` (secondary) |
| Primary / brand | A deep blue such as `#1F4FD8` (or your organization's brand color) |
| Success / paid | `#16A34A` on a light green tint |
| Warning / watch | `#D97706` on a light amber tint |
| Critical / overdue | `#DC2626` on a light red tint |
| Neutral / closed | `#6B7280` on light grey |

Use **tinted badges** (light background, darker text) for status instead of solid color blocks. They look more refined and are easier to read in tables. Offer a **dark mode** later, but a good light theme comes first.

**Typography:** Inter (or system UI fonts). Use **tabular numbers** (`font-variant-numeric: tabular-nums`) so digits line up in columns, and right-align all amounts. Sizes: 14px body, 12px table meta, 28-32px for big KPI numbers.

**Icons:** one consistent set, such as Lucide or Tabler. Pair every status color with an icon or label, so it isn't color alone (helps colorblind users and printed reports).

## 3. Layout

- **Left sidebar** (collapsible): Dashboard, Reports, Contracts, Uploads, Settings. Keep it to 5-6 items.
- **Top bar:** page title, global search (reference, customer, CID), as-of date, user menu.
- **Content area:** max width about 1400px, with a card grid.
- **Desktop-first**, but make it usable on a tablet. Managers will glance at the dashboard on their phones, so stack the KPI cards vertically on small screens.

## 4. Key screens

**Dashboard**
- Row of 4 KPI cards: **Total receivable**, **Collected**, **Overdue**, **Critical accounts**. Each shows a small change vs the previous upload ("+3.2% since 30 Sep").
- Below: a **region comparison bar chart** (the main feature finance asked for) beside an **aging bucket chart** (0-30, 31-60, 61-90, 91-120, 120+).
- A "needs attention" card: contracts in review, validation warnings, and so on.
- A line chart of collection trend by month, with an external vs internal toggle.

**Upload flow (a 4-step stepper)**
1. **Choose file:** drag-and-drop area, with the as-of date field next to it
2. **Validate:** progress, then a clean list of problems (errors in red, warnings in amber), each with the row number
3. **Preview:** summary cards (newly paid, newly overdue, new, missing) and before/after totals
4. **Confirm:** a single clear primary button, plus an authenticator code field

The stepper is what makes the process feel safe. The user always knows where they are and that nothing is saved until step 4.

**Missing-contract review**
- A red banner at the top: "14 contracts from the last upload are missing from this file."
- A table with a checkbox per row, the balance due highlighted, and three row actions: **Close**, **Keep active**, **Decide later**.
- A sticky bar at the bottom for bulk actions once rows are selected.
- When the missing share is large, put **Cancel upload** first and make it prominent.

**Reports**
- A filter bar of **chips** (Region: Western ×, Channel: Internal ×, Month: Oct ×) above the table, with "Clear all"
- A density toggle (comfortable and compact), a sticky header row, and column sorting
- An **Export** dropdown (Excel, CSV, PDF) at the top right
- Subtotals in a bold row, and numbers right-aligned

**Contract detail**
- Header: reference, customer (CID masked), status badge, region, channel
- A **timeline of installments** as a horizontal row of small dots or boxes, one per month: green paid, red overdue, grey upcoming. Finance can read a contract's history in one second.
- A side card with balance due, installments remaining, and the history of upload changes

**Login and TOTP**
- A centered card with a quiet background. The 6-digit code field uses **six separate boxes** with auto-advance, and the QR enrollment page shows the steps beside the QR code.
- Show recovery codes once, with a "Download" and "I've saved them" checkbox before continuing.

## 5. Details that make it feel polished

- **Skeleton loaders** instead of spinners for tables and charts
- **Empty states** that explain what to do ("No uploads yet. Upload your first file.") with one button
- **Friendly errors:** "Row 42: Posting Date is not a valid date (found '2026-13-45')" rather than "Validation failed"
- **Toasts** for success ("Upload confirmed, 38 contracts updated") with an **Undo / Rollback** link
- **Number formatting:** `Nu. 1,22,640` or `Nu. 122,640` consistently, whichever finance prefers, with no decimals in summaries and two in detail views
- **Subtle motion:** 150-200ms fades and hover states. Avoid anything flashy.
- **Confirm dialogs** only for destructive actions (close contract, rollback), and they restate the consequence ("Closing this contract stops all reminders. Balance due: Nu. 15,330")
- **Keyboard support:** Tab order, visible focus rings, and Esc to close dialogs
- **Print stylesheet** for reports, since finance will print them

## 6. Tools to build it quickly

| Choice | Notes |
|---|---|
| **React + Tailwind + shadcn/ui** | The most polished default look with the least effort. Pairs well with FastAPI. |
| **Django + Tabler or Bootstrap 5 template** | Quick if you prefer server-rendered pages. Tabler's dashboard template already looks clean and professional. |
| **Charts** | Apache ECharts (feature-rich and attractive) or Recharts (simple, React) |
| **Tables** | TanStack Table (React) or AG Grid Community for large, sortable, filterable tables |
| **Icons and fonts** | Lucide or Tabler icons, Inter font |

For inspiration, look at the dashboards of **Stripe**, **Linear**, **Mercury**, and **Vercel**. They are good models of calm, number-focused interfaces.

## 7. A quick checklist before you build a screen

- Is there one clear primary action?
- Can someone read the key number in 3 seconds?
- Does every status use color **and** a label or icon?
- Is every amount right-aligned and consistently formatted?
- Does anything that changes data show a preview first?

If you tell me your front-end choice (React or server-rendered), I can mock up the dashboard and upload-preview screens so you have something concrete to copy, or write the Tailwind/CSS design tokens for the palette above.