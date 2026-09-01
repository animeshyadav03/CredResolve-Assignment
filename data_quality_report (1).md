# Data Quality Report
## Collections Analytics — Recovery Performance Review

Scope: 17 raw source tables, ~30,000 accounts, Jan–Aug 2026.

This report has four parts: **Major Data Issues**, **Detection
Methodology**, **Treatment**, and **Business Impact**. Each part covers all
12 issues found, in the same order, so a given issue (e.g. "Issue 3 —
Duplicate Payment Events") can be tracked across all four parts.

---

## 1. Major Data Issues

**Issue 1 — Agent Dimension Corruption.** The `agents` table has only
1,000 unique `agent_id` values but 30,000 rows — an average of 30
conflicting snapshot rows per agent (max 48). Across all 1,000 agents,
only 10 distinct `agent_name` values exist. `employee_code`, `vendor_id`,
`team`, `status`, and `joined_at` are effectively resampled at random on
every row for the same agent.

**Issue 2 — Borrower Dimension Corruption.** The same corruption pattern
as agents, one level less severe: `borrower_id` repeats up to 11x with
randomized `name`, `phone`, `email`, `city`, and `state` on every row.
Only 10 distinct name values exist across ~11,015 real borrowers.

**Issue 3 — Duplicate Payment Events.** 500 rows in `payments.csv` are
exact full-row duplicates of another `payment_id`-bearing row (identical
ID, amount, status, timestamp) — a classic ingestion/retry duplication
pattern.

**Issue 4 — Payment Reference Collisions.** The same `payment_reference`
(e.g. a single TXN number) appears against multiple unrelated
`account_id`/`borrower_id` combinations on different dates. Looks
superficially like a duplicate-detection signal but is not.

**Issue 5 — Unreliable Timezone Field.** The `timezone` column on `calls`
(also present on `accounts` and `vendor_telephony`) cannot be used to
determine true local call time.

**Issue 6 — Disposition Code Drift.** `call_dispositions.disposition_code`
contains both `PROMISE_TO_PAY` and `PTP` as if they were different
outcomes.

**Issue 7 — Denominator Inflation in the Naive Recovery Rate.** A
recovery-rate metric computed as two independent `COUNT(DISTINCT ...)`
aggregates divided against each other silently allows the numerator
(accounts with a SUCCESS payment) to include accounts that were not part
of that month's worked cohort.

**Issue 8 — Un-traceable Payment Reversals.**
`payments.payment_status = 'REVERSED'` rows (chargebacks/bounced payments)
cannot be linked back to the specific original SUCCESS transaction they
reverse.

**Issue 9 — RPC Definition Breaks on a Loose Join.** An initial
Right-Party-Contact (RPC) definition, joining `calls` to
`call_dispositions` on matching `account_id` + calendar day, produced an
implausible 0.04% RPC rate.

**Issue 10 — PTP Source-Channel Mix Ignored by a Naive Definition.** An
initial PTP-rate definition used "accounts contacted by phone" as the
denominator, implicitly assuming PTPs mostly come from calls.

**Issue 11 — Bad/Absurd Agent Session Durations.** `agent_sessions` could
plausibly contain negative-duration sessions (logout before login) or
absurdly long ones (system failing to log a logout).

**Issue 12 — Partial Final Month / Incorrect Period Framing.** The
assignment brief states "~12 months of collections data." The actual data
spans 2026-01-01 through 2026-08-08 only (~7.3 months), with the final
month partial.

---

## 2. Detection Methodology

**Issue 1 (Agent Dimension Corruption).** Cardinality check:
`COUNT(DISTINCT agent_id)` vs. `COUNT(*)`; `COUNT(DISTINCT agent_name)`;
row-level inspection of a single `agent_id`'s full history sorted by
`updated_at` (confirmed no plausible correction/versioning pattern —
values are noise, not a real change history).

**Issue 2 (Borrower Dimension Corruption).** Cardinality check: 30,600 raw
rows vs. 11,015 unique `borrower_id`; distinct-value count on `name`;
row-level inspection of a single `borrower_id`'s full history.

**Issue 3 (Duplicate Payment Events).** Full-row `duplicated()` scan
across the raw `payments` table (not just `payment_id` — confirmed the
entire row repeats, ruling out legitimate multi-installment payments that
happen to share an ID).

**Issue 4 (Payment Reference Collisions).** Grouped raw `payments` by
`payment_reference`, found reference values shared across accounts with
no other overlapping field (different borrower, different date, different
amount) — inconsistent with a real duplicate transaction, consistent with
reference-number reuse noise in the data generator.

**Issue 5 (Unreliable Timezone Field).** Built an hour-of-day distribution
of `event_at` grouped by `timezone` label. A real calling operation
concentrates volume in business hours (9am–9pm local); this data shows a
statistically uniform distribution (coefficient of variation ~2.7–2.9%
across 24 hours) within every timezone label — no business-hours
clustering at all, regardless of which zone is attached.

**Issue 6 (Disposition Code Drift).** Cross-tabulated `disposition_code` ×
`disposition_version` (legacy/v1/v2). If this were a real schema
migration, one label would dominate one version. Instead, both codes
appear at nearly identical volumes (~1,300 each) in all three versions.

**Issue 7 (Denominator Inflation).** Built the recovery-rate metric two
ways and compared: (a) naive — `COUNT(DISTINCT recovered accounts) /
COUNT(DISTINCT worked accounts)`, two separate queries divided; (b)
corrected — a row-level cohort join requiring the same account to appear
in both the worked population and the SUCCESS-payment set for that month.
The two produced materially different answers, which is what surfaced the
bug.

**Issue 8 (Un-traceable Payment Reversals).** Attempted to join REVERSED
rows to SUCCESS rows on `account_id` + `payment_reference` (the only
plausible shared key) — zero matches found across 1,255 reversed
payments.

**Issue 9 (RPC Definition Breaks on a Loose Join).** Sanity-checked the
computed RPC rate against the independently computed contact rate; RPC
should be a subset of contact and roughly the same order of magnitude, not
two orders of magnitude smaller. Investigated the join and found
`call_dispositions` carries its own real foreign key, `call_id`, which the
day-level join was ignoring.

**Issue 10 (PTP Source-Channel Mix Ignored).** Checked
`promises_to_pay.source` and found PTPs split nearly evenly across CALL
(25%), FIELD (25%), SMS (25%), and WHATSAPP (25%).

**Issue 11 (Bad/Absurd Agent Session Durations).** Filtered for
`logout_at <= login_at` and for `duration_hr >= 16` (longer than any real
single shift).

**Issue 12 (Partial Final Month).** Computed `MIN(event_at)`/
`MAX(event_at)` across every event table (calls, payments, PTPs,
complaints, targeting, sessions, etc.).

---

## 3. Treatment

**Issue 1 (Agent Dimension Corruption).** `agent_id` is kept as the only
trustworthy key (it is the actual foreign key used by `calls`,
`call_dispositions`, `promises_to_pay`, and `field_visits`). A
best-effort current `status` snapshot (most recent `updated_at`) is
retained but flagged `LOW_SNAPSHOT_ONLY` confidence. `agent_name`,
`employee_code`, `vendor_id`, `team`, and `joined_at` are dropped from all
analytical use. Agent tenure is reconstructed instead from the first
transactional event (`MIN(event_at)` in `calls`) per `agent_id`.

**Issue 2 (Borrower Dimension Corruption).** `borrower_id` kept as the
sole identity key. Most-recent `updated_at` snapshot kept for coarse
geography (city/state) only, flagged `LOW_ATTRIBUTES_ONLY_ID_STABLE`.
Name/phone/email are never used in any join or matching logic anywhere in
the pipeline.

**Issue 3 (Duplicate Payment Events).** Dropped in the golden
`payments_golden` table (kept the first occurrence). A small number (14)
of `payment_id` values had genuinely conflicting field values across their
"duplicate" rows — these were resolved by keeping the most recent
`event_at`.

**Issue 4 (Payment Reference Collisions).** `payment_reference` is
explicitly excluded as a deduplication key anywhere in the pipeline
(Issue 3's fix uses full-row matching instead).

**Issue 5 (Unreliable Timezone Field).** `event_at` is used as-is, with no
timezone offset correction applied. Documented as an unresolved
limitation rather than silently patched.

**Issue 6 (Disposition Code Drift).** Standardized both labels to a
single canonical code, `PTP`, in the golden `call_dispositions_golden`
table (`disposition_code_std` column; original `disposition_code`
retained for audit).

**Issue 7 (Denominator Inflation).** Rebuilt every recovery-rate
calculation in this project (notebook, SQL, dashboard) on the corrected
cohort-join definition. The naive definition is retained side-by-side
specifically to show the gap.

**Issue 8 (Un-traceable Payment Reversals).** Reversals are netted at the
portfolio-month level (`SUM(SUCCESS) - SUM(REVERSED)` within the same
calendar month) rather than at the individual-transaction level.

**Issue 9 (RPC Definition Breaks on a Loose Join).** Rebuilt RPC using the
actual foreign key: an ANSWERED call joined to its `call_dispositions` row
via `call_id`, counted as RPC if the linked disposition is anything other
than `NO_CONTACT`/`WRONG_NUMBER`.

**Issue 10 (PTP Source-Channel Mix Ignored).** Redefined PTP rate over
the full worked population (all channels), not just call-contacted
accounts.

**Issue 11 (Bad/Absurd Agent Session Durations).** A filter is in place
in the golden pipeline (`clean.agent_sessions_clean`) to exclude such
rows. In this run, zero rows were removed — the filter remains a
standing guardrail for future data loads.

**Issue 12 (Partial Final Month).** All trend and MoM calculations in
this project restrict to the 7 complete calendar months (Jan–Jul). August
is reported separately and never blended into a trend line.

---

## 4. Business Impact

**Issue 1 (Agent Dimension Corruption).** This table cannot support any
"who is this agent / what team / how long have they worked here" claim.
Any report showing "Team X outperforms Team Y" or "agents with 6+ months
tenure convert better," built directly on this table, would be built on
fabricated patterns. This is the single biggest identity-integrity risk in
the dataset.

**Issue 2 (Borrower Dimension Corruption).** Any city/state/demographic
cut of recovery performance carries real uncertainty and should be
labeled best-effort. No customer-facing communication should be generated
from this table's name/phone/email fields without a separate, trustworthy
identity source.

**Issue 3 (Duplicate Payment Events).** Left uncorrected, these ~250
duplicate cash events would inflate reported SUCCESS recovery by ₹25.0
million across the period (~0.36% of total recovered cash over 7 months)
— small as a share of the total, but large enough to distort a
month-on-month comparison if left in.

**Issue 4 (Payment Reference Collisions).** Had this field been used
naively for dedup, the pipeline would have wrongly deleted genuine,
distinct transactions belonging to different borrowers — a more damaging
error than the duplicates it would have caught, since it silently removes
real recovered cash rather than double-counting it.

**Issue 5 (Unreliable Timezone Field).** Any "best time to call"
staffing-optimization analysis, or any report claiming a genuine
local-hour calling pattern, built on this field would be fabricated. This
blocks call-time optimization by geography until the source system
provides a trustworthy local-time signal.

**Issue 6 (Disposition Code Drift).** Before correction, any PTP-rate
metric filtering on only one of the two labels would have undercounted
true PTP volume by roughly half — large enough to manufacture a false
"PTP generation declined" narrative if the label mix shifted between
reporting periods.

**Issue 7 (Denominator Inflation).** The naive definition overstates the
true recovery rate by 2.5–2.9 percentage points every single month (e.g.
10.54% naive vs. 8.09% corrected in January) — a stable ~30% relative
inflation. Any historical recovery-rate figure quoted from an existing
dashboard should be treated as ~30% too optimistic until confirmed to use
cohort-join logic. This is large enough on its own to be a plausible
source of an inflated headline "improvement" number.

**Issue 8 (Un-traceable Payment Reversals).** A reversal that logically
belongs to a payment made in the previous month will be netted against
the current month's total instead, slightly overstating month-to-month
volatility at calendar boundaries.

**Issue 9 (RPC Definition Breaks on a Loose Join).** Had the broken 0.04%
figure shipped to a dashboard unchecked, it would have signaled a
near-total operational failure in right-party contact and could have
triggered a costly, unnecessary process overhaul based on a join bug
rather than a real problem.

**Issue 10 (PTP Source-Channel Mix Ignored).** The call-only denominator
would have systematically undercounted roughly 75% of true
PTP-generation volume, and would have made non-voice channels (field,
SMS, WhatsApp) look artificially ineffective in any channel-comparison
report — directly relevant to the ₹10 Cr channel-investment decision.

**Issue 11 (Bad/Absurd Agent Session Durations).** None in the current
period (no bad rows found), but this check protects the
recovery-per-agent-hour productivity metric from being skewed by corrupt
session logs in future data.

**Issue 12 (Partial Final Month).** Including August as if it were a full
month would show a fake ~74% "collapse" in recovered amount (₹172M in July
vs. ₹44M in a partial August), purely from truncation — enough to trigger
a false-alarm escalation if it reached a leadership dashboard unlabeled.
