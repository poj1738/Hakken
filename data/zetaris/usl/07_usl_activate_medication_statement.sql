-- Every medicine line from the four silos (13,856), resolved to a medicine.
-- Each source codes medicines its own way, and this is where that is reconciled once:
--   EMR       AMT medicinal product (amt_mp)
--   GP        AMT medicinal product pack (amt_mpp)
--   pharmacy  PBS item code; private scripts carry none and resolve by brand
--   patient   free text only -- left unresolved here (resolved_by = 'none')
-- Each exploded view is referenced ONCE: referencing one twice fails with
-- MISSING_ATTRIBUTES (Zetaris SQL companion section 4), so the lexicon becomes a single
-- key map in one pass, with each generic's real strengths attached by a window function.
-- The longest matching APINCHS ATC prefix wins.
ACTIVATE USL TABLE lightning.metastore.medtrace.medtrace_usl.medication_statement AS
WITH code_map AS (
  SELECT DISTINCT k.lookup, k.key, generic, atc_primary, strengths
  FROM (
    SELECT generic, atc_primary, amt_mp, amt_mpp, pbs_code, brand,
           collect_set(lower(trim(strength))) OVER (PARTITION BY generic) AS strengths
    FROM medtrace.MED_LEXICON
  ) lx
  LATERAL VIEW explode(array(
    named_struct('lookup', 'amt_mp', 'key', amt_mp),
    named_struct('lookup', 'amt_mpp', 'key', amt_mpp),
    named_struct('lookup', 'pbs_code', 'key', pbs_code),
    named_struct('lookup', 'brand', 'key', lower(brand))
  )) t AS k
),
stmt AS (
  SELECT a.*,
    CASE WHEN a.source = 'emr' THEN 'amt_mp'
         WHEN a.source = 'gp' THEN 'amt_mpp'
         WHEN a.source = 'pharmacy' AND a.script_type = 'private' THEN 'brand'
         WHEN a.source = 'pharmacy' THEN 'pbs_code' END AS lookup,
    CASE WHEN a.source = 'pharmacy' AND a.script_type = 'private' THEN lower(a.med_text)
         ELSE a.med_code END AS key
  FROM medtrace.ALL_SOURCES a
),
resolved AS (
  SELECT s.*, m.generic, m.atc_primary AS atc,
         CASE WHEN m.generic IS NULL THEN 'none' ELSE s.lookup END AS resolved_by,
         m.strengths
  FROM stmt s LEFT JOIN code_map m ON s.lookup = m.lookup AND s.key = m.key
),
ranked AS (
  SELECT r.*, h.apinchs_class,
         ROW_NUMBER() OVER (PARTITION BY r.row_id ORDER BY length(h.atc_prefix) DESC) AS rn
  FROM resolved r LEFT JOIN medtrace.APINCHS h ON r.atc LIKE concat(h.atc_prefix, '%')
)
SELECT COALESCE(row_id, '') AS row_id, source, source_patient_id AS patient_id, record_kind, doc_date,
       med_text, code_system, med_code, generic, atc, apinchs_class AS high_risk_class, resolved_by,
       strength_text, dose_text, freq_text, status_text, qty, days_supply, pharmacy_id, script_type,
       CASE WHEN generic IS NULL OR strength_text IS NULL OR trim(strength_text) = '' THEN NULL
            ELSE array_contains(strengths, lower(trim(strength_text))) END AS strength_listed
FROM ranked
WHERE rn = 1
