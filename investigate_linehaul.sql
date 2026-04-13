-- =============================================================================
-- Woop Linehaul Investigation Queries
-- Run against: postgresql://postgres:QUCLoTKRmLWvkDwnpfGQSerEwEavctOP@hopper.proxy.rlwy.net:20735/railway
--
-- Usage: psql "postgresql://postgres:QUCLoTKRmLWvkDwnpfGQSerEwEavctOP@hopper.proxy.rlwy.net:20735/railway" -f investigate_linehaul.sql
-- =============================================================================

-- Q1: ALL client codes containing WOOP (are there more than the 4 currently used?)
\echo '=== Q1: ALL client codes containing WOOP ==='
SELECT ucjbclientcode, COUNT(*) as job_count,
       MIN(ucjbdate) as earliest, MAX(ucjbdate) as latest
FROM tucjobarchive
WHERE UPPER(ucjbclientcode) LIKE '%WOOP%'
GROUP BY ucjbclientcode
ORDER BY ucjbclientcode;

-- Q2: ALL speed IDs by client code
\echo '=== Q2: Speed IDs by client code ==='
SELECT ucjbclientcode, ucjbspeed, COUNT(*) as cnt,
       MIN(ucjbdate) as earliest, MAX(ucjbdate) as latest
FROM tucjobarchive
WHERE UPPER(ucjbclientcode) LIKE '%WOOP%'
GROUP BY ucjbclientcode, ucjbspeed
ORDER BY ucjbclientcode, cnt DESC;

-- Q3: Job number suffix patterns (last 3 chars)
\echo '=== Q3: Job number suffix patterns ==='
SELECT ucjbclientcode, RIGHT(ucjbnumber, 3) as suffix,
       COUNT(*) as cnt, MIN(ucjbdate) as earliest, MAX(ucjbdate) as latest
FROM tucjobarchive
WHERE UPPER(ucjbclientcode) LIKE '%WOOP%'
GROUP BY ucjbclientcode, RIGHT(ucjbnumber, 3)
HAVING COUNT(*) > 5
ORDER BY ucjbclientcode, cnt DESC;

-- Q4: Jobs with LH in the job number
\echo '=== Q4: Jobs with LH in job number ==='
SELECT ucjbclientcode, ucjbspeed, jobrelationshiptypeid,
       COUNT(*) as cnt, MIN(ucjbdate) as earliest, MAX(ucjbdate) as latest,
       ROUND(AVG(ucjbamount::numeric), 2) as avg_amt,
       ROUND(SUM(ucjbamount::numeric), 2) as total_amt
FROM tucjobarchive
WHERE UPPER(ucjbclientcode) LIKE '%WOOP%'
  AND UPPER(ucjbnumber) LIKE '%LH%'
GROUP BY ucjbclientcode, ucjbspeed, jobrelationshiptypeid
ORDER BY ucjbclientcode, cnt DESC;

-- Q5: Non-standard speed IDs (NOT 95/94/4) - these may be linehaul
\echo '=== Q5: Non-standard speed IDs (NOT 95/94/4) ==='
SELECT ucjbclientcode, ucjbspeed, jobrelationshiptypeid as rel,
       COUNT(*) as cnt, MIN(ucjbdate) as earliest, MAX(ucjbdate) as latest,
       ROUND(AVG(ucjbamount::numeric), 2) as avg_amt,
       ROUND(SUM(ucjbamount::numeric), 2) as total_amt
FROM tucjobarchive
WHERE UPPER(ucjbclientcode) LIKE '%WOOP%'
  AND ucjbspeed::text NOT IN ('95', '94', '4')
GROUP BY ucjbclientcode, ucjbspeed, jobrelationshiptypeid
ORDER BY cnt DESC;

-- Q6: Non-standard speed jobs by year (2021-2024) - the missing linehaul period
\echo '=== Q6: Non-standard speed jobs by year (2021-2024) ==='
SELECT EXTRACT(YEAR FROM ucjbdate::timestamp)::int as yr,
       ucjbclientcode, ucjbspeed, jobrelationshiptypeid as rel,
       COUNT(*) as cnt,
       ROUND(AVG(ucjbamount::numeric), 2) as avg_amt,
       ROUND(SUM(ucjbamount::numeric), 2) as total_amt
FROM tucjobarchive
WHERE UPPER(ucjbclientcode) LIKE '%WOOP%'
  AND ucjbspeed::text NOT IN ('95', '94', '4')
  AND ucjbdate >= '2021-01-01' AND ucjbdate < '2025-01-01'
  AND (ucjbvoid = 'False' OR ucjbvoid = '0')
