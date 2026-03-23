-- ═══════════════════════════════════════════════════════════════
-- GOLD MODEL: trials_enriched
-- Materialized as: TABLE (full refresh, analytics-optimised)
-- Purpose: Business-ready, enriched, embedding-ready records
-- This is what the LLM gets as context AND what Streamlit charts show
-- ═══════════════════════════════════════════════════════════════
{{ config(
    materialized = 'table',
    schema       = 'gold',
    indexes      = [
        {'columns': ['nct_id'], 'unique': True},
        {'columns': ['status']},
        {'columns': ['phase_num']},
        {'columns': ['therapeutic_area']},
    ]
) }}

WITH cleaned AS (
    SELECT * FROM {{ ref('int_trials_cleaned') }}
),

categories AS (
    SELECT * FROM {{ ref('condition_categories') }}
),

enriched AS (
    SELECT
        c.nct_id,
        c.title,
        c.official_title,
        c.status,
        c.phase_num,
        c.phase_raw,
        c.study_type,
        c.allocation,
        c.intervention_model,
        c.brief_summary,
        c.detailed_description,
        c.conditions,
        c.keywords,
        c.interventions,
        c.primary_outcomes,
        c.eligibility_criteria,
        c.sponsor,
        c.sponsor_class,
        c.organization,
        c.enrollment_count,
        c.enrollment_type,
        c.submit_date,
        c.start_date,
        c.completion_date,
        c.last_update_date,
        c.min_age,
        c.max_age,
        c.sex,
        c.locations,
        c.condition_tag,
        c.has_summary,
        c.updated_at,

        -- ── Therapeutic area classification (from seed lookup) ──────────
        cat.therapeutic_area,
        cat.disease_category,

        -- ── Computed: trial duration in months ──────────────────────────
        CASE
            WHEN c.completion_date IS NOT NULL AND c.start_date IS NOT NULL
            THEN EXTRACT(MONTH FROM AGE(c.completion_date, c.start_date))::INTEGER
            ELSE NULL
        END AS duration_months,

        -- ── Active flag for business filtering ──────────────────────────
        c.status IN ('RECRUITING',
                     'ACTIVE_NOT_RECRUITING',
                     'ENROLLING_BY_INVITATION') AS is_active,

        -- ── Has results ─────────────────────────────────────────────────
        c.status = 'COMPLETED' AS is_completed,

        -- ── Decade for trend analysis ────────────────────────────────────
        EXTRACT(YEAR FROM c.submit_date)::INTEGER AS submit_year,

        -- ── Embedding text ───────────────────────────────────────────────
        -- Concatenates key fields into one text block for LLM context.
        -- This is what gets chunked and embedded into pgvector.
        CONCAT_WS(E'\n',
            'Trial ID: '    || c.nct_id,
            'Title: '       || c.title,
            'Status: '      || c.status,
            'Phase: '       || COALESCE(c.phase_num::TEXT, 'N/A'),
            'Sponsor: '     || COALESCE(c.sponsor, 'Unknown'),
            'Condition: '   || COALESCE(c.condition_tag, 'Unknown'),
            'Therapeutic Area: ' || COALESCE(cat.therapeutic_area, 'Unknown'),
            'Start Date: '  || COALESCE(c.start_date::TEXT, 'Unknown'),
            'Completion: '  || COALESCE(c.completion_date::TEXT, 'Ongoing'),
            'Enrollment: '  || COALESCE(c.enrollment_count::TEXT, 'Unknown') || ' participants',
            'Summary: '     || COALESCE(c.brief_summary, 'No summary available')
        ) AS embedding_text

    FROM cleaned c
    LEFT JOIN categories cat
      ON c.condition_tag ILIKE '%' || cat.keyword || '%'
      OR c.conditions::TEXT ILIKE '%' || cat.keyword || '%'
    WHERE c.title IS NOT NULL
      AND c.nct_id IS NOT NULL
),

deduped AS (
    SELECT DISTINCT ON (nct_id)
        nct_id,
        title,
        official_title,
        status,
        phase_num,
        phase_raw,
        study_type,
        allocation,
        intervention_model,
        brief_summary,
        detailed_description,
        conditions,
        keywords,
        interventions,
        primary_outcomes,
        eligibility_criteria,
        sponsor,
        sponsor_class,
        organization,
        enrollment_count,
        enrollment_type,
        submit_date,
        start_date,
        completion_date,
        last_update_date,
        min_age,
        max_age,
        sex,
        locations,
        condition_tag,
        has_summary,
        updated_at,
        therapeutic_area,
        disease_category,
        duration_months,
        is_active,
        is_completed,
        submit_year,
        embedding_text
    FROM enriched
    ORDER BY
        nct_id,
        disease_category,
        updated_at DESC NULLS LAST
)

SELECT *
FROM deduped