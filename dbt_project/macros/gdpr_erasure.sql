-- macros/gdpr_erasure.sql
-- GDPR Right to Erasure macro.
-- Usage: {{ gdpr_erase_subject(subject_id='NCT04567890', id_column='nct_id') }}
{% macro gdpr_erase_subject(subject_id, id_column='nct_id') %}

    {% set tables_with_pii = [
        {'schema': 'raw',    'table': 'clinical_trials',  'columns': ['raw_json']},
        {'schema': 'silver', 'table': 'int_trials_cleaned', 'columns': ['eligibility_criteria', 'detailed_description']},
    ] %}

    {% for item in tables_with_pii %}
        {% for col in item.columns %}
            UPDATE {{ item.schema }}.{{ item.table }}
            SET {{ col }} = '[REDACTED - GDPR erasure {{ run_started_at }}]'
            WHERE {{ id_column }} = '{{ subject_id }}';
        {% endfor %}
    {% endfor %}

    -- Log the erasure
    INSERT INTO eval.ingestion_runs (batch_id, status, conditions)
    VALUES (
        'gdpr_erasure_{{ subject_id }}_{{ run_started_at | replace(" ", "_") }}',
        'gdpr_erased',
        ARRAY['{{ subject_id }}']
    )
    ON CONFLICT DO NOTHING;

{% endmacro %}
