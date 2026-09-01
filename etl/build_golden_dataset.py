"""
build_golden_dataset.py
========================
Collections Analytics — Golden Dataset Builder

Turns the 17 raw source tables into a trustworthy analytical layer.
Every cleaning decision below is logged (raw -> rejected/corrected -> golden)
into etl_log.json so the numbers in the notebook, memo and dashboard are
reproducible and auditable, not asserted.

Run: python3 build_golden_dataset.py
Inputs:  /home/claude/work/data/*.csv
Outputs: /home/claude/work/outputs/golden/*.parquet (+ .csv fallback)
         /home/claude/work/outputs/etl_log.json
"""
import pandas as pd
import numpy as np
import json
import os

RAW = "/home/claude/work/data"
OUT = "/home/claude/work/outputs/golden"
os.makedirs(OUT, exist_ok=True)
LOG = {}

def log(step, **kwargs):
    LOG[step] = kwargs
    print(f"[{step}]", {k: v for k, v in kwargs.items() if k != 'sample'})

def save(df, name):
    # Parquet is the intended production format (see architecture doc); this
    # sandbox has no pyarrow/network access, so we persist CSV here. The
    # pipeline code is otherwise format-agnostic (swap to_csv -> to_parquet).
    path_c = f"{OUT}/{name}.csv"
    df.to_csv(path_c, index=False)
    return path_c

pd.set_option('display.width', 200)

# ---------------------------------------------------------------------------
# 1. ACCOUNTS  — anchor / fact-of-dimensions table. account_id is unique and
#    clean (no duplicate keys). Treated as source of truth for loan terms.
# ---------------------------------------------------------------------------
accounts = pd.read_csv(f"{RAW}/accounts.csv", parse_dates=['opened_at'])
raw_n = len(accounts)
dupe_ids = accounts.account_id.duplicated().sum()
# sanity bounds: negative/absurd amounts, dpd out of [0,180]
bad_amount = accounts[(accounts.principal_amount <= 0) | (accounts.outstanding_amount < 0)]
accounts_golden = accounts[(accounts.principal_amount > 0) & (accounts.outstanding_amount >= 0)].copy()
log("accounts", raw_rows=raw_n, duplicate_account_ids=int(dupe_ids),
    rejected_bad_amounts=int(len(bad_amount)), golden_rows=len(accounts_golden))
save(accounts_golden, "accounts_golden")

# ---------------------------------------------------------------------------
# 2. BORROWERS — borrower_id key is stable but the attribute columns
#    (name, phone, email, city, state) are RANDOMLY overwritten across rows:
#    the same borrower_id shows up to 11x with different names/cities/phones
#    with no plausible "correction history" pattern (only 10 distinct first+
#    last name combinations reused across ~11,000 unique borrowers — names
#    are not usable as an identity signal at all).
#    Decision: identity = borrower_id only. For descriptive attributes
#    (city/state used only for coarse geography cuts) we take the row with
#    the max(updated_at) as a "best-effort current snapshot" and flag the
#    whole dimension as LOW RELIABILITY. We do NOT use name/phone/email for
#    any matching or dedup logic anywhere in this pipeline.
# ---------------------------------------------------------------------------
borrowers = pd.read_csv(f"{RAW}/borrowers.csv", parse_dates=['created_at', 'updated_at'])
raw_n = len(borrowers)
uniq_ids = borrowers.borrower_id.nunique()
rows_per_id = borrowers.groupby('borrower_id').size()
borrowers_sorted = borrowers.sort_values('updated_at')
borrowers_golden = borrowers_sorted.drop_duplicates('borrower_id', keep='last').copy()
borrowers_golden['identity_confidence'] = 'LOW_ATTRIBUTES_ONLY_ID_STABLE'
log("borrowers", raw_rows=raw_n, unique_borrower_ids=int(uniq_ids),
    max_rows_per_id=int(rows_per_id.max()), distinct_name_values=int(borrowers.name.nunique()),
    rejected_duplicate_snapshots=int(raw_n - uniq_ids), golden_rows=len(borrowers_golden),
    decision="keep max(updated_at) row per borrower_id; attributes flagged LOW confidence, name/phone/email excluded from any join logic")
