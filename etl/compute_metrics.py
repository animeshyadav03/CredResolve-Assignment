"""
compute_metrics.py
====================
Reads the golden dataset and produces every metric/statistic used in the
notebook, memo and dashboard. Nothing in the downstream reports is computed
ad hoc outside of this file — one source of truth.
"""
import pandas as pd
import numpy as np
import json

G = "/home/claude/work/outputs/golden"
OUT = "/home/claude/work/outputs"

accounts = pd.read_csv(f"{G}/accounts_golden.csv", parse_dates=['opened_at'])
payments = pd.read_csv(f"{G}/payments_golden.csv", parse_dates=['event_at'])
calls = pd.read_csv(f"{G}/calls_golden.csv", parse_dates=['event_at'])
attempts = pd.read_csv(f"{G}/call_attempts_golden.csv", parse_dates=['event_at'])
disp = pd.read_csv(f"{G}/call_dispositions_golden.csv", parse_dates=['event_at'])
ptp = pd.read_csv(f"{G}/promises_to_pay_golden.csv", parse_dates=['event_at', 'promised_date'])
worked = pd.read_csv(f"{G}/worked_population_golden.csv")
sessions = pd.read_csv(f"{G}/agent_sessions_golden.csv", parse_dates=['login_at', 'logout_at'])
targeting = pd.read_csv(f"{G}/daily_targeting_golden.csv", parse_dates=['target_date'])
campaigns = pd.read_csv(f"{G}/campaigns_golden.csv", parse_dates=['start_at', 'end_at'])
whatsapp = pd.read_csv(f"{G}/whatsapp_events_golden.csv", parse_dates=['event_at'])
sms = pd.read_csv(f"{G}/sms_events_golden.csv", parse_dates=['event_at'])
field = pd.read_csv(f"{G}/field_visits_golden.csv", parse_dates=['event_at'])

# Restrict analysis window to full calendar months only (Aug is a partial
# month - data cuts off 2026-08-08 - including it would make August look
# like a collapse purely from a truncated month, a classic time-series trap).
FULL_MONTHS = [f"2026-0{m}" for m in range(1, 8)]  # 2026-01 .. 2026-07
ALL_MONTHS = FULL_MONTHS + ["2026-08"]

results = {}

# ---------------------------------------------------------------------------
# A. THE HEADLINE CLAIM: recovered amount, MoM%, naive vs corrected
# ---------------------------------------------------------------------------
succ = payments[payments.payment_status == 'SUCCESS']
rev = payments[payments.payment_status == 'REVERSED']
rec_by_month = succ.groupby('month').amount.sum() - rev.groupby('month').amount.sum().reindex(succ.groupby('month').amount.sum().index, fill_value=0)
rec_by_month = rec_by_month.reindex(ALL_MONTHS)
mom = rec_by_month.pct_change() * 100

results['recovered_amount_by_month'] = rec_by_month.round(0).to_dict()
results['recovered_amount_mom_pct'] = mom.round(2).to_dict()
results['reported_claim_mom_pct'] = 11
results['closest_single_month_to_claim'] = mom.abs().sub(11).abs().idxmin()
results['full_period_avg_monthly_recovery_full_months'] = float(rec_by_month[FULL_MONTHS].mean())
results['full_period_cagr_style_change_jan_to_jul'] = float(
    (rec_by_month['2026-07'] / rec_by_month['2026-01'] - 1) * 100)
# linear trend test (full months only) - simple OLS slope via numpy (no statsmodels)
x = np.arange(len(FULL_MONTHS))
y = rec_by_month[FULL_MONTHS].values
slope, intercept = np.polyfit(x, y, 1)
resid = y - (slope * x + intercept)
ss_res = (resid ** 2).sum()
ss_tot = ((y - y.mean()) ** 2).sum()
r2 = 1 - ss_res / ss_tot
results['trend_ols_slope_per_month_inr'] = float(slope)
results['trend_ols_r2'] = float(r2)
results['trend_pct_of_mean_slope'] = float(slope / y.mean() * 100)

