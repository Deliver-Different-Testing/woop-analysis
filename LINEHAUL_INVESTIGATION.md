# Woop Linehaul Investigation

## Status: Investigation Scripts Ready — DB Not Accessible From Cloud Sandbox

The Railway PostgreSQL (`hopper.proxy.rlwy.net`) and Production SQL Server (RDS) are
both unreachable from the Claude Code cloud sandbox environment (egress proxy blocks
non-HTTP hosts). Two investigation scripts have been prepared that need to be run
locally or from an environment with database access.

## What We Know From Code Analysis

### Current Cost-Decomposition Gaps

The existing `extract_cost_decomposition.py` has these potential blind spots:

1. **Only 4 client codes queried**: `WOOP`, `WOOPH`, `WOOPW`, `WOOPC`
   - But `query_2025.py` uses **5 client IDs**: `16867, 17534, 17535, 18005, 34155`
   - **The 5th client ID (34155) may correspond to a linehaul-specific client code
     that is NOT in the four codes used by the extraction script**

2. **Linehaul classified too narrowly**: Only `rel=20, speed IN (142, 126)`
   - This catches the post-March 2025 per-box model linehaul (LHP/LH1 jobs)
   - But pre-2025 linehaul may have used different speed IDs or relationship types
   - Speed IDs 120, 110, 96 are already treated as "delivery" but could be linehaul

3. **Linehaul timeline shows suspicious gap**:
   - 2017-2022: 0 linehaul jobs
   - 2023: 8 jobs
   - 2024: 219 jobs
   - 2025: 62,093 jobs
   - If linehaul was invoiced separately during 2021-2024, those charges are missing

4. **The "Other" speed handling**: The existing script classifies `rel=1, speed IN
   (120, 110, 96)` as deliveries — but these speed IDs might actually be linehaul
   charges on the old delivery model

### Key Questions the Investigation Scripts Will Answer

1. Are there additional `%WOOP%` client codes beyond the four used?
2. What does client ID 34155 map to? Is it a linehaul-specific code?
3. What speed IDs exist for Woop? Do any correspond to linehaul?
4. What job number suffixes exist beyond DEL and LH? (e.g., LHP, LH1, etc.)
5. Are there billing/invoice/surcharge tables that capture linehaul separately?
6. What does the speed reference table say speed IDs 120, 110, 96, 126, 142 mean?
7. Were there linehaul-like RunNames during 2021-2024?

## Scripts to Run

### Option A: Production SQL Server (preferred — has client ID cross-reference)
```bash
python3 investigate_linehaul.py
```
- Connects to: `urgent-couriers-sql-server-urgent-prod...rds.amazonaws.com`
- Runs 15 queries covering all investigation points
- Cross-references client IDs with client codes via `tucclient`

### Option B: Railway PostgreSQL (same data, different format)
```bash
python3 investigate_linehaul_railway.py
```
- Connects to: `hopper.proxy.rlwy.net:20735`
- Runs 13 equivalent queries against the Railway mirror

### Most Critical Queries

If running manually, these are the highest-priority queries:

```sql
-- Q1: Find ALL client codes containing WOOP (are there more than 4?)
SELECT ucjbClientCode, COUNT(*) as cnt
FROM tucJobArchive
WHERE ucjbClientCode LIKE '%WOOP%'
GROUP BY ucjbClientCode ORDER BY ucjbClientCode;

-- Q2: What speeds exist for Woop clients?
SELECT ucjbClientCode, ucjbSpeed, COUNT(*) as cnt
FROM tucJobArchive
WHERE ucjbClientCode LIKE '%WOOP%'
GROUP BY ucjbClientCode, ucjbSpeed ORDER BY cnt DESC;

-- Q3: What does client ID 34155 map to?
SELECT ucclID, ucclCode, ucclName FROM tucclient
WHERE ucclID IN (16867, 17534, 17535, 18005, 34155);

-- Q4: Non-standard speed jobs by year in 2021-2024
SELECT YEAR(ucjbDate) as yr, ucjbSpeed, COUNT(*), SUM(ucjbAmount)
FROM tucJobArchive
WHERE ucjbClientCode LIKE '%WOOP%'
  AND ucjbSpeed NOT IN (95, 94, 4)
  AND ucjbDate >= '2021-01-01' AND ucjbDate < '2025-01-01'
GROUP BY YEAR(ucjbDate), ucjbSpeed ORDER BY yr;

-- Q5: Speed reference table
SELECT ucspID, ucspName FROM tucSpeed
WHERE ucspID IN (4, 94, 95, 96, 110, 120, 126, 142);
```

## Next Steps

1. Run the investigation script from a machine with DB access
2. Review results, particularly:
   - Any new client codes found
   - Client ID 34155 mapping
   - Non-standard speed ID volumes during 2021-2024
3. Report findings back
4. Update `extract_cost_decomposition.py` to capture missing linehaul data
5. Regenerate `cost-decomposition.html`
