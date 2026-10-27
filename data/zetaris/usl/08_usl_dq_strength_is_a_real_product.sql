-- Data-quality rule (native Zetaris DQ, command reference 14.1): a medicine line that
-- names a medicine and a strength must name a strength that medicine is actually made in.
-- "amlodipine 2.5 mg" fails: amlodipine comes as 5 mg and 10 mg, so 2.5 mg means a halved
-- tablet or a charting error -- either way a dose a pharmacist must confirm.
-- Lines with no resolved medicine or no stated strength (patient free text, devices) pass:
-- this rule judges strengths, not resolution. A same-table boolean expression, the form
-- Zetaris has confirmed (no window functions, no row alias; companion 8.6).
REGISTER DQ strength_is_a_real_product TABLE lightning.metastore.medtrace.medtrace_usl.medication_statement AS
COALESCE(strength_listed, true)
