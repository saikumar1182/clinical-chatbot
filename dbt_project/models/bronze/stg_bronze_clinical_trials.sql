{{ config(materialized='view') }}
SELECT
    id AS raw_id, nct_id, ingested_at, batch_id,
    raw_json #>> '{protocolSection,identificationModule,briefTitle}'      AS title,
    raw_json #>> '{protocolSection,statusModule,overallStatus}'            AS status,
    raw_json #>> '{protocolSection,statusModule,studyFirstSubmitDate}'    AS first_submit_date,
    raw_json #>> '{protocolSection,descriptionModule,briefSummary}'        AS brief_summary,
    raw_json #>> '{protocolSection,designModule,phases,0}'               AS phase,
    (raw_json #> '{protocolSection,conditionsModule,conditions}')::text   AS conditions_json,
    raw_json #>> '{protocolSection,sponsorCollaboratorsModule,leadSponsor,name}' AS sponsor,
    (raw_json #>> '{protocolSection,designModule,enrollmentInfo,count}')::INTEGER AS enrollment_count,
    raw_json #>> '{protocolSection,statusModule,completionDateStruct,date}'  AS completion_date
FROM bronze.clinical_trials
WHERE nct_id IS NOT NULL AND raw_json IS NOT NULL