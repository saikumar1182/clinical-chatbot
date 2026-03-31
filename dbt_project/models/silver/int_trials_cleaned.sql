-- ═══════════════════════════════════════════════════════════════
-- SILVER MODEL: int_trials_cleaned
-- Materialized as: INCREMENTAL (only processes new/changed rows)
-- Purpose: Type casting, deduplication, standardisation, quality rules
-- Rule: One clean row per NCT ID. Business logic starts here.
-- ═══════════════════════════════════════════════════════════════
{{ config(
    materialized        = 'incremental',
    unique_key          = 'nct_id',
    on_schema_change    = 'append_new_columns',
    incremental_strategy = 'merge',
    schema              = 'silver'
) }}

WITH staged AS (

    SELECT * FROM {{ ref('stg_raw_trials') }}

    -- Incremental filter: only process rows ingested since last run
    {% if is_incremental() %}
    WHERE ingested_at > (
        SELECT COALESCE(MAX(ingested_at), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}

),

cleaned AS (

    SELECT
        nct_id,

        -- ── Title cleaning ─────────────────────────────────────────────
        TRIM(REGEXP_REPLACE(title, '\s+', ' ', 'g')) AS title,
        TRIM(REGEXP_REPLACE(official_title, '\s+', ' ', 'g')) AS official_title,
        organization,

        -- ── Status normalisation ────────────────────────────────────────
        UPPER(TRIM(status)) AS status,

        -- ── Phase extraction (1/2/3/4 as integer) ───────────────────────
        CASE
            WHEN phase_raw ILIKE '%phase 1%' OR phase_raw ILIKE '%phase1%' THEN 1
            WHEN phase_raw ILIKE '%phase 2%' OR phase_raw ILIKE '%phase2%' THEN 2
            WHEN phase_raw ILIKE '%phase 3%' OR phase_raw ILIKE '%phase3%' THEN 3
            WHEN phase_raw ILIKE '%phase 4%' OR phase_raw ILIKE '%phase4%' THEN 4
            WHEN phase_raw ILIKE '%early phase%' THEN 1
            ELSE NULL
        END AS phase_num,

        phase_raw AS phase_raw,
        study_type,
        allocation,
        intervention_model,

        -- ── Enrollment ──────────────────────────────────────────────────
        CASE
            WHEN enrollment_count < 0 THEN NULL
            WHEN enrollment_count > 1000000 THEN NULL  -- Unrealistic value
            ELSE enrollment_count
        END AS enrollment_count,
        enrollment_type,

        -- ── Summary cleaning ────────────────────────────────────────────
        NULLIF(TRIM(brief_summary), '') AS brief_summary,
        NULLIF(TRIM(detailed_description), '') AS detailed_description,
        LENGTH(brief_summary) > 50 AS has_summary,

        -- ── Conditions ──────────────────────────────────────────────────
        conditions_json::JSONB AS conditions,
        keywords_json::JSONB AS keywords,
        interventions_json::JSONB AS interventions,
        primary_outcomes_json::JSONB AS primary_outcomes,
        eligibility_criteria,
        min_age, max_age, sex,

        -- ── Sponsor ─────────────────────────────────────────────────────
        TRIM(sponsor) AS sponsor,
        sponsor_class,

        -- ── Date parsing (safe cast with NULL on failure) ────────────────
        CASE
            WHEN first_submit_date_raw ~ '^\d{4}-\d{2}-\d{2}$'
            THEN first_submit_date_raw::DATE
            ELSE NULL
        END AS submit_date,

        CASE
            WHEN completion_date_raw ~ '^\d{4}-\d{2}-\d{2}$'
            THEN completion_date_raw::DATE
            ELSE NULL
        END AS completion_date,

        CASE
            WHEN start_date_raw ~ '^\d{4}-\d{2}-\d{2}$'
            THEN start_date_raw::DATE
            ELSE NULL
        END AS start_date,

        CASE
            WHEN last_update_date_raw ~ '^\d{4}-\d{2}-\d{2}$'
            THEN last_update_date_raw::DATE
            ELSE NULL
        END AS last_update_date,

        locations_json::JSONB AS locations,

        -- ── Audit ────────────────────────────────────────────────────────
        condition_tag,
        batch_id,
        ingested_at,
        NOW() AS updated_at

    FROM staged
    WHERE
        title IS NOT NULL
        AND LENGTH(TRIM(title)) > 5
        AND nct_id IS NOT NULL

)

SELECT * FROM cleaned
