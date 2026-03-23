-- tests/int_trials_cleaned_has_summary_ratio_at_least_70.sql

with stats as (
    select
        count(*) filter (where has_summary) * 1.0 / nullif(count(*), 0) as ratio
    from {{ ref('int_trials_cleaned') }}
)
select *
from stats
where ratio < 0.70