-- =============================================================================
-- 05_analytical_queries.sql
-- Collections Analytics — Data Forensics & Statistical Investigation queries
-- (assignment Parts 2, 3, 4). Each query is self-contained and commented
-- with what it detects and why it matters.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 2A. DUPLICATE PAYMENTS — exact full-row duplicates by payment_id
-- Finding: 500 rows / ~250 duplicate cash events, ~₹25.0M in SUCCESS amount
-- that would be double-counted if not deduplicated.
-- -----------------------------------------------------------------------------
SELECT
    COUNT(*) AS duplicate_rows,
    SUM(amount) FILTER (WHERE payment_status = 'SUCCESS') AS inflated_success_amount
FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY payment_id, account_id, event_at,
        payment_reference, amount, payment_status ORDER BY payment_id) AS rn
    FROM staging.stg_payments
) t
WHERE rn > 1;

-- -----------------------------------------------------------------------------
-- 2B. ATTRIBUTION ERRORS — is a payment being attributed to whichever
-- campaign/call happened most recently rather than the one that actually
-- drove it? Proxy check: for each SUCCESS payment, find the most recent
-- call on that account in the preceding 7 days and see how often more than
-- one campaign touched the account in that window (multi-touch ambiguity).
-- -----------------------------------------------------------------------------
WITH recent_touches AS (
    SELECT p.payment_id, p.account_id, p.event_at AS payment_at, c.campaign_id, c.event_at AS call_at
    FROM golden.fct_payment p
    JOIN golden.fct_call c
      ON c.account_id = p.account_id
     AND c.event_at BETWEEN p.event_at - INTERVAL '7 days' AND p.event_at
    WHERE p.payment_status = 'SUCCESS'
)
SELECT
    payment_id,
    COUNT(DISTINCT campaign_id) AS campaigns_touching_in_prior_7d
FROM recent_touches
GROUP BY payment_id
HAVING COUNT(DISTINCT campaign_id) > 1
ORDER BY campaigns_touching_in_prior_7d DESC;
-- Interpretation: any payment with >1 distinct campaign in the prior-7-day
-- window is at risk of "last touch wins" misattribution if the reporting
-- layer naively joins payment -> most recent call -> that call's campaign.
-- Recommend multi-touch or first-touch-in-cycle attribution, documented
-- explicitly, rather than silent last-touch.

-- -----------------------------------------------------------------------------
-- 2C. TIMEZONE PROBLEMS — hour-of-day distribution by timezone label.
-- Finding: distribution is statistically FLAT (~uniform 1200-1350 calls per
-- hour) within every timezone label. Real calling operations concentrate in
-- business hours; a flat distribution means the `timezone` column carries
-- NO recoverable local-time signal. Do not attempt to "correct" event_at
-- with a UTC offset derived from this column — it would relabel noise as
-- false precision.
-- -----------------------------------------------------------------------------
SELECT
    timezone,
    EXTRACT(HOUR FROM event_at) AS hour_of_day,
    COUNT(*) AS n_calls
FROM clean.calls_clean
GROUP BY timezone, EXTRACT(HOUR FROM event_at)
ORDER BY timezone, hour_of_day;

-- -----------------------------------------------------------------------------
-- 2D. VENDOR / DISPOSITION CODE MAPPING CHANGES over the period.
-- Finding: PROMISE_TO_PAY and PTP co-occur ~evenly across legacy/v1/v2
-- disposition_version rather than splitting cleanly by version -> synonyms,
-- not a real schema migration boundary. Standardized in 02_cleaning_dedup.sql.
-- -----------------------------------------------------------------------------
SELECT disposition_version, disposition_code, COUNT(*) AS n
FROM staging.stg_call_dispositions
GROUP BY disposition_version, disposition_code
ORDER BY disposition_version, disposition_code;

-- -----------------------------------------------------------------------------
-- 2E. AGENT IDENTITY PROBLEMS — rows per agent_id, distinct attribute values.
-- Finding: 1,000 unique agent_id values carry 30,000 rows (avg 30/agent, max
-- 48), with only 10 distinct agent_name values total across all of them.
-- This table cannot support a "who is this agent" claim on anything but
-- agent_id itself.
-- -----------------------------------------------------------------------------
SELECT
    COUNT(DISTINCT agent_id) AS unique_agent_ids,
    COUNT(*) AS total_rows,
    ROUND(COUNT(*) * 1.0 / COUNT(DISTINCT agent_id), 1) AS avg_rows_per_agent,
    COUNT(DISTINCT agent_name) AS distinct_names,
    COUNT(DISTINCT employee_code) AS distinct_employee_codes
FROM staging.stg_agents;

-- -----------------------------------------------------------------------------
-- 2F. PORTFOLIO MIX CHANGES — did risk-segment / DPD-bucket composition of
-- the WORKED population shift materially month to month?
-- Finding: mix stays within ~24-26% per segment every month (flat) -> ruled
-- out as a driver of the recovery-rate swings (confirmed further by the
-- direct-standardization check in 3. below).
-- -----------------------------------------------------------------------------
SELECT
    w.month,
    a.risk_segment,
    COUNT(DISTINCT w.account_id) AS n_accounts,
    ROUND(100.0 * COUNT(DISTINCT w.account_id)
        / SUM(COUNT(DISTINCT w.account_id)) OVER (PARTITION BY w.month), 2) AS pct_of_month
