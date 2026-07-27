alter table analysis_jobs
add column source_id text;

create index analysis_jobs_source_id_idx on analysis_jobs (source_id);