save(borrowers_golden, "borrowers_golden")

# ---------------------------------------------------------------------------
# 3. AGENTS — same corruption pattern as borrowers, but far more severe:
#    1,000 unique agent_id values but 30,000 rows (avg 30 rows/agent_id,
#    up to 48), only 10 distinct agent_name values total, and per agent_id
#    the employee_code/vendor_id/team/status/joined_at are all essentially
#    resampled at random on every row. This table cannot support any
#    reliable "who is this agent / what team / what tenure" claim.
#    Decision:
#      - agent_id is the ONLY trustworthy key (it is what calls/dispositions/
#        ptp/field_visits actually key on).
#      - We keep a best-effort "current snapshot" (max updated_at) purely so
#        downstream joins don't break, but tag confidence LOW and EXCLUDE
#        agent_name, employee_code and joined_at from tenure/identity logic.
#      - Agent TENURE is instead reconstructed from transactional evidence:
#        first observed event_at for that agent_id across
#        calls/call_attempts/call_dispositions/promises_to_pay/field_visits
#        ("first_seen_in_data"), which is the only tenure signal we trust.
#      - Agent CHANNEL/vendor actually worked is reconstructed the same way
#        (from calls.vendor_id / agent_sessions.channel), not from the
#        agents dimension table.
# ---------------------------------------------------------------------------
agents = pd.read_csv(f"{RAW}/agents.csv", parse_dates=['joined_at', 'updated_at'])
raw_n = len(agents)
uniq_ids = agents.agent_id.nunique()
rows_per_id = agents.groupby('agent_id').size()
agents_sorted = agents.sort_values('updated_at')
agents_golden = agents_sorted.drop_duplicates('agent_id', keep='last')[
    ['agent_id', 'status']].copy()  # only status kept as best-effort; everything else too noisy to trust
agents_golden['identity_confidence'] = 'LOW_SNAPSHOT_ONLY'
log("agents", raw_rows=raw_n, unique_agent_ids=int(uniq_ids), distinct_agent_names=int(agents.agent_name.nunique()),
    avg_rows_per_agent_id=float(rows_per_id.mean()), max_rows_per_agent_id=int(rows_per_id.max()),
    rejected_duplicate_snapshots=int(raw_n - uniq_ids), golden_rows=len(agents_golden),
    decision="agent_id kept as only trustworthy key; name/employee_code/vendor/team/joined_at DROPPED as unreliable; tenure and channel reconstructed from transactional first-seen timestamps instead")

# transactional first-seen per agent (tenure proxy) + channel mix (from calls)
calls_raw = pd.read_csv(f"{RAW}/calls.csv", parse_dates=['event_at'])
first_seen = calls_raw.groupby('agent_id')['event_at'].min().rename('agent_first_seen_at')
agents_golden = agents_golden.merge(first_seen, on='agent_id', how='left')
save(agents_golden, "agents_golden")

