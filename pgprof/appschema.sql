
-- This must already be done by admin ---
/*
  psql postgres postgres
  CREATE USER benchuser WITH LOGIN CREATEDB ENCRYPTED PASSWORD 'b3ncH@U53R';
  CREATE DATABASE benchdb WITH OWNER = benchuser TEMPLATE = template1 ENCODING 'UTF-8' CONNECTION LIMIT = 20;
  \c benchdb
  CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
*/

CREATE SCHEMA IF NOT EXISTS pgfailover AUTHORIZATION benchuser;
CREATE TABLE IF NOT EXISTS pgfailover.benchtab ( ts TIMESTAMP NOT NULL, id UUID PRIMARY KEY NOT NULL, status TEXT );
CREATE OR REPLACE VIEW pgfailover.benchview AS
SELECT benchtab.status as status, benchtab.ts as timestamp FROM pgfailover.benchtab WHERE COALESCE(benchtab.status,'') <> '';

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA pgfailover TO benchuser;

CREATE OR REPLACE FUNCTION random_text_md5(length INTEGER)
RETURNS TEXT
LANGUAGE PLPGSQL
AS $$ 
DECLARE 
  -- how many md5's we need to have at least length chars
  loop_count INTEGER := CEIL(length / 32.); 
  output TEXT := ''; -- the result text 
  i INT4; -- loop counter 
BEGIN
  FOR i IN 1..loop_count LOOP
    output := output || md5(random()::TEXT);
  END LOOP; 
  -- get the substring for the exact number of characters
  -- and upper them up 
  RETURN upper(substring(output, length)); 
END; $$;

CREATE OR REPLACE FUNCTION bench_trigger() RETURNS TRIGGER
LANGUAGE plpgsql AS 
$$
BEGIN
  NEW.id := uuid_generate_v5(uuid_ns_url(), random_text_md5(10));
RETURN NEW;
END;
$$;


DROP TRIGGER IF EXISTS benchtab_bench_trigger ON pgfailover.benchtab;
CREATE TRIGGER benchtab_bench_trigger
BEFORE INSERT ON pgfailover.benchtab
FOR EACH ROW EXECUTE PROCEDURE bench_trigger();

COMMIT;
