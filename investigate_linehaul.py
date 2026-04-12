#!/usr/bin/env python3
"""
Investigate Woop linehaul charging in the production SQL Server database.

This script runs against the production Despatch-Urgent-Prod database to find
linehaul data that the existing cost-decomposition analysis may be missing.

The current analysis only looks at client codes WOOP/WOOPH/WOOPW/WOOPC and
classifies linehaul as rel=20, speed IN (142, 126). This script investigates
whether linehaul was separately invoiced during 2021-2024 using different
client codes, speed IDs, or job number patterns.

Usage: python3 investigate_linehaul.py
"""
import pymssql
import json
from collections import defaultdict
from datetime import datetime

SERVER = 'urgent-couriers-sql-server-urgent-prod.c9wsc8ywswov.ap-southeast-2.rds.amazonaws.com'
PORT = 1433
USER = 'admin'
PASSWORD = 'Y3sF0Z9*3Z~WA2yvp$0roJzLGt?f'
DATABASE = 'Despatch-Urgent-Prod'

def connect():
    return pymssql.connect(server=SERVER, port=PORT, user=USER,
                           password=PASSWORD, database=DATABASE)

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
    conn = connect()
    cur = conn.cursor()
    results = {}

    # =========================================================================
    # QUERY 1: ALL distinct client codes containing 'WOOP'
    # =========================================================================
    rows, cols = run_query(cur, 'QUERY 1: ALL client codes containing WOOP', """
        SELECT ucjbClientCode, COUNT(*) as job_count,
               MIN(ucjbDate) as earliest_date,
               MAX(ucjbDate) as latest_date
        FROM tucJobArchive
        WHERE ucjbClientCode LIKE '%WOOP%'
        GROUP BY ucjbClientCode
        ORDER BY ucjbClientCode
    """)
    results['client_codes'] = [{'code': r[0], 'count': r[1],
                                 'earliest': str(r[2]), 'latest': str(r[3])} for r in rows]

    # =========================================================================
    # QUERY 2: ALL speed IDs by client code for WOOP clients
    # =========================================================================
    rows, cols = run_query(cur, 'QUERY 2: Speed IDs by client code (ALL WOOP%)', """
        SELECT ucjbClientCode, ucjbSpeed, COUNT(*) as cnt,
               MIN(ucjbDate) as earliest, MAX(ucjbDate) as latest
        FROM tucJobArchive
        WHERE ucjbClientCode LIKE '%WOOP%'
        GROUP BY ucjbClientCode, ucjbSpeed
        ORDER BY ucjbClientCode, cnt DESC
    """)
    results['speed_ids'] = [{'code': r[0], 'speed': r[1], 'count': r[2],
                              'earliest': str(r[3]), 'latest': str(r[4])} for r in rows]

    # =========================================================================
    # QUERY 3: Job number suffix patterns (last 3 chars)
    # =========================================================================
    rows, cols = run_query(cur, 'QUERY 3: Job number suffix patterns', """
        SELECT ucjbClientCode, RIGHT(ucjbNumber, 3) as suffix,
               COUNT(*) as cnt,
               MIN(ucjbDate) as earliest, MAX(ucjbDate) as latest
        FROM tucJobArchive
        WHERE ucjbClientCode LIKE '%WOOP%'
        GROUP BY ucjbClientCode, RIGHT(ucjbNumber, 3)
        HAVING COUNT(*) > 5
        ORDER BY ucjbClientCode, cnt DESC
    """)
    results['suffixes'] = [{'code': r[0], 'suffix': r[1], 'count': r[2],
                             'earliest': str(r[3]), 'latest': str(r[4])} for r in rows]

    # =========================================================================
    # QUERY 4: Look for 'LH' or 'linehaul' in job numbers specifically
    # =========================================================================
    rows, cols = run_query(cur, 'QUERY 4: Jobs with LH in the job number', """
        SELECT ucjbClientCode, ucjbSpeed, JobRelationshipTypeID,
               COUNT(*) as cnt,
               MIN(ucjbDate) as earliest, MAX(ucjbDate) as latest,
               MIN(ucjbAmount) as min_amt, MAX(ucjbAmount) as max_amt,
               AVG(ucjbAmount) as avg_amt
        FROM tucJobArchive
        WHERE ucjbClientCode LIKE '%WOOP%'
          AND ucjbNumber LIKE '%LH%'
        GROUP BY ucjbClientCode, ucjbSpeed, JobRelationshipTypeID
        ORDER BY ucjbClientCode, cnt DESC
    """)

    # =========================================================================
    # QUERY 5: Non-standard speed IDs for Woop (NOT 95, 94, 4)
    # =========================================================================
    rows, cols = run_query(cur, 'QUERY 5: Non-standard speed IDs (NOT 95/94/4)', """
        SELECT ucjbClientCode, ucjbSpeed, JobRelationshipTypeID,
               COUNT(*) as cnt,
               MIN(ucjbDate) as earliest, MAX(ucjbDate) as latest,
               AVG(ucjbAmount) as avg_amt,
               SUM(ucjbAmount) as total_amt
        FROM tucJobArchive
        WHERE ucjbClientCode LIKE '%WOOP%'
          AND ucjbSpeed NOT IN (95, 94, 4)
        GROUP BY ucjbClientCode, ucjbSpeed, JobRelationshipTypeID
        ORDER BY cnt DESC
    """)

    # =========================================================================
    # QUERY 6: Linehaul-specific investigation for 2021-2024
    #  - Look for speed IDs that might be linehaul (120, 126, 142, 110, 96, etc.)
    #  - Break down by year
    # =========================================================================
    rows, cols = run_query(cur, 'QUERY 6: Potential linehaul jobs by year (2021-2024)', """
        SELECT YEAR(ucjbDate) as yr, ucjbClientCode, ucjbSpeed,
               JobRelationshipTypeID as rel,
               COUNT(*) as cnt,
               AVG(ucjbAmount) as avg_amt,
               SUM(ucjbAmount) as total_amt,
               AVG(COALESCE(RawBaseAmount, ucjbAmount)) as avg_base,
               AVG(FuelSurchargeAmount) as avg_fuel
        FROM tucJobArchive
        WHERE ucjbClientCode LIKE '%WOOP%'
          AND ucjbSpeed NOT IN (95, 94, 4)
          AND ucjbDate >= '2021-01-01' AND ucjbDate < '2025-01-01'
          AND ucjbVoid = 0
        GROUP BY YEAR(ucjbDate), ucjbClientCode, ucjbSpeed, JobRelationshipTypeID
        ORDER BY yr, ucjbClientCode, cnt DESC
    """)

    # =========================================================================
    # QUERY 7: All JobRelationshipTypeIDs for Woop
    # =========================================================================
    rows, cols = run_query(cur, 'QUERY 7: All relationship types for Woop', """
        SELECT ucjbClientCode, JobRelationshipTypeID, COUNT(*) as cnt,
               MIN(ucjbDate) as earliest, MAX(ucjbDate) as latest
        FROM tucJobArchive
        WHERE ucjbClientCode LIKE '%WOOP%'
        GROUP BY ucjbClientCode, JobRelationshipTypeID
        ORDER BY ucjbClientCode, cnt DESC
    """)

    # =========================================================================
    # QUERY 8: Check for 'linehaul' related tables in the database
    # =========================================================================
    rows, cols = run_query(cur, 'QUERY 8: Tables containing "linehaul" or "invoice" or "billing"', """
        SELECT TABLE_NAME, TABLE_TYPE
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_NAME LIKE '%linehaul%'
           OR TABLE_NAME LIKE '%invoice%'
           OR TABLE_NAME LIKE '%billing%'
           OR TABLE_NAME LIKE '%charge%'
           OR TABLE_NAME LIKE '%surcharge%'
        ORDER BY TABLE_NAME
    """)

    # =========================================================================
    # QUERY 9: Check for any Woop-related client IDs in tucclient
    # =========================================================================
    rows, cols = run_query(cur, 'QUERY 9: Woop client records', """
        SELECT TOP 50 *
        FROM tucclient
        WHERE ucclCode LIKE '%WOOP%'
           OR ucclName LIKE '%WOOP%'
           OR ucclName LIKE '%Woop%'
        ORDER BY ucclCode
    """)

    # =========================================================================
    # QUERY 10: Sample linehaul-like jobs from 2021-2024
    # =========================================================================
    rows, cols = run_query(cur, 'QUERY 10: Sample non-standard speed jobs 2021-2024', """
        SELECT TOP 50
               ucjbNumber, ucjbDate, ucjbClientCode, ucjbSpeed,
               JobRelationshipTypeID, ucjbAmount, RawBaseAmount,
               FuelSurchargeAmount, RunName, ucjbVoid
        FROM tucJobArchive
        WHERE ucjbClientCode LIKE '%WOOP%'
          AND ucjbSpeed NOT IN (95, 94, 4)
          AND ucjbDate >= '2021-01-01' AND ucjbDate < '2025-01-01'
        ORDER BY ucjbDate
    """)

    # =========================================================================
    # QUERY 11: Check for linehaul using RunName patterns
    # =========================================================================
    rows, cols = run_query(cur, 'QUERY 11: Jobs with linehaul-related RunName', """
        SELECT ucjbClientCode, RunName, ucjbSpeed,
               COUNT(*) as cnt,
               MIN(ucjbDate) as earliest, MAX(ucjbDate) as latest,
               AVG(ucjbAmount) as avg_amt
        FROM tucJobArchive
        WHERE ucjbClientCode LIKE '%WOOP%'
          AND (RunName LIKE '%LH%' OR RunName LIKE '%linehaul%' OR RunName LIKE '%Linehaul%')
        GROUP BY ucjbClientCode, RunName, ucjbSpeed
        ORDER BY cnt DESC
    """)

    # =========================================================================
    # QUERY 12: Monthly breakdown of ALL Woop jobs by speed, 2021-2024
    # =========================================================================
    rows, cols = run_query(cur, 'QUERY 12: Monthly Woop volumes by speed (2021-2024)', """
        SELECT FORMAT(ucjbDate, 'yyyy-MM') as month,
               ucjbSpeed, COUNT(*) as cnt,
               SUM(ucjbAmount) as total_amt
        FROM tucJobArchive
        WHERE ucjbClientCode LIKE '%WOOP%'
          AND ucjbDate >= '2021-01-01' AND ucjbDate < '2025-01-01'
          AND ucjbVoid = 0
          AND ucjbSpeed NOT IN (95, 94, 4)
        GROUP BY FORMAT(ucjbDate, 'yyyy-MM'), ucjbSpeed
        ORDER BY month, ucjbSpeed
    """, max_rows=500)

    # =========================================================================
    # QUERY 13: Check tucclient for all Woop-related client IDs
    #           and cross-reference with jobs
    # =========================================================================
    rows, cols = run_query(cur, 'QUERY 13: Woop client IDs from tucclient', """
        SELECT c.ucclID, c.ucclCode, c.ucclName,
               COUNT(j.ucjbNumber) as job_count
        FROM tucclient c
        LEFT JOIN tucJobArchive j ON j.ucjbClientID = c.ucclID
        WHERE c.ucclCode LIKE '%WOOP%'
           OR c.ucclName LIKE '%Woop%'
           OR c.ucclName LIKE '%WOOP%'
        GROUP BY c.ucclID, c.ucclCode, c.ucclName
        ORDER BY c.ucclCode
    """)

    # =========================================================================
    # QUERY 14: Check if linehaul was billed under a different client code
    #           by looking at jobs with Woop-like client IDs
    # =========================================================================
    rows, cols = run_query(cur, 'QUERY 14: Jobs for Woop client IDs (by ID, not code)', """
        SELECT j.ucjbClientCode, j.ucjbClientID, j.ucjbSpeed,
               JobRelationshipTypeID as rel,
               COUNT(*) as cnt,
               MIN(j.ucjbDate) as earliest, MAX(j.ucjbDate) as latest,
               AVG(j.ucjbAmount) as avg_amt
        FROM tucJobArchive j
        WHERE j.ucjbClientID IN (
            SELECT ucclID FROM tucclient
            WHERE ucclCode LIKE '%WOOP%' OR ucclName LIKE '%Woop%'
        )
        GROUP BY j.ucjbClientCode, j.ucjbClientID, j.ucjbSpeed, JobRelationshipTypeID
        ORDER BY j.ucjbClientCode, cnt DESC
    """)

    # =========================================================================
    # QUERY 15: Speed ID reference - what do speed IDs mean?
    # =========================================================================
    rows, cols = run_query(cur, 'QUERY 15: Speed reference table', """
        SELECT TOP 50 *
        FROM tucSpeed
        WHERE ucspID IN (4, 94, 95, 96, 110, 120, 126, 142)
        ORDER BY ucspID
    """)

    cur.close()
    conn.close()

    # Save results
    with open('linehaul_investigation_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f'\n\nResults saved to linehaul_investigation_results.json')
    print('Script complete.')

if __name__ == '__main__':
    main()