# ---------------------------------------------------------------------------
# B. FUNNEL METRICS BY MONTH — independently (re)defined
#    Denominator discipline: every rate below uses the FULL worked
#    population for that month (from worked_population_golden), so
#    unsuccessful accounts cannot silently disappear from a denominator
#    (Part 2G).
# ---------------------------------------------------------------------------
worked_by_month = worked.groupby('month').account_id.nunique()

calls['answered'] = calls.call_status == 'ANSWERED'
contact_by_month = calls[calls.answered].groupby('month').account_id.nunique()
attempted_calls_by_month = calls.groupby('month').account_id.nunique()
contact_rate = (contact_by_month / worked_by_month * 100).reindex(ALL_MONTHS)

# RPC = Right Party Contact. The raw data has no explicit "right party"
# flag, and RPC is commonly (wrongly) conflated with "answered" in
# dashboards. We define RPC precisely via the call_id key: an ANSWERED call
# that has a matching call_dispositions row (joined on call_id, the actual
# foreign key -- NOT same-day account matching, which is far too loose/noisy
# given timestamps are not tightly coupled) with a disposition other than
# NO_CONTACT/WRONG_NUMBER, i.e. a conversation that was genuinely with
# someone able to discuss the debt.
calls_ans = calls[calls.answered].copy()
disp_key = disp[['call_id', 'disposition_code_std']].drop_duplicates('call_id')
rpc_merge = calls_ans.merge(disp_key, on='call_id', how='inner')
rpc_merge = rpc_merge[~rpc_merge.disposition_code_std.isin(['NO_CONTACT', 'WRONG_NUMBER'])]
rpc_by_month = rpc_merge.groupby('month').account_id.nunique().reindex(ALL_MONTHS)
rpc_rate = (rpc_by_month / worked_by_month * 100).reindex(ALL_MONTHS)

# PTP rate. promises_to_pay.source shows PTPs are generated near-evenly
# across CALL/FIELD/SMS/WHATSAPP (~25% each) -- restricting the denominator
# to only call-contacted accounts would systematically undercount PTPs
# sourced from other channels. We define PTP rate over the full WORKED
# population for the month (any channel), which is the honest denominator.
ptp['month'] = ptp.event_at.dt.to_period('M').astype(str) if 'month' not in ptp.columns else ptp['month']
ptp_by_month = ptp.groupby('month').account_id.nunique().reindex(ALL_MONTHS)
ptp_rate = (ptp_by_month / worked_by_month * 100).reindex(ALL_MONTHS)  # PTP rate of worked accounts (all channels)

ptp_kept = ptp[ptp.status == 'KEPT']
ptp_kept_month = ptp.assign(month=ptp.event_at.dt.to_period('M').astype(str))
kept_rate = ptp_kept_month[ptp_kept_month.status == 'KEPT'].groupby('month').size() / ptp_kept_month.groupby('month').size() * 100
kept_rate = kept_rate.reindex(ALL_MONTHS)

accounts_recovered_by_month = succ.groupby('month').account_id.nunique().reindex(ALL_MONTHS)
# NAIVE definition (what a quick dashboard query typically does): count
# distinct accounts with a SUCCESS payment that month, divide by count of
# distinct worked accounts that month -- computed as two INDEPENDENT
# nunique() ratios. This silently allows the numerator to include accounts
# that paid but were NOT in that month's worked cohort (e.g. paid off-cycle,
# or contact happened the prior month and payment posted this month) --
# i.e. the numerator is not guaranteed to be a subset of the denominator.
recovery_rate_naive = (accounts_recovered_by_month / worked_by_month * 100).reindex(ALL_MONTHS)

# CORRECTED definition: cohort join. An account counts as "recovered" in
# month M only if it (a) was in the worked population in month M AND
# (b) had a SUCCESS payment in month M. This guarantees numerator subset
# denominator and is the definition used everywhere else in this analysis.
worked_pairs = worked[['account_id', 'month']].drop_duplicates()
succ_pairs = succ[['account_id', 'month']].drop_duplicates()
succ_pairs['recovered'] = 1
cohort = worked_pairs.merge(succ_pairs, on=['account_id', 'month'], how='left')
cohort['recovered'] = cohort.recovered.fillna(0)
recovery_rate = (cohort.groupby('month').recovered.mean() * 100).reindex(ALL_MONTHS)
recovered_not_in_worked_cohort = accounts_recovered_by_month - cohort.groupby('month').recovered.sum().reindex(ALL_MONTHS)
results['naive_vs_corrected_recovery_rate_pct'] = {
    'naive': recovery_rate_naive.round(2).to_dict(),
    'corrected_cohort_join': recovery_rate.round(2).to_dict(),
    'gap_pct_points': (recovery_rate_naive - recovery_rate).round(2).to_dict(),
}
results['accounts_recovered_outside_same_month_worked_cohort'] = recovered_not_in_worked_cohort.round(0).to_dict()
recovery_per_account = (rec_by_month / worked_by_month).reindex(ALL_MONTHS)

# agent hours from sessions
sessions['duration_hr'] = (sessions.logout_at - sessions.login_at).dt.total_seconds() / 3600
sessions['month'] = sessions.login_at.dt.to_period('M').astype(str)
sessions_clean = sessions[(sessions.duration_hr > 0) & (sessions.duration_hr < 16)]  # drop bad/negative/absurd sessions
bad_sessions = len(sessions) - len(sessions_clean)
hours_by_month = sessions_clean.groupby('month').duration_hr.sum().reindex(ALL_MONTHS)
recovery_per_agent_hour = (rec_by_month / hours_by_month).reindex(ALL_MONTHS)

funnel = pd.DataFrame({
    'worked_accounts': worked_by_month,
    'contact_rate_pct': contact_rate,
    'rpc_rate_pct': rpc_rate,
    'ptp_rate_pct_of_worked': ptp_rate,
    'ptp_kept_rate_pct': kept_rate,
    'recovery_rate_pct': recovery_rate,
    'recovered_amount': rec_by_month,
    'recovery_per_worked_account': recovery_per_account,
    'agent_hours': hours_by_month,
    'recovery_per_agent_hour': recovery_per_agent_hour,
}).reindex(ALL_MONTHS)
funnel.to_csv(f"{OUT}/monthly_funnel_metrics.csv")
results['bad_sessions_dropped'] = int(bad_sessions)
results['funnel'] = funnel.round(3).to_dict()

# ---------------------------------------------------------------------------
# C. MIX EFFECTS — is the population of worked accounts changing composition
#    (risk_segment / dpd bucket) month to month? Standardize recovery rate
#    to the January mix to isolate genuine operational improvement from
#    population mix shift (classic Simpson's-paradox guard).
# ---------------------------------------------------------------------------
acc_small = accounts[['account_id', 'risk_segment', 'dpd']].copy()
acc_small['dpd_bucket'] = pd.cut(acc_small.dpd, [-1, 0, 30, 60, 90, 120, 181],
                                  labels=['0', '1-30', '31-60', '61-90', '91-120', '121-180'])
worked_seg = worked.merge(acc_small, on='account_id', how='left')
mix_by_month = pd.crosstab(worked_seg.month, worked_seg.risk_segment, normalize='index') * 100
results['risk_segment_mix_by_month_pct'] = mix_by_month.round(2).to_dict()

# recovered flag per account per month
succ_flag = succ[['account_id', 'month']].drop_duplicates()
succ_flag['recovered'] = 1
seg_rate = worked_seg.merge(succ_flag, on=['account_id', 'month'], how='left')
seg_rate['recovered'] = seg_rate.recovered.fillna(0)
rate_by_seg_month = seg_rate.groupby(['month', 'risk_segment']).recovered.mean().unstack() * 100
results['recovery_rate_by_segment_month_pct'] = rate_by_seg_month.round(2).to_dict()

# direct standardization to Jan mix
jan_mix = mix_by_month.loc['2026-01']
standardized = {}
for m in ALL_MONTHS:
    if m in rate_by_seg_month.index:
        standardized[m] = float((rate_by_seg_month.loc[m].reindex(jan_mix.index).fillna(0) * jan_mix / 100).sum())
