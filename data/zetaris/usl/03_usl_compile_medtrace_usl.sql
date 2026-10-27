-- The MedTrace USL: three related tables over six registered sources.
--   high_risk_class       <- APINCHS (ACSQHC high-risk medicine classes)
--   medicine              <- the PBS medicines lexicon, one row per generic
--   medication_statement  <- EMR + GP + pharmacy + patient interview, every line resolved
--                            to a medicine, its ATC and its high-risk class
-- One statement: a multi-table COMPILE must be sent intact, with each CREATE TABLE on
-- its own line (Zetaris command reference 13.1). The semicolons below separate tables;
-- there is none at the end. Columns are scalar (ARRAY/MAP/STRUCT are not supported).
-- The PRIMARY KEYs and the FOREIGN KEY generate Zetaris data-quality rules of their own.
COMPILE USL medtrace_usl DEPLOY NAMESPACE lightning.metastore.medtrace DDL
CREATE TABLE high_risk_class (
  atc_prefix varchar(16) NOT NULL PRIMARY KEY,
  apinchs_class varchar(64),
  label varchar(200)
);
CREATE TABLE medicine (
  generic varchar(120) NOT NULL PRIMARY KEY,
  atc_primary varchar(16),
  product_count int,
  strengths varchar(1000)
);
CREATE TABLE medication_statement (
  row_id varchar(32) NOT NULL PRIMARY KEY,
  source varchar(16),
  patient_id varchar(32),
  record_kind varchar(32),
  doc_date varchar(32),
  med_text varchar(500),
  code_system varchar(16),
  med_code varchar(64),
  generic varchar(120) FOREIGN KEY REFERENCES medicine(generic),
  atc varchar(16),
  high_risk_class varchar(64),
  resolved_by varchar(16),
  strength_text varchar(64),
  dose_text varchar(64),
  freq_text varchar(200),
  status_text varchar(64),
  qty varchar(16),
  days_supply varchar(16),
  pharmacy_id varchar(32),
  script_type varchar(16),
  strength_listed boolean
)
