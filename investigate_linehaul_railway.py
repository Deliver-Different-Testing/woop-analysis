#!/usr/bin/env python3
"""
Investigate Woop linehaul charging in the Railway PostgreSQL database.

Same investigation as investigate_linehaul.py but targeting the Railway
PostgreSQL mirror that the existing cost-decomposition analysis uses.

Usage: python3 investigate_linehaul_railway.py
"""
import psycopg2
import json
from collections import defaultdict
from datetime import datetime

RAILWAY_DSN = "postgresql://postgres:QUCLoTKRmLWvkDwnpfGQSerEwEavctOP@hopper.proxy.rlwy.net:20735/railway"

def run_query(cur, label, sql, max_rows=200):
    print(f'\n{"="*70}')
    print(f'  {label}')
    print(f'{"="*70}')
    cur.execute(sql)
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]
    print(f'  Columns: {cols}')
    print(f'  Rows returned: {len(rows)}')
    for i, row in enumerate(rows):
        if i >= max_rows:
            print(f'  ... ({len(rows) - max_rows} more rows)')
            break
        formatted = '  '
        for j, col in enumerate(cols):
            val = row[j]
            if isinstance(val, float):
                formatted += f'{col}={val:.2f}  '
            else:
                formatted += f'{col}={val}  '
        print(formatted)
    return rows, cols