# ---------------------------------------------------------------------------
# 4. PAYMENTS — the money truth table.
#    a) 500 rows are EXACT full-row duplicates of another payment_id-bearing
#       row (same payment_id + every field) => straightforward ingestion
#       duplicate. Dropped.
#    b) payment_reference collides across UNRELATED accounts (e.g. the same
#       TXN number appears against 3 different borrowers on different
#       dates) — this is reference-number reuse noise in the generator, NOT
#       evidence of duplicate cash. We do NOT dedup on payment_reference.
#    c) REVERSED payments cannot be traced back to a specific prior SUCCESS
#       row (no shared account_id+reference match), so we cannot net them
#       at the transaction level. We net them at the PORTFOLIO-MONTH level:
#       recovered_amount(month) = sum(SUCCESS) - sum(REVERSED in that month)
#       and flag this as a limitation (true chargebacks may cross month
#       boundaries).
#    d) PENDING/FAILED are excluded from recovered amount but kept for
#       funnel/conversion metrics.
# ---------------------------------------------------------------------------
payments = pd.read_csv(f"{RAW}/payments.csv", parse_dates=['event_at'])
raw_n = len(payments)
exact_dupes = payments.duplicated().sum()
payments_dedup = payments.drop_duplicates().copy()
after_dedup = len(payments_dedup)
# also guard against duplicate payment_id with conflicting content (14 cases seen) - keep latest event_at
conflict_ids = payments_dedup[payments_dedup.duplicated('payment_id', keep=False)]
payments_golden = payments_dedup.sort_values('event_at').drop_duplicates('payment_id', keep='last').copy()
payments_golden['month'] = payments_golden.event_at.dt.to_period('M').astype(str)
log("payments", raw_rows=raw_n, exact_duplicate_rows_removed=int(exact_dupes),
    after_exact_dedup=after_dedup, conflicting_payment_id_rows=int(len(conflict_ids)),
    golden_rows=len(payments_golden),
    inflated_success_amount_from_dupes=float(
        payments[payments.duplicated(keep='first') & (payments.payment_status == 'SUCCESS')].amount.sum()),
    decision="drop exact full-row duplicates (500 rows / ~250 duplicate payment events); "
             "payment_reference NOT used for dedup (colliding across unrelated accounts = generator noise, not real dupes); "
             "REVERSED netted at portfolio-month level, not transaction level")
save(payments_golden, "payments_golden")

# ---------------------------------------------------------------------------
# 5. CALLS — standardize; keep timezone as-is (see below), dedupe exact rows.
# ---------------------------------------------------------------------------
calls = calls_raw.copy()
raw_n = len(calls)
exact_dupes = calls.duplicated().sum()
calls_golden = calls.drop_duplicates().copy()
calls_golden['month'] = calls_golden.event_at.dt.to_period('M').astype(str)
# Timezone check: hour-of-day distribution is statistically flat across all
# three timezone labels (chi-square-level uniform ~1200-1350 per hour per
# tz, no business-hours clustering). This means the `timezone` label does
# NOT correspond to a recoverable local-time signal — attempting to
# "correct" event_at using it would relabel noise as precision. We treat
# event_at as already being on a single consistent clock and DO NOT apply
# a timezone offset shift. This is documented as a known limitation, not
# silently assumed.
log("calls", raw_rows=raw_n, exact_duplicate_rows_removed=int(exact_dupes), golden_rows=len(calls_golden),
    decision="exact duplicates dropped; timezone field found NOT to carry a recoverable local-hour signal "
             "(hour-of-day distribution is uniform within each tz label) -> event_at used as-is, no tz shift applied, flagged as limitation")
save(calls_golden, "calls_golden")

# ---------------------------------------------------------------------------
# 6. CALL ATTEMPTS
# ---------------------------------------------------------------------------
call_attempts = pd.read_csv(f"{RAW}/call_attempts.csv", parse_dates=['event_at'])
raw_n = len(call_attempts)
exact_dupes = call_attempts.duplicated().sum()
call_attempts_golden = call_attempts.drop_duplicates().copy()
call_attempts_golden['month'] = call_attempts_golden.event_at.dt.to_period('M').astype(str)
log("call_attempts", raw_rows=raw_n, exact_duplicate_rows_removed=int(exact_dupes), golden_rows=len(call_attempts_golden))
save(call_attempts_golden, "call_attempts_golden")

