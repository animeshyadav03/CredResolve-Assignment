-- =============================================================================
-- 03_golden_views.sql
-- Collections Analytics — Golden Layer
-- Business-ready, denormalized views built on top of clean.*. These are the
-- tables analysts and BI tools should query — never staging or clean
-- directly. Grain is documented on every view.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS golden;

-- Grain: 1 row per account_id (current state)
CREATE OR REPLACE VIEW golden.dim_account AS
SELECT
    a.account_id,
    a.borrower_id,
    a.loan_type,
    a.principal_amount,
    a.outstanding_amount,
    a.dpd,
    CASE
        WHEN a.dpd = 0 THEN '0'
        WHEN a.dpd BETWEEN 1 AND 30 THEN '1-30'
        WHEN a.dpd BETWEEN 31 AND 60 THEN '31-60'
        WHEN a.dpd BETWEEN 61 AND 90 THEN '61-90'
        WHEN a.dpd BETWEEN 91 AND 120 THEN '91-120'
        ELSE '121-180'
    END AS dpd_bucket,
    a.risk_segment,
    a.status,
    a.opened_at,
    b.city,
    b.state,
    b.identity_confidence AS borrower_attribute_confidence
FROM clean.accounts_clean a
LEFT JOIN clean.borrowers_clean b USING (borrower_id);

-- Grain: 1 row per agent_id (current state, low-confidence attributes)
CREATE OR REPLACE VIEW golden.dim_agent AS
SELECT agent_id, status, agent_first_seen_at, identity_confidence
FROM clean.agents_clean;

-- Grain: 1 row per (account_id, calendar_month) that was actively worked
CREATE OR REPLACE VIEW golden.fct_worked_account_month AS
SELECT account_id, worked_month AS month
FROM clean.worked_population;

-- Grain: 1 row per successful/reversed cash event, netted to account-month
CREATE OR REPLACE VIEW golden.fct_payment AS
SELECT
    payment_id, account_id, borrower_id, event_at, txn_month,
    amount, payment_status, payment_method, provider_id
FROM clean.payments_clean;

-- Grain: 1 row per (account_id, month) — the recovery cohort join.
-- THIS is the corrected definition: an account counts as recovered in
-- month M only if it was BOTH worked in month M AND had a SUCCESS payment
-- in month M (numerator guaranteed subset of denominator). See
-- 04_metrics.sql for why the naive independent-count-ratio version
-- overstates this by ~2.5-2.9 points every month.
CREATE OR REPLACE VIEW golden.fct_account_month_recovery AS
SELECT
    w.account_id,
    w.month,
    CASE WHEN p.account_id IS NOT NULL THEN 1 ELSE 0 END AS recovered_flag,
    COALESCE(p.recovered_amount, 0) AS recovered_amount,
    COALESCE(r.reversed_amount, 0) AS reversed_amount
FROM golden.fct_worked_account_month w
LEFT JOIN (
    SELECT account_id, txn_month AS month, SUM(amount) AS recovered_amount
    FROM golden.fct_payment WHERE payment_status = 'SUCCESS'
    GROUP BY 1, 2
) p ON p.account_id = w.account_id AND p.month = w.month
LEFT JOIN (
    SELECT account_id, txn_month AS month, SUM(amount) AS reversed_amount
    FROM golden.fct_payment WHERE payment_status = 'REVERSED'
    GROUP BY 1, 2
) r ON r.account_id = w.account_id AND r.month = w.month;

-- Grain: 1 row per call
CREATE OR REPLACE VIEW golden.fct_call AS
SELECT
    c.call_id, c.account_id, c.borrower_id, c.event_at, c.event_month,
    c.agent_id, c.campaign_id, c.direction, c.vendor_id, c.call_status,
    c.duration_sec,
    (c.call_status = 'ANSWERED') AS is_answered,
    d.disposition_code_std,
    (d.disposition_code_std IS NOT NULL
        AND d.disposition_code_std NOT IN ('NO_CONTACT', 'WRONG_NUMBER')) AS is_rpc
FROM clean.calls_clean c
LEFT JOIN clean.call_dispositions_clean d ON d.call_id = c.call_id;

-- Grain: 1 row per PTP
CREATE OR REPLACE VIEW golden.fct_ptp AS
SELECT ptp_id, account_id, borrower_id, event_at, event_month, agent_id,
       promised_amount, promised_date, status, source
FROM clean.promises_to_pay_clean;

-- Grain: 1 row per agent-day worked-hours
CREATE OR REPLACE VIEW golden.fct_agent_hours AS
SELECT agent_id, session_month AS month, SUM(duration_hr) AS agent_hours
FROM clean.agent_sessions_clean
GROUP BY 1, 2;
