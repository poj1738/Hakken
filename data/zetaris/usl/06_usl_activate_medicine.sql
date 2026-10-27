-- The PBS lexicon, one row per generic (98), with every real product strength listed.
-- pbs_code cannot be the key: 224 lexicon rows carry 184 distinct codes.
ACTIVATE USL TABLE lightning.metastore.medtrace.medtrace_usl.medicine AS
SELECT COALESCE(generic, '') AS generic,
       MAX(atc_primary) AS atc_primary,
       CAST(COUNT(*) AS INT) AS product_count,
       concat_ws(', ', sort_array(collect_set(strength))) AS strengths
FROM medtrace.MED_LEXICON
GROUP BY generic
