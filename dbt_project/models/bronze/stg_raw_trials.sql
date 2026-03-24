-- ═══════════════════════════════════════════════════════════════
-- BRONZE MODEL: stg_raw_trials
-- Materialized as: VIEW (always fresh, zero storage overhead)
-- Purpose: Parse raw JSONB from raw.clinical_trials into typed columns
-- Rule: NO business logic here — structural parsing only
-- ═══════════════════════════════════════════════════════════════
{{ config(
    materialized = 'view',
    schema       = 'raw'
) }}

SELECT
    -- Surrogate key
    id AS raw_id,

    -- Primary identifier
    nct_id,

    -- Audit columns
    ingested_at,
    batch_id,
    condition_tag,
    is_processed,

    -- ── Identification ─────────────────────────────────────────────────────
    raw_json #>> '{protocolSection,identificationModule,briefTitle}'AS title,
    raw_json #>> '{protocolSection,identificationModule,officialTitle}'AS official_title,
    raw_json #>> '{protocolSection,identificationModule,organization,fullName}' AS organization,

    -- ── Status ─────────────────────────────────────────────────────────────
    raw_json #>> '{protocolSection,statusModule,overallStatus}'AS status,
    raw_json #>> '{protocolSection,statusModule,studyFirstSubmitDate}'AS first_submit_date_raw,
    raw_json #>> '{protocolSection,statusModule,lastUpdateSubmitDate}'AS last_update_date_raw,
    raw_json #>> '{protocolSection,statusModule,completionDateStruct,date}'AS completion_date_raw,
    raw_json #>> '{protocolSection,statusModule,startDateStruct,date}'AS start_date_raw,

    -- ── Description ────────────────────────────────────────────────────────
    raw_json #>> '{protocolSection,descriptionModule,briefSummary}' AS brief_summary,
    raw_json #>> '{protocolSection,descriptionModule,detailedDescription}'AS detailed_description,

    -- ── Design ─────────────────────────────────────────────────────────────
    raw_json #>> '{protocolSection,designModule,phases,0}'AS phase_raw,
    raw_json #>> '{protocolSection,designModule,studyType}'AS study_type,
    raw_json #>> '{protocolSection,designModule,designInfo,allocation}'AS allocation,
    raw_json #>> '{protocolSection,designModule,designInfo,interventionModel}' AS intervention_model,
    (raw_json #>> '{protocolSection,designModule,enrollmentInfo,count}')::INTEGER AS enrollment_count,
    raw_json #>> '{protocolSection,designModule,enrollmentInfo,type}'AS enrollment_type,

    -- ── Conditions ─────────────────────────────────────────────────────────
    (raw_json #> '{protocolSection,conditionsModule,conditions}')::TEXT AS conditions_json,
    (raw_json #> '{protocolSection,conditionsModule,keywords}')::TEXT AS keywords_json,

    -- ── Interventions ──────────────────────────────────────────────────────
    (raw_json #> '{protocolSection,armsInterventionsModule,interventions}')::TEXT AS interventions_json,

    -- ── Sponsor ────────────────────────────────────────────────────────────
    raw_json #>> '{protocolSection,sponsorCollaboratorsModule,leadSponsor,name}' AS sponsor,
    raw_json #>> '{protocolSection,sponsorCollaboratorsModule,leadSponsor,class}' AS sponsor_class,

    -- ── Eligibility ────────────────────────────────────────────────────────
    raw_json #>> '{protocolSection,eligibilityModule,eligibilityCriteria}' AS eligibility_criteria,
    raw_json #>> '{protocolSection,eligibilityModule,minimumAge}' AS min_age,
    raw_json #>> '{protocolSection,eligibilityModule,maximumAge}' AS max_age,
    raw_json #>> '{protocolSection,eligibilityModule,sex}' AS sex,
    (raw_json #>> '{protocolSection,eligibilityModule,stdAgesJson}')AS std_ages_json,

    -- ── Location ───────────────────────────────────────────────────────────
    (raw_json #> '{protocolSection,contactsLocationsModule,locations}')::TEXT AS locations_json,

    -- ── Outcomes ───────────────────────────────────────────────────────────
    (raw_json #> '{protocolSection,outcomesModule,primaryOutcomes}')::TEXT AS primary_outcomes_json

FROM {{ source('raw', 'clinical_trials') }}
WHERE
    nct_id IS NOT NULL
    AND raw_json IS NOT NULL
    AND LENGTH(nct_id) > 3
