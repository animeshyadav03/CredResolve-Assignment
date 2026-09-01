-- =============================================================================
-- 04_metrics.sql
-- Collections Analytics — Metric Definitions (independently redefined, with
-- the reasoning for each definition documented inline, per assignment
-- Part 3). Every metric here is grounded in golden.* views only.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- METRIC: Monthly recovered amount (headline KPI)
-- Definition: SUM(SUCCESS payments) - SUM(REVERSED payments) in the month.
-- Netting is done at PORTFOLIO-MONTH grain, not per-transaction, because
-- REVERSED rows cannot be traced to a specific original SUCCESS row
-- (payment_reference collides across unrelated accounts — see DQ report).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW golden.metric_recovered_amount_by_month AS
SELECT
    txn_month AS month,
    SUM(CASE WHEN payment_status = 'SUCCESS' THEN amount ELSE 0 END)
      - SUM(CASE WHEN payment_status = 'REVERSED' THEN amount ELSE 0 END) AS recovered_amount,
    LAG(SUM(CASE WHEN payment_status = 'SUCCESS' THEN amount ELSE 0 END)
      - SUM(CASE WHEN payment_status = 'REVERSED' THEN amount ELSE 0 END))
      OVER (ORDER BY txn_month) AS prev_month_amount,
    ROUND(100.0 * (
        (SUM(CASE WHEN payment_status = 'SUCCESS' THEN amount ELSE 0 END)
          - SUM(CASE WHEN payment_status = 'REVERSED' THEN amount ELSE 0 END))
        / NULLIF(LAG(SUM(CASE WHEN payment_status = 'SUCCESS' THEN amount ELSE 0 END)
          - SUM(CASE WHEN payment_status = 'REVERSED' THEN amount ELSE 0 END))
          OVER (ORDER BY txn_month), 0) - 1), 2) AS mom_pct_change
FROM golden.fct_payment
GROUP BY txn_month;

-- -----------------------------------------------------------------------------
-- METRIC: Recovery Rate — CORRECTED (cohort-join) definition.
-- WHY THIS DEFINITION: a naive query computing
--   COUNT(DISTINCT recovered accounts) / COUNT(DISTINCT worked accounts)
-- as two INDEPENDENT nunique() aggregates (no join) silently allows the
-- numerator to include accounts that paid but were NOT in that month's
-- worked cohort (e.g. paid off-cycle, contact happened the prior month).
-- We measured this gap directly: the naive ratio overstates the true
-- (joined) rate by 2.5-2.9 percentage points in every single month of the
-- period — a ~30% relative inflation baked into any dashboard using the
-- naive form. The definition below fixes this by construction: an account
-- can only be "recovered" in month M if the SAME row also shows it was
-- worked in month M.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW golden.metric_recovery_rate_by_month AS
SELECT
    month,
    COUNT(*) AS worked_accounts,
    SUM(recovered_flag) AS recovered_accounts,
    ROUND(100.0 * SUM(recovered_flag) / NULLIF(COUNT(*), 0), 2) AS recovery_rate_pct,
    ROUND(SUM(recovered_amount) / NULLIF(COUNT(*), 0), 2) AS recovery_per_worked_account
FROM golden.fct_account_month_recovery
GROUP BY month;

-- -----------------------------------------------------------------------------
-- METRIC: Contact Rate — % of worked accounts with >=1 ANSWERED call.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW golden.metric_contact_rate_by_month AS
SELECT
    w.month,
    COUNT(DISTINCT w.account_id) AS worked_accounts,
    COUNT(DISTINCT CASE WHEN c.is_answered THEN c.account_id END) AS contacted_accounts,
    ROUND(100.0 * COUNT(DISTINCT CASE WHEN c.is_answered THEN c.account_id END)
        / NULLIF(COUNT(DISTINCT w.account_id), 0), 2) AS contact_rate_pct
FROM golden.fct_worked_account_month w
LEFT JOIN golden.fct_call c ON c.account_id = w.account_id AND c.event_month = w.month
GROUP BY w.month;

-- -----------------------------------------------------------------------------
-- METRIC: Right-Party-Contact (RPC) Rate.
-- WHY THIS DEFINITION: RPC is not "answered" (that's call_status), it's
-- "reached a human who could discuss the debt". We key this off the real
-- foreign key (call_id -> disposition), not a loose same-day/account match,
-- because timestamps between a call and its disposition are not reliably
-- same-day in this data (a same-day match produces a near-zero, clearly
-- broken rate: see DQ report). RPC = ANSWERED call whose linked disposition
-- is anything other than NO_CONTACT/WRONG_NUMBER.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW golden.metric_rpc_rate_by_month AS
SELECT
    w.month,
    COUNT(DISTINCT w.account_id) AS worked_accounts,
    COUNT(DISTINCT CASE WHEN c.is_rpc THEN c.account_id END) AS rpc_accounts,
    ROUND(100.0 * COUNT(DISTINCT CASE WHEN c.is_rpc THEN c.account_id END)
        / NULLIF(COUNT(DISTINCT w.account_id), 0), 2) AS rpc_rate_pct
FROM golden.fct_worked_account_month w
LEFT JOIN golden.fct_call c ON c.account_id = w.account_id AND c.event_month = w.month
GROUP BY w.month;

-- -----------------------------------------------------------------------------
-- METRIC: PTP Rate — % of WORKED accounts (all channels) with a PTP.
-- WHY THIS DEFINITION: promises_to_pay.source shows PTPs originate from
-- CALL/FIELD/SMS/WHATSAPP in a near-even split (~25% each). Restricting the
-- denominator to only call-contacted accounts (a common dashboard shortcut)
-- would systematically undercount 75% of the true PTP-generation surface.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW golden.metric_ptp_rate_by_month AS
SELECT
    w.month,
    COUNT(DISTINCT w.account_id) AS worked_accounts,
    COUNT(DISTINCT p.account_id) AS ptp_accounts,
    ROUND(100.0 * COUNT(DISTINCT p.account_id) / NULLIF(COUNT(DISTINCT w.account_id), 0), 2) AS ptp_rate_pct
FROM golden.fct_worked_account_month w
LEFT JOIN golden.fct_ptp p ON p.account_id = w.account_id AND p.event_month = w.month
GROUP BY w.month;

-- -----------------------------------------------------------------------------
-- METRIC: PTP Kept Rate — of all PTPs whose status is terminal (KEPT or
-- BROKEN — excludes OPEN/CANCELLED, which have not yet resolved).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW golden.metric_ptp_kept_rate_by_month AS
SELECT
    event_month AS month,
    COUNT(*) FILTER (WHERE status IN ('KEPT', 'BROKEN')) AS resolved_ptps,
    COUNT(*) FILTER (WHERE status = 'KEPT') AS kept_ptps,
    ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'KEPT')
        / NULLIF(COUNT(*) FILTER (WHERE status IN ('KEPT', 'BROKEN')), 0), 2) AS ptp_kept_rate_pct
FROM golden.fct_ptp
GROUP BY event_month;

-- -----------------------------------------------------------------------------
-- METRIC: Recovery per Agent-Hour — the true productivity metric (accounts
-- and rupees recovered relative to hours actually logged in, not headcount,
-- which is inflated by the corrupted agents dimension).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW golden.metric_recovery_per_agent_hour AS
SELECT
    r.month,
    SUM(r.recovered_amount) AS recovered_amount,
    SUM(h.agent_hours) AS agent_hours,
    ROUND(SUM(r.recovered_amount) / NULLIF(SUM(h.agent_hours), 0), 2) AS recovery_per_agent_hour
FROM (SELECT month, SUM(recovered_amount) AS recovered_amount
      FROM golden.fct_account_month_recovery GROUP BY month) r
JOIN (SELECT month, SUM(agent_hours) AS agent_hours
      FROM golden.fct_agent_hours GROUP BY month) h USING (month)
GROUP BY r.month, h.month;  -- (grouped for clarity; already 1 row/month)

-- -----------------------------------------------------------------------------
-- METRIC: Channel Conversion — recovery rate attributed to each campaign
-- channel touching the account that month.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW golden.metric_channel_conversion AS
SELECT
    cm.channel,
    COUNT(DISTINCT c.account_id || '-' || c.event_month) AS touched_account_months,
    ROUND(100.0 * AVG(r.recovered_flag), 2) AS conversion_pct
FROM golden.fct_call c
JOIN clean.campaigns_clean cm ON cm.campaign_id = c.campaign_id
LEFT JOIN golden.fct_account_month_recovery r
    ON r.account_id = c.account_id AND r.month = c.event_month
GROUP BY cm.channel;

-- -----------------------------------------------------------------------------
-- METRIC: Cost per Rupee Recovered — DIRECTIONAL ONLY.
-- No salary/cost-center table exists in the source data. We proxy cost with
-- agent_hours * an assumed fully-loaded blended hourly cost (parameterized
-- below; replace with Finance's actual figure). This metric should be
-- treated as an index for trend purposes, NOT an audited cost figure, until
-- a real cost table is connected (see executive memo, "what we'd need").
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW golden.metric_cost_per_rupee_recovered AS
SELECT
    month,
    agent_hours,
    agent_hours * 350 AS assumed_labor_cost_inr,     -- <-- replace 350 (INR/hr) with real blended cost
    recovered_amount,
    ROUND((agent_hours * 350) / NULLIF(recovered_amount, 0), 4) AS cost_per_rupee_recovered
FROM golden.metric_recovery_per_agent_hour;
