-- Parent namespace. On a clean instance the child below fails without it
-- ("parent namespace : metastore is not existing"; Zetaris SQL companion 8.4).
CREATE NAMESPACE IF NOT EXISTS lightning.metastore