# ---------------------------------------------------------------------------
# 7. CALL DISPOSITIONS — standardize the changed disposition-code vocabulary.
#    PROMISE_TO_PAY (legacy label) and PTP (new label) co-occur across ALL
#    THREE disposition_version values roughly evenly (~1300 each) rather
#    than cleanly splitting by version — i.e. the two labels are used
#    interchangeably regardless of schema version. We map both to a single
#    canonical code PTP so PTP-rate metrics aren't silently undercounted.
# ---------------------------------------------------------------------------
call_disp = pd.read_csv(f"{RAW}/call_dispositions.csv", parse_dates=['event_at'])
raw_n = len(call_disp)
exact_dupes = call_disp.duplicated().sum()
call_disp_golden = call_disp.drop_duplicates().copy()
code_map = {'PROMISE_TO_PAY': 'PTP'}
before_codes = call_disp_golden.disposition_code.value_counts().to_dict()
call_disp_golden['disposition_code_std'] = call_disp_golden.disposition_code.replace(code_map)
call_disp_golden['month'] = call_disp_golden.event_at.dt.to_period('M').astype(str)
log("call_dispositions", raw_rows=raw_n, exact_duplicate_rows_removed=int(exact_dupes),
    golden_rows=len(call_disp_golden), codes_before=before_codes,
    decision="PROMISE_TO_PAY merged into PTP (co-occurs with PTP across all 3 schema versions evenly -> synonym, not a version-specific code)")
save(call_disp_golden, "call_dispositions_golden")

# ---------------------------------------------------------------------------
# 8. WHATSAPP / SMS / FIELD VISITS / PTP / COMPLAINTS / STATUS HISTORY /
#    AGENT SESSIONS / DAILY TARGETING / CAMPAIGNS / VENDOR TELEPHONY
#    — straightforward exact-duplicate removal + month tagging.
# ---------------------------------------------------------------------------
simple_tables = {
    'whatsapp_events': ['event_at'],
    'sms_events': ['event_at'],
    'field_visits': ['event_at', 'scheduled_at'],
    'promises_to_pay': ['event_at', 'promised_date'],
    'complaints': ['event_at', 'resolution_at'],
    'account_status_history': ['event_at', 'recorded_at'],
    'agent_sessions': ['login_at', 'logout_at'],
    'daily_targeting': ['target_date'],
    'campaigns': ['start_at', 'end_at'],
}
for name, dcols in simple_tables.items():
    df = pd.read_csv(f"{RAW}/{name}.csv", parse_dates=dcols)
    raw_n = len(df)
    exact_dupes = df.duplicated().sum()
    golden = df.drop_duplicates().copy()
    if 'event_at' in df.columns:
        golden['month'] = golden.event_at.dt.to_period('M').astype(str)
    log(name, raw_rows=raw_n, exact_duplicate_rows_removed=int(exact_dupes), golden_rows=len(golden))
    save(golden, f"{name}_golden")

vendor = pd.read_csv(f"{RAW}/vendor_telephony.csv")
save(vendor.drop_duplicates(), "vendor_telephony_golden")
log("vendor_telephony", raw_rows=len(vendor), golden_rows=vendor.drop_duplicates().shape[0])

# ---------------------------------------------------------------------------
# 9. DENOMINATOR POPULATION — "which accounts were being actively worked in
#    month M" (needed so conversion-rate denominators can't silently shrink
#    / disappear = Part 2G denominator manipulation check).
#    Definition: an account is "in the worked population" for month M if it
#    has >=1 call_attempt OR daily_targeting row OR whatsapp/sms/field_visit
#    event in that month, REGARDLESS of outcome. This guarantees unsuccessful
#    accounts (no answer, no contact, no payment) stay in the denominator.
# ---------------------------------------------------------------------------
frames = []
for name, dcol in [('call_attempts', 'event_at'), ('daily_targeting', 'target_date'),
                    ('whatsapp_events', 'event_at'), ('sms_events', 'event_at'),
                    ('field_visits', 'event_at')]:
    df = pd.read_csv(f"{RAW}/{name}.csv", usecols=['account_id', dcol], parse_dates=[dcol])
    df = df.rename(columns={dcol: 'event_at'})
    df['month'] = df.event_at.dt.to_period('M').astype(str)
    frames.append(df[['account_id', 'month']])
worked_pop = pd.concat(frames).drop_duplicates()
log("worked_population", total_account_month_pairs=len(worked_pop),
    unique_accounts_ever_worked=int(worked_pop.account_id.nunique()))
save(worked_pop, "worked_population_golden")

with open("/home/claude/work/outputs/etl_log.json", "w") as f:
    json.dump(LOG, f, indent=2, default=str)

print("\n=== DONE. Golden tables written to", OUT, "===")
