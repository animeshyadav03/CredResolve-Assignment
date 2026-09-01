-- =============================================================================
-- 02_cleaning_dedup.sql
-- Collections Analytics — Cleaning & Deduplication
-- Mirrors the logic in /etl/build_golden_dataset.py exactly, so the same
-- decisions apply whether the pipeline runs in Python or in-warehouse SQL.
-- Every step is a view (not a destructive UPDATE/DELETE) so raw staging
-- data is always retained for audit.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS clean;

-- -----------------------------------------------------------------------------
-- ACCOUNTS: unique key, no true duplicates found. Sanity-filter only.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW clean.accounts_clean AS
SELECT *
FROM staging.stg_accounts
WHERE principal_amount > 0
  AND outstanding_amount >= 0
  AND dpd BETWEEN 0 AND 180;

-- -----------------------------------------------------------------------------
-- BORROWERS: borrower_id repeats up to 11x with randomized name/phone/
-- email/city/state on every row (only 10 distinct name values exist across
-- ~11,000 real borrowers — name is not a usable identity signal).
-- Decision: identity = borrower_id only. Keep the most-recently-updated
-- snapshot per borrower_id as a best-effort attribute set, flagged LOW
-- confidence. Never join on name/phone/email.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW clean.borrowers_clean AS
WITH ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY borrower_id ORDER BY updated_at DESC) AS rn
    FROM staging.stg_borrowers
)
SELECT
    borrower_id, name, phone, email, city, state, created_at, updated_at,
    'LOW_ATTRIBUTES_ONLY_ID_STABLE' AS identity_confidence
FROM ranked
WHERE rn = 1;

-- -----------------------------------------------------------------------------
-- AGENTS: far worse than borrowers — 1,000 real agent_id values but 30,000
-- rows (avg 30 conflicting snapshots per agent, up to 48), and only 10
-- distinct agent_name values total. This table cannot support any reliable
-- "who is this agent" claim on name/employee_code/vendor/team/joined_at.
-- Decision: agent_id is the only trustworthy key. We keep status as a
-- best-effort current snapshot but DROP name/employee_code/vendor/team/
-- joined_at from any downstream logic. Tenure and channel are reconstructed
-- from transactional evidence instead (see clean.agents_clean below).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW clean.agents_clean AS
WITH ranked AS (
    SELECT agent_id, status,
           ROW_NUMBER() OVER (PARTITION BY agent_id ORDER BY updated_at DESC) AS rn
    FROM staging.stg_agents
),
first_seen AS (
    -- Tenure proxy: first transactional evidence of this agent_id actually
    -- working an account, which is the only tenure signal we trust.
    SELECT agent_id, MIN(event_at) AS agent_first_seen_at
    FROM staging.stg_calls
    GROUP BY agent_id
)
SELECT r.agent_id, r.status, f.agent_first_seen_at,
       'LOW_SNAPSHOT_ONLY' AS identity_confidence
FROM ranked r
LEFT JOIN first_seen f USING (agent_id)
WHERE r.rn = 1;

-- -----------------------------------------------------------------------------
-- PAYMENTS: 500 rows are EXACT full-row duplicates of another payment_id
-- (ingestion retries) -> dropped. payment_reference collides across
-- UNRELATED accounts (generator noise, not real duplicate cash) -> NOT used
-- for dedup. REVERSED payments cannot be traced to a specific prior SUCCESS
-- row (no shared account_id+reference match) -> netted at portfolio-month
-- grain downstream, not transaction grain.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW clean.payments_clean AS
WITH dedup AS (
    SELECT DISTINCT * FROM staging.stg_payments   -- drop exact full-row dupes
),
-- guard against the rare (14-case) conflicting payment_id where fields
-- differ across the "duplicate" -- keep the latest event
ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY payment_id ORDER BY event_at DESC) AS rn
    FROM dedup
)
SELECT payment_id, account_id, borrower_id, event_at, payment_reference,
       amount, payment_status, payment_method, provider_id,
       DATE_TRUNC('month', event_at) AS txn_month
FROM ranked
WHERE rn = 1;

-- -----------------------------------------------------------------------------
-- CALLS: exact-duplicate removal. `timezone` column is retained but flagged
-- unreliable — hour-of-day distribution is statistically uniform within
-- each timezone label (no business-hours clustering), so it carries no
-- recoverable local-time signal. event_at is used as-is; no offset shift
-- is applied (applying one would relabel noise as false precision).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW clean.calls_clean AS
SELECT DISTINCT *, DATE_TRUNC('month', event_at) AS event_month
FROM staging.stg_calls;

