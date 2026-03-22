{{ config(materialized='incremental', unique_key='nct_id', on_schema_change='append_new_columns') }}

WITH staged AS (
    SELECT * FROM {{ ref('stg_bronze_clinical_trials') }}
    {% if is_incremental() %}
        WHERE ingested_at > (SELECT MAX(ingested_at) FROM {{ this }})
    {% endif %}
)
SELECT
    nct_id, TRIM(title) AS title, UPPER(TRIM(status)) AS status,
    CASE WHEN phase LIKE '%1%' THEN 1 WHEN phase LIKE '%2%' THEN 2
         WHEN phase LIKE '%3%' THEN 3 WHEN phase LIKE '%4%' THEN 4 ELSE NULL END AS phase_num,
    brief_summary, conditions_json::jsonb AS conditions, sponsor,
    enrollment_count, first_submit_date::date AS submit_date,
    completion_date::date AS completion_date,
    LENGTH(brief_summary) > 100 AS has_summary, ingested_at, NOW() AS updated_at
FROM staged WHERE title IS NOT NULL AND LENGTH(title) > 5