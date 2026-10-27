-- APINCHS: the ACSQHC high-risk medicine classes, keyed by ATC prefix (42 rows).
ACTIVATE USL TABLE lightning.metastore.medtrace.medtrace_usl.high_risk_class AS
SELECT COALESCE(atc_prefix, '') AS atc_prefix, apinchs_class, label
FROM medtrace.APINCHS