CREATE OR REPLACE VIEW clean.call_attempts_clean AS
SELECT DISTINCT *, DATE_TRUNC('month', event_at) AS event_month
FROM staging.stg_call_attempts;

-- -----------------------------------------------------------------------------
-- CALL DISPOSITIONS: PROMISE_TO_PAY and PTP co-occur roughly evenly across
-- ALL THREE disposition_version values (~1300 each) rather than splitting
-- cleanly by version -> they are synonyms used interchangeably, not a
-- version-specific rename. Standardize to a single canonical code.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW clean.call_dispositions_clean AS
SELECT DISTINCT
    disposition_id, account_id, borrower_id, event_at, call_id, agent_id,
    disposition_code,
    CASE WHEN disposition_code = 'PROMISE_TO_PAY' THEN 'PTP' ELSE disposition_code END AS disposition_code_std,
    disposition_version,
    DATE_TRUNC('month', event_at) AS event_month
FROM staging.stg_call_dispositions;

-- -----------------------------------------------------------------------------
-- Remaining event tables: straightforward exact-duplicate removal.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW clean.whatsapp_events_clean AS
SELECT DISTINCT *, DATE_TRUNC('month', event_at) AS event_month FROM staging.stg_whatsapp_events;

CREATE OR REPLACE VIEW clean.sms_events_clean AS
SELECT DISTINCT *, DATE_TRUNC('month', event_at) AS event_month FROM staging.stg_sms_events;

CREATE OR REPLACE VIEW clean.field_visits_clean AS
SELECT DISTINCT *, DATE_TRUNC('month', event_at) AS event_month FROM staging.stg_field_visits;

CREATE OR REPLACE VIEW clean.promises_to_pay_clean AS
SELECT DISTINCT *, DATE_TRUNC('month', event_at) AS event_month FROM staging.stg_promises_to_pay;

CREATE OR REPLACE VIEW clean.complaints_clean AS
SELECT DISTINCT *, DATE_TRUNC('month', event_at) AS event_month FROM staging.stg_complaints;

CREATE OR REPLACE VIEW clean.account_status_history_clean AS
SELECT DISTINCT *, DATE_TRUNC('month', event_at) AS event_month FROM staging.stg_account_status_history;

CREATE OR REPLACE VIEW clean.agent_sessions_clean AS
SELECT DISTINCT *,
       DATEDIFF('second', login_at, logout_at) / 3600.0 AS duration_hr,
       DATE_TRUNC('month', login_at) AS session_month
FROM staging.stg_agent_sessions
WHERE logout_at > login_at
  AND DATEDIFF('second', login_at, logout_at) / 3600.0 < 16;   -- drop bad/negative/absurd sessions

CREATE OR REPLACE VIEW clean.daily_targeting_clean AS
SELECT DISTINCT *, DATE_TRUNC('month', target_date) AS target_month FROM staging.stg_daily_targeting;

CREATE OR REPLACE VIEW clean.campaigns_clean AS
SELECT DISTINCT * FROM staging.stg_campaigns;

CREATE OR REPLACE VIEW clean.vendor_telephony_clean AS
SELECT DISTINCT * FROM staging.stg_vendor_telephony;

-- -----------------------------------------------------------------------------
-- WORKED POPULATION: the denominator guardrail for every rate metric.
-- An account is "worked" in month M if it has >=1 call_attempt OR
-- daily_targeting row OR whatsapp/sms/field_visit event that month,
-- REGARDLESS of outcome — so unsuccessful accounts cannot silently vanish
-- from a conversion-rate denominator (Part 2G check).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW clean.worked_population AS
SELECT DISTINCT account_id, DATE_TRUNC('month', event_at) AS worked_month FROM staging.stg_call_attempts
UNION
SELECT DISTINCT account_id, DATE_TRUNC('month', target_date) FROM staging.stg_daily_targeting
UNION
SELECT DISTINCT account_id, DATE_TRUNC('month', event_at) FROM staging.stg_whatsapp_events
UNION
SELECT DISTINCT account_id, DATE_TRUNC('month', event_at) FROM staging.stg_sms_events
UNION
SELECT DISTINCT account_id, DATE_TRUNC('month', event_at) FROM staging.stg_field_visits;