FROM golden.fct_worked_account_month w
JOIN golden.dim_account a USING (account_id)
GROUP BY w.month, a.risk_segment
ORDER BY w.month, a.risk_segment;

-- -----------------------------------------------------------------------------
-- 2G. DENOMINATOR MANIPULATION — are unsuccessful accounts disappearing
-- from the population used to calculate conversion? Compare the naive
-- (independent nunique ratio) recovery rate against the corrected
-- cohort-join rate. Finding: naive overstates by 2.5-2.9pp every month --
-- not evidence of deliberate manipulation (the gap is stable, not growing),
-- but a real definitional inflation baked into any dashboard using the
-- naive form.
-- -----------------------------------------------------------------------------
WITH naive AS (
    SELECT
        w.month,
        COUNT(DISTINCT w.account_id) AS worked_accounts,
        (SELECT COUNT(DISTINCT account_id) FROM golden.fct_payment p
          WHERE p.payment_status = 'SUCCESS' AND p.txn_month = w.month) AS recovered_accounts_independent
    FROM golden.fct_worked_account_month w
    GROUP BY w.month
)
SELECT
    n.month,
    ROUND(100.0 * n.recovered_accounts_independent / n.worked_accounts, 2) AS naive_recovery_rate_pct,
    c.recovery_rate_pct AS corrected_recovery_rate_pct,
    ROUND(100.0 * n.recovered_accounts_independent / n.worked_accounts - c.recovery_rate_pct, 2) AS gap_pp
FROM naive n
JOIN golden.metric_recovery_rate_by_month c USING (month)
ORDER BY n.month;

-- -----------------------------------------------------------------------------
-- 3. MIX-ADJUSTMENT (direct standardization) — recompute each month's
-- recovery rate using January's risk-segment mix as fixed weights, to
-- isolate genuine operational change from population composition change
-- (Simpson's-paradox guard).
-- -----------------------------------------------------------------------------
WITH jan_mix AS (
    SELECT a.risk_segment, COUNT(DISTINCT w.account_id) * 1.0
        / SUM(COUNT(DISTINCT w.account_id)) OVER () AS weight
    FROM golden.fct_worked_account_month w
    JOIN golden.dim_account a USING (account_id)
    WHERE w.month = '2026-01-01'
    GROUP BY a.risk_segment
),
seg_month_rate AS (
    SELECT w.month, a.risk_segment, AVG(r.recovered_flag) AS rate
    FROM golden.fct_worked_account_month w
    JOIN golden.dim_account a USING (account_id)
    JOIN golden.fct_account_month_recovery r ON r.account_id = w.account_id AND r.month = w.month
    GROUP BY w.month, a.risk_segment
)
SELECT
    s.month,
    ROUND(100.0 * SUM(s.rate * j.weight), 2) AS standardized_recovery_rate_pct
FROM seg_month_rate s
JOIN jan_mix j USING (risk_segment)
GROUP BY s.month
ORDER BY s.month;

-- -----------------------------------------------------------------------------
-- 4. COUNTERFACTUAL — Difference-in-Differences on the targeting-strategy
-- change. Treatment = accounts ever targeted under a v2/v3 campaign
-- (strategy_version), control = accounts never targeted under v2/v3.
-- Pre/post windows are relative to each treated account's first v2/v3
-- exposure month; control uses the same calendar pre/post windows
-- (Jan-Feb vs Jun-Jul) as a naive but transparent comparable.
-- LIMITATIONS (documented, not hidden): switch timing is not randomized
-- (confounded with which accounts campaigns happened to prioritize),
-- strategy_version dates are scattered rather than a single clean cutover,
-- and this proxy conflates "targeting strategy" with "campaign version
-- label" which may not be a 1:1 mapping to the real strategy change
-- leadership has in mind.
-- -----------------------------------------------------------------------------
WITH first_new AS (
    SELECT dt.account_id, MIN(dt.target_date) AS switch_date
    FROM clean.daily_targeting_clean dt
    JOIN clean.campaigns_clean cm USING (campaign_id)
    WHERE cm.strategy_version IN ('v2', 'v3')
    GROUP BY dt.account_id
),
treated AS (
    SELECT r.account_id, r.month, r.recovered_flag,
           DATE_DIFF('month', DATE_TRUNC('month', f.switch_date), r.month) AS rel_month
    FROM golden.fct_account_month_recovery r
    JOIN first_new f USING (account_id)
),
control AS (
    SELECT r.account_id, r.month, r.recovered_flag
    FROM golden.fct_account_month_recovery r
    WHERE r.account_id NOT IN (SELECT account_id FROM first_new)
)
SELECT
    'treated_pre' AS grp, AVG(recovered_flag) * 100 AS recovery_rate_pct FROM treated WHERE rel_month BETWEEN -2 AND -1
UNION ALL
SELECT 'treated_post', AVG(recovered_flag) * 100 FROM treated WHERE rel_month BETWEEN 0 AND 1
UNION ALL
SELECT 'control_pre', AVG(recovered_flag) * 100 FROM control WHERE month IN ('2026-01-01', '2026-02-01')
UNION ALL
SELECT 'control_post', AVG(recovered_flag) * 100 FROM control WHERE month IN ('2026-06-01', '2026-07-01');
-- DiD estimate = (treated_post - treated_pre) - (control_post - control_pre)
