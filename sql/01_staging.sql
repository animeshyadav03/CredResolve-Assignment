-- =============================================================================
-- 01_staging.sql
-- Collections Analytics — Staging Layer
-- Target: any modern warehouse (written in Snowflake/BigQuery-portable ANSI
-- SQL; swap COPY INTO / LOAD DATA for your platform's bulk loader).
--
-- Staging = raw files loaded 1:1, no business logic, all columns typed as
-- close to source as safely possible, plus system audit columns. Nothing is
-- dropped or corrected here — staging preserves the raw truth so cleaning
-- decisions in 02_cleaning_dedup.sql are always re-derivable and auditable.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS staging;

CREATE OR REPLACE TABLE staging.stg_borrowers (
    borrower_id     STRING,
    name            STRING,
    phone           STRING,
    email           STRING,
    city            STRING,
    state           STRING,
    created_at      TIMESTAMP,
    updated_at      TIMESTAMP,
    _source_file    STRING,
    _loaded_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE TABLE staging.stg_accounts (
    account_id          STRING,
    borrower_id         STRING,
    loan_type           STRING,
    principal_amount    NUMERIC(18,2),
    outstanding_amount  NUMERIC(18,2),
    dpd                 INT,
    risk_segment        STRING,
    status              STRING,
    opened_at           TIMESTAMP,
    timezone            STRING,
    schema_version      STRING,
    _loaded_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE TABLE staging.stg_agents (
    agent_id        STRING,
    employee_code   STRING,
    agent_name      STRING,
    vendor_id       STRING,
    team            STRING,
    status          STRING,
    joined_at       TIMESTAMP,
    updated_at      TIMESTAMP,
    _loaded_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE TABLE staging.stg_agent_sessions (
    session_id  STRING,
    agent_id    STRING,
    login_at    TIMESTAMP,
    channel     STRING,
    device_id   STRING,
    timezone    STRING,
    logout_at   TIMESTAMP,
    _loaded_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE TABLE staging.stg_campaigns (
    campaign_id         STRING,
    campaign_name       STRING,
    channel             STRING,
    strategy_version    STRING,
    start_at            TIMESTAMP,
    target_definition   STRING,
    end_at              TIMESTAMP,
    _loaded_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE TABLE staging.stg_daily_targeting (
    target_id            STRING,
    account_id            STRING,
    campaign_id            STRING,
    target_date            DATE,
    priority               INT,
    recommended_channel    STRING,
    status                 STRING,
    _loaded_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE TABLE staging.stg_calls (
    call_id         STRING,
    account_id      STRING,
    borrower_id     STRING,
    event_at        TIMESTAMP,
    agent_id        STRING,
    campaign_id     STRING,
    direction       STRING,
    vendor_id       STRING,
    call_status     STRING,
    duration_sec    INT,
    timezone        STRING,
    _loaded_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE TABLE staging.stg_call_attempts (
    attempt_id      STRING,
    account_id      STRING,
    borrower_id     STRING,
    event_at        TIMESTAMP,
    call_id         STRING,
    agent_id        STRING,
    attempt_no      INT,
    vendor_id       STRING,
    attempt_status  STRING,
    _loaded_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE TABLE staging.stg_call_dispositions (
    disposition_id          STRING,
    account_id              STRING,
    borrower_id             STRING,
    event_at                TIMESTAMP,
    call_id                 STRING,
    agent_id                STRING,
    disposition_code        STRING,
    disposition_version     STRING,
    _loaded_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE TABLE staging.stg_whatsapp_events (
    whatsapp_event_id   STRING,
    account_id          STRING,
    borrower_id         STRING,
    event_at            TIMESTAMP,
    message_id          STRING,
    event_type          STRING,
    template_code       STRING,
    provider_id         STRING,
    _loaded_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE TABLE staging.stg_sms_events (
    sms_event_id    STRING,
    account_id      STRING,
    borrower_id     STRING,
    event_at        TIMESTAMP,
    message_id      STRING,
    event_type      STRING,
    template_code   STRING,
    provider_id     STRING,
    _loaded_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE TABLE staging.stg_field_visits (
    visit_id        STRING,
    account_id      STRING,
    borrower_id     STRING,
    event_at        TIMESTAMP,
    agent_id        STRING,
    visit_type      STRING,
    outcome         STRING,
    latitude        FLOAT,
    longitude       FLOAT,
    scheduled_at    TIMESTAMP,
    _loaded_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE TABLE staging.stg_promises_to_pay (
    ptp_id              STRING,
    account_id          STRING,
    borrower_id         STRING,
    event_at            TIMESTAMP,
    agent_id            STRING,
    promised_amount     NUMERIC(18,2),
    promised_date       DATE,
    status              STRING,
    source              STRING,
    _loaded_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE TABLE staging.stg_payments (
    payment_id          STRING,
    account_id          STRING,
    borrower_id         STRING,
    event_at            TIMESTAMP,
    payment_reference   STRING,
    amount              NUMERIC(18,2),
    payment_status      STRING,
    payment_method      STRING,
    provider_id         STRING,
    _loaded_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE TABLE staging.stg_vendor_telephony (
    vendor_id           STRING,
    vendor_name         STRING,
    vendor_account_id   STRING,
    timezone            STRING,
    status              STRING,
    schema_version      STRING,
    _loaded_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE TABLE staging.stg_complaints (
    complaint_id    STRING,
    account_id      STRING,
    borrower_id     STRING,
    event_at        TIMESTAMP,
    complaint_type  STRING,
    severity        STRING,
    status          STRING,
    source          STRING,
    resolution_at   TIMESTAMP,
    _loaded_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE TABLE staging.stg_account_status_history (
    history_id      STRING,
    account_id      STRING,
    borrower_id     STRING,
    event_at        TIMESTAMP,
    status          STRING,
    changed_by      STRING,
    source          STRING,
    recorded_at     TIMESTAMP,
    _loaded_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

-- Loading (Snowflake-style example — swap for your platform's loader):
-- COPY INTO staging.stg_payments (payment_id, account_id, borrower_id, event_at,
--     payment_reference, amount, payment_status, payment_method, provider_id, _source_file)
-- FROM @raw_stage/payments.csv
-- FILE_FORMAT = (TYPE = CSV SKIP_HEADER = 1);