def main():
    conn = psycopg2.connect(RAILWAY_DSN)
    cur = conn.cursor()

    # =========================================================================
    # QUERY 1: ALL distinct client codes containing 'WOOP'
    # =========================================================================
    run_query(cur, 'QUERY 1: ALL client codes containing WOOP', """
        SELECT ucjbclientcode, COUNT(*) as job_count,
               MIN(ucjbdate) as earliest_date,
               MAX(ucjbdate) as latest_date
        FROM tucjobarchive
        WHERE UPPER(ucjbclientcode) LIKE '%WOOP%'
        GROUP BY ucjbclientcode
        ORDER BY ucjbclientcode
    """)

    # =========================================================================
    # QUERY 2: ALL speed IDs by client code
    # =========================================================================
    run_query(cur, 'QUERY 2: Speed IDs by client code (ALL WOOP%)', """
        SELECT ucjbclientcode, ucjbspeed, COUNT(*) as cnt,
               MIN(ucjbdate) as earliest, MAX(ucjbdate) as latest
        FROM tucjobarchive
        WHERE UPPER(ucjbclientcode) LIKE '%WOOP%'
        GROUP BY ucjbclientcode, ucjbspeed
        ORDER BY ucjbclientcode, cnt DESC
    """)

    # =========================================================================
    # QUERY 3: Job number suffix patterns
    # =========================================================================
    run_query(cur, 'QUERY 3: Job number suffix patterns', """
        SELECT ucjbclientcode, RIGHT(ucjbnumber, 3) as suffix,
               COUNT(*) as cnt,
               MIN(ucjbdate) as earliest, MAX(ucjbdate) as latest
        FROM tucjobarchive
        WHERE UPPER(ucjbclientcode) LIKE '%WOOP%'
        GROUP BY ucjbclientcode, RIGHT(ucjbnumber, 3)
        HAVING COUNT(*) > 5
        ORDER BY ucjbclientcode, cnt DESC
    """)

    # =========================================================================
    # QUERY 4: Jobs with LH in job number
    # =========================================================================
    run_query(cur, 'QUERY 4: Jobs with LH in the job number', """
        SELECT ucjbclientcode, ucjbspeed, jobrelationshiptypeid,
               COUNT(*) as cnt,
               MIN(ucjbdate) as earliest, MAX(ucjbdate) as latest,
               MIN(ucjbamount) as min_amt, MAX(ucjbamount) as max_amt,
               AVG(ucjbamount) as avg_amt
        FROM tucjobarchive
        WHERE UPPER(ucjbclientcode) LIKE '%WOOP%'
          AND ucjbnumber LIKE '%LH%'
        GROUP BY ucjbclientcode, ucjbspeed, jobrelationshiptypeid
        ORDER BY ucjbclientcode, cnt DESC
    """)

    # =========================================================================
    # QUERY 5: Non-standard speed IDs
    # =========================================================================
    run_query(cur, 'QUERY 5: Non-standard speed IDs (NOT 95/94/4)', """
        SELECT ucjbclientcode, ucjbspeed, jobrelationshiptypeid,
               COUNT(*) as cnt,
               MIN(ucjbdate) as earliest, MAX(ucjbdate) as latest,
               AVG(ucjbamount) as avg_amt,
               SUM(ucjbamount) as total_amt
        FROM tucjobarchive
        WHERE UPPER(ucjbclientcode) LIKE '%WOOP%'
          AND ucjbspeed::text NOT IN ('95', '94', '4')
        GROUP BY ucjbclientcode, ucjbspeed, jobrelationshiptypeid
        ORDER BY cnt DESC
    """)

    # =========================================================================
    # QUERY 6: Potential linehaul jobs by year (2021-2024)
    # =========================================================================
    run_query(cur, 'QUERY 6: Non-standard speed jobs by year (2021-2024)', """
        SELECT EXTRACT(YEAR FROM ucjbdate::timestamp) as yr,
               ucjbclientcode, ucjbspeed,
               jobrelationshiptypeid as rel,
               COUNT(*) as cnt,
               AVG(ucjbamount) as avg_amt,
               SUM(ucjbamount) as total_amt,
               AVG(COALESCE(rawbaseamount, ucjbamount)) as avg_base,
               AVG(fuelsurchargeamount) as avg_fuel
        FROM tucjobarchive
        WHERE UPPER(ucjbclientcode) LIKE '%WOOP%'
          AND ucjbspeed::text NOT IN ('95', '94', '4')
          AND ucjbdate >= '2021-01-01' AND ucjbdate < '2025-01-01'
          AND (ucjbvoid = 'False' OR ucjbvoid = '0')
        GROUP BY EXTRACT(YEAR FROM ucjbdate::timestamp),
                 ucjbclientcode, ucjbspeed, jobrelationshiptypeid
        ORDER BY yr, ucjbclientcode, cnt DESC
    """)

    # =========================================================================
    # QUERY 7: All relationship types for Woop
    # =========================================================================
    run_query(cur, 'QUERY 7: All relationship types for Woop', """
        SELECT ucjbclientcode, jobrelationshiptypeid, COUNT(*) as cnt,
               MIN(ucjbdate) as earliest, MAX(ucjbdate) as latest
        FROM tucjobarchive
        WHERE UPPER(ucjbclientcode) LIKE '%WOOP%'
        GROUP BY ucjbclientcode, jobrelationshiptypeid
        ORDER BY ucjbclientcode, cnt DESC
    """)

    # =========================================================================
    # QUERY 8: Tables in the database
    # =========================================================================
    run_query(cur, 'QUERY 8: All tables in the database', """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND (table_name ILIKE '%linehaul%'
               OR table_name ILIKE '%invoice%'
               OR table_name ILIKE '%billing%'
               OR table_name ILIKE '%charge%'
               OR table_name ILIKE '%surcharge%')
        ORDER BY table_name
    """)

    # =========================================================================
    # QUERY 9: Check ALL tables for anything linehaul-related
    # =========================================================================
    run_query(cur, 'QUERY 9: All public tables', """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)

    # =========================================================================
    # QUERY 10: Sample non-standard speed jobs 2021-2024
    # =========================================================================
    run_query(cur, 'QUERY 10: Sample non-standard speed jobs 2021-2024', """
        SELECT ucjbnumber, ucjbdate, ucjbclientcode, ucjbspeed,
               jobrelationshiptypeid, ucjbamount, rawbaseamount,
               fuelsurchargeamount, runname, ucjbvoid
        FROM tucjobarchive
        WHERE UPPER(ucjbclientcode) LIKE '%WOOP%'
          AND ucjbspeed::text NOT IN ('95', '94', '4')
          AND ucjbdate >= '2021-01-01' AND ucjbdate < '2025-01-01'
        ORDER BY ucjbdate
        LIMIT 50
    """)

    # =========================================================================
    # QUERY 11: Jobs with linehaul-related RunName
    # =========================================================================
    run_query(cur, 'QUERY 11: Jobs with linehaul-related RunName', """
        SELECT ucjbclientcode, runname, ucjbspeed,
               COUNT(*) as cnt,
               MIN(ucjbdate) as earliest, MAX(ucjbdate) as latest,
               AVG(ucjbamount) as avg_amt
        FROM tucjobarchive
        WHERE UPPER(ucjbclientcode) LIKE '%WOOP%'
          AND (runname ILIKE '%LH%' OR runname ILIKE '%linehaul%')
        GROUP BY ucjbclientcode, runname, ucjbspeed
        ORDER BY cnt DESC
    """)

    # =========================================================================
    # QUERY 12: Monthly breakdown by speed 2021-2024
    # =========================================================================
    run_query(cur, 'QUERY 12: Monthly volumes by speed (2021-2024)', """
        SELECT TO_CHAR(ucjbdate::timestamp, 'YYYY-MM') as month,
               ucjbspeed, COUNT(*) as cnt,
               SUM(ucjbamount) as total_amt
        FROM tucjobarchive
        WHERE UPPER(ucjbclientcode) LIKE '%WOOP%'
          AND ucjbdate >= '2021-01-01' AND ucjbdate < '2025-01-01'
          AND (ucjbvoid = 'False' OR ucjbvoid = '0')
          AND ucjbspeed::text NOT IN ('95', '94', '4')
        GROUP BY TO_CHAR(ucjbdate::timestamp, 'YYYY-MM'), ucjbspeed
        ORDER BY month, ucjbspeed
    """, max_rows=500)

    # =========================================================================
    # QUERY 13: Check columns of tucjobarchive for linehaul-related fields
    # =========================================================================
    run_query(cur, 'QUERY 13: All columns in tucjobarchive', """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'tucjobarchive'
          AND table_schema = 'public'
        ORDER BY ordinal_position
    """)

    cur.close()
    conn.close()
    print('\n\nScript complete.')

if __name__ == '__main__':
    main()