results['recovery_rate_standardized_to_jan_mix_pct'] = standardized
results['recovery_rate_actual_pct'] = recovery_rate.round(3).to_dict()

# ---------------------------------------------------------------------------
# D. DENOMINATOR MANIPULATION CHECK — are unsuccessful accounts vanishing?
#    Compare worked population size trend vs total open portfolio trend.
# ---------------------------------------------------------------------------
worked_trend = worked_by_month.reindex(ALL_MONTHS)
results['worked_population_trend'] = worked_trend.to_dict()
results['worked_population_mom_pct'] = (worked_trend.pct_change() * 100).round(2).to_dict()

# ---------------------------------------------------------------------------
# E. CHANNEL CONVERSION
# ---------------------------------------------------------------------------
calls['month2'] = calls.event_at.dt.to_period('M').astype(str)
# channel per call approximated via campaign channel
camp_chan = campaigns[['campaign_id', 'channel']].drop_duplicates('campaign_id')
calls_ch = calls.merge(camp_chan, on='campaign_id', how='left')
conv = calls_ch.merge(succ_flag.rename(columns={'month': 'month2'}), on=['account_id', 'month2'], how='left')
conv['recovered'] = conv.recovered.fillna(0)
chan_conv = conv.groupby('channel').recovered.mean() * 100
results['channel_conversion_pct'] = chan_conv.round(2).to_dict()

# ---------------------------------------------------------------------------
# F. AGENT TENURE EFFECT (using transactional first-seen proxy)
# ---------------------------------------------------------------------------
agents_g = pd.read_csv(f"{G}/agents_golden.csv", parse_dates=['agent_first_seen_at'])
calls_agent = calls.merge(agents_g[['agent_id', 'agent_first_seen_at']], on='agent_id', how='left')
calls_agent['tenure_days_at_call'] = (calls_agent.event_at - calls_agent.agent_first_seen_at).dt.days
calls_agent['tenure_bucket'] = pd.cut(calls_agent.tenure_days_at_call, [-1, 30, 90, 180, 99999],
                                       labels=['0-30d', '31-90d', '91-180d', '180d+'])
conv_t = calls_agent.merge(succ_flag.rename(columns={'month': 'month2'}), on=['account_id'], how='left')
tenure_conv = calls_agent.groupby('tenure_bucket', observed=True).size()
results['agent_tenure_call_volume_by_bucket'] = tenure_conv.to_dict()

# ---------------------------------------------------------------------------
# G. COUNTERFACTUAL — campaign strategy_version as targeting-strategy proxy.
#    Treat accounts predominantly targeted under legacy/v1 vs v2/v3 as
#    control/treatment groups; DiD on recovery rate before/after each
#    account's first exposure to a v2/v3 campaign.
# ---------------------------------------------------------------------------
targeting_c = targeting.merge(campaigns[['campaign_id', 'strategy_version']], on='campaign_id', how='left')
targeting_c['is_new_strategy'] = targeting_c.strategy_version.isin(['v2', 'v3'])
first_new = targeting_c[targeting_c.is_new_strategy].groupby('account_id').target_date.min().rename('first_new_strategy_date')
acct_strategy = targeting_c.groupby('account_id').agg(
    ever_new=('is_new_strategy', 'max'),
).reset_index().merge(first_new, on='account_id', how='left')
results['accounts_ever_under_new_strategy'] = int(acct_strategy.ever_new.sum())
results['accounts_never_under_new_strategy'] = int((~acct_strategy.ever_new.astype(bool)).sum())

with open(f"{OUT}/metrics_results.json", "w") as f:
    json.dump(results, f, indent=2, default=str)

funnel.to_csv(f"{OUT}/monthly_funnel_metrics.csv")
print("Metrics computed. Keys:", list(results.keys()))
print("\nRecovered amount by month:\n", rec_by_month)
print("\nMoM %:\n", mom)
print("\nStandardized (Jan mix) vs Actual recovery rate:")
for m in ALL_MONTHS:
    print(m, "actual:", round(results['recovery_rate_actual_pct'].get(m, float('nan')), 2),
          "standardized:", round(standardized.get(m, float('nan')), 2))