GROUP BY EXTRACT(YEAR FROM ucjbdate::timestamp)::int,
         ucjbclientcode, ucjbspeed, jobrelationshiptypeid
ORDER BY yr, cnt DESC;

-- Q7: All relationship types for Woop
\echo '=== Q7: All relationship types ==='
SELECT ucjbclientcode, jobrelationshiptypeid, COUNT(*) as cnt,
       MIN(ucjbdate) as earliest, MAX(ucjbdate) as latest
FROM tucjobarchive
WHERE UPPER(ucjbclientcode) LIKE '%WOOP%'
GROUP BY ucjbclientcode, jobrelationshiptypeid
ORDER BY ucjbclientcode, cnt DESC;

-- Q8: Billing/invoice/linehaul/surcharge tables
\echo '=== Q8: Billing/invoice/linehaul tables ==='
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND (table_name ILIKE '%linehaul%' OR table_name ILIKE '%invoice%'
       OR table_name ILIKE '%billing%' OR table_name ILIKE '%charge%'
       OR table_name ILIKE '%surcharge%')
ORDER BY table_name;

-- Q9: ALL public tables (to find any billing-related tables)
\echo '=== Q9: All public tables ==='
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

-- Q10: Sample non-standard speed jobs 2021-2024 (first 30)
\echo '=== Q10: Sample non-standard speed jobs 2021-2024 ==='
SELECT ucjbnumber, ucjbdate, ucjbclientcode, ucjbspeed,
       jobrelationshiptypeid as rel, ucjbamount, rawbaseamount,
       fuelsurchargeamount, runname, ucjbvoid
FROM tucjobarchive
WHERE UPPER(ucjbclientcode) LIKE '%WOOP%'
  AND ucjbspeed::text NOT IN ('95', '94', '4')
  AND ucjbdate >= '2021-01-01' AND ucjbdate < '2025-01-01'
ORDER BY ucjbdate
LIMIT 30;

-- Q11: Jobs with LH-related RunName
\echo '=== Q11: Jobs with linehaul-related RunName ==='
SELECT ucjbclientcode, runname, ucjbspeed,
       COUNT(*) as cnt, MIN(ucjbdate) as earliest, MAX(ucjbdate) as latest,
       ROUND(AVG(ucjbamount::numeric), 2) as avg_amt
FROM tucjobarchive
WHERE UPPER(ucjbclientcode) LIKE '%WOOP%'
  AND (runname ILIKE '%LH%' OR runname ILIKE '%linehaul%')
GROUP BY ucjbclientcode, runname, ucjbspeed
ORDER BY cnt DESC;

-- Q12: Monthly non-standard speed volumes 2021-2024
\echo '=== Q12: Monthly non-standard speed volumes (2021-2024) ==='
SELECT TO_CHAR(ucjbdate::timestamp, 'YYYY-MM') as month,
       ucjbspeed, COUNT(*) as cnt,
       ROUND(SUM(ucjbamount::numeric), 2) as total_amt
FROM tucjobarchive
WHERE UPPER(ucjbclientcode) LIKE '%WOOP%'
  AND ucjbdate >= '2021-01-01' AND ucjbdate < '2025-01-01'
  AND (ucjbvoid = 'False' OR ucjbvoid = '0')
  AND ucjbspeed::text NOT IN ('95', '94', '4')
GROUP BY TO_CHAR(ucjbdate::timestamp, 'YYYY-MM'), ucjbspeed
ORDER BY month, ucjbspeed;

-- Q13: All columns in tucjobarchive
\echo '=== Q13: All columns in tucjobarchive ==='
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'tucjobarchive' AND table_schema = 'public'
ORDER BY ordinal_position;

-- Q14: ALL Woop jobs by year (all speeds) - to see total picture
\echo '=== Q14: All Woop jobs by year (all speeds) ==='
SELECT EXTRACT(YEAR FROM ucjbdate::timestamp)::int as yr,
       ucjbspeed, COUNT(*) as cnt,
       ROUND(SUM(ucjbamount::numeric), 2) as total_amt,
       ROUND(AVG(ucjbamount::numeric), 2) as avg_amt
FROM tucjobarchive
WHERE UPPER(ucjbclientcode) LIKE '%WOOP%'
  AND (ucjbvoid = 'False' OR ucjbvoid = '0')
  AND ucjbdate >= '2017-01-01'
GROUP BY EXTRACT(YEAR FROM ucjbdate::timestamp)::int, ucjbspeed
ORDER BY yr, cnt DESC;

\echo '=== ALL QUERIES COMPLETE ==='
