#!/usr/bin/env python3
"""Woop Pricing Audit: dedup + DEL suffix filtering"""
import pymssql
import psycopg2
from collections import Counter, defaultdict
from datetime import datetime, date

RAILWAY_DSN = "postgresql://postgres:QUCLoTKRmLWvkDwnpfGQSerEwEavctOP@hopper.proxy.rlwy.net:20735/railway"
AWS_HOST = "urgent-couriers-sql-server-urgent-prod.c9wsc8ywswov.ap-southeast-2.rds.amazonaws.com"
AWS_PASSWORD = r'Y3sF0Z9*3Z~WA2yvp$0roJzLGt?f'

def to_date(d):
    if d is None: return None
    if isinstance(d, datetime): return d.date()
    if isinstance(d, date): return d
    if isinstance(d, str):
        try:
            return datetime.strptime(d.split(' ')[0], '%d/%m/%Y').date()
        except: pass
    return None

print("=" * 60)
print("WOOP PRICING AUDIT — Dedup + Suffix Analysis")
print("=" * 60)

# 1. Railway (lowercase cols, dates as strings)
print("\n[1] Railway PG...")
pg = psycopg2.connect(RAILWAY_DSN)
pgc = pg.cursor()
pgc.execute("""SELECT ucjbid, ucjbnumber, ucjbdate, ucjbamount, jobrelationshiptypeid
               FROM tucjobarchive WHERE ucjbclientcode IN ('WOOP','WOOPW')""")
railway_rows = pgc.fetchall()
# Normalize: convert id to int, amount to float, date to date obj
railway_norm = {}
for r in railway_rows:
    uid = int(r[0]) if r[0] else None
    if uid is None: continue
    railway_norm[uid] = (uid, str(r[1] or ''), to_date(r[2]), float(r[3] or 0), str(r[4] or ''))
pg.close()
print(f"   {len(railway_rows)} rows, {len(railway_norm)} unique IDs")
rd = [v[2] for v in railway_norm.values() if v[2]]
if rd: print(f"   Range: {min(rd)} → {max(rd)}")

# 2. AWS (mixed case cols, proper datetime)
print("\n[2] AWS RDS...")
ms = pymssql.connect(server=AWS_HOST, port=1433, user="admin", password=AWS_PASSWORD, database="Despatch-Urgent-Prod")
msc = ms.cursor()
msc.execute("""SELECT ucjbID, ucjbNumber, ucjbDate, ucjbAmount, JobRelationshipTypeID
               FROM tucjobarchive WHERE ucjbClientCode IN ('WOOP','WOOPW')""")
aws_rows = msc.fetchall()
aws_norm = {}
for r in aws_rows:
    uid = int(r[0]) if r[0] else None
    if uid is None: continue
    aws_norm[uid] = (uid, str(r[1] or ''), to_date(r[2]), float(r[3] or 0), str(r[4] or ''))
ms.close()
print(f"   {len(aws_rows)} rows, {len(aws_norm)} unique IDs")
ad = [v[2] for v in aws_norm.values() if v[2]]
if ad: print(f"   Range: {min(ad)} → {max(ad)}")

# 3. Overlap
r_ids = set(railway_norm.keys())
a_ids = set(aws_norm.keys())
overlap = r_ids & a_ids
print(f"\n[3] OVERLAP")
print(f"   Railway only:  {len(r_ids - a_ids)}")
print(f"   AWS only:      {len(a_ids - r_ids)}")
print(f"   OVERLAP:       {len(overlap)}")
print(f"   Total unique:  {len(r_ids | a_ids)}")
if len(overlap) > 0:
    print(f"   ⚠️  {len(overlap)} rows DOUBLE-COUNTED in original analysis!")
    od = [aws_norm[i][2] for i in overlap if aws_norm[i][2]]
    if od: print(f"   Overlap dates: {min(od)} → {max(od)}")

# 4. Merge (prefer AWS for overlaps)
merged = dict(railway_norm)
merged.update(aws_norm)
print(f"\n[4] Deduplicated total: {len(merged)}")

# 5. Suffix analysis post-April 2025
cutoff = date(2025, 4, 1)

def get_suffix(jobno):
    j = str(jobno).upper().strip()
    for s in ["DEL", "LHP", "LH"]:
        if j.endswith(s): return s
    return "(none)"

post_apr = {uid: r for uid, r in merged.items() if r[2] and r[2] >= cutoff}
print(f"\n[5] POST-APRIL 2025: {len(post_apr)} deduped jobs")

suffix_counts = Counter()
suffix_samples = defaultdict(list)
for uid, r in post_apr.items():
    s = get_suffix(r[1])
    suffix_counts[s] += 1
    if len(suffix_samples[s]) < 5:
        suffix_samples[s].append(r[1])

print(f"\n   Suffix breakdown:")
for s, c in suffix_counts.most_common():
    pct = c / len(post_apr) * 100
    print(f"     {s:8s}: {c:6d} ({pct:5.1f}%)  e.g. {', '.join(suffix_samples[s][:3])}")

# 6. Relationship codes post-April
print(f"\n[6] RELATIONSHIP CODES (post-April 2025)")
rc = Counter()
for uid, r in post_apr.items():
    rc[r[4]] += 1
for rel, c in rc.most_common():
    pct = c / len(post_apr) * 100
    print(f"   rel={rel}: {c} ({pct:.1f}%)")

# 7. Price comparison
def avg_amt(rows):
    vals = [r[3] for r in rows if r[3] > 0]
    return (sum(vals) / len(vals), len(vals)) if vals else (0, 0)

all_avg, all_n = avg_amt(list(post_apr.values()))
del_only = [r for r in post_apr.values() if get_suffix(r[1]) == "DEL"]
del_avg, del_n = avg_amt(del_only)
no_lh = [r for r in post_apr.values() if get_suffix(r[1]) not in ("LH", "LHP")]
nolh_avg, nolh_n = avg_amt(no_lh)

print(f"\n[7] PRICE IMPACT (post-April 2025)")
print(f"   All jobs:        ${all_avg:.2f} (n={all_n})")
print(f"   DEL-suffix only: ${del_avg:.2f} (n={del_n})")
print(f"   Excl LH/LHP:    ${nolh_avg:.2f} (n={nolh_n})")

# 8. Monthly detail
print(f"\n[8] MONTHLY: ALL vs DEL-ONLY (post-April 2025)")
m_all = defaultdict(list)
m_del = defaultdict(list)
for r in post_apr.values():
    key = f"{r[2].year}-{r[2].month:02d}"
    if r[3] > 0:
        m_all[key].append(r[3])
        if get_suffix(r[1]) == "DEL":
            m_del[key].append(r[3])

print(f"   {'Month':8s} | {'All Avg':>9s} {'(n)':>6s} | {'DEL Avg':>9s} {'(n)':>6s} | {'Diff':>7s}")
print(f"   {'-'*55}")
for mo in sorted(m_all.keys()):
    aa = sum(m_all[mo]) / len(m_all[mo])
    dl = m_del.get(mo, [])
    da = sum(dl) / len(dl) if dl else 0
    print(f"   {mo:8s} | ${aa:8.2f} {len(m_all[mo]):5d} | ${da:8.2f} {len(dl):5d} | ${(da-aa) if dl else 0:+7.2f}")

# 9. Full annual table — deduped, correct filtering
print(f"\n[9] CORRECTED ANNUAL TABLE")
print(f"   Pre-April 2025: all rel=1 jobs (old model)")
print(f"   Post-April 2025: DEL-suffix only (delivery leg)")

yearly = defaultdict(list)
yearly_all = defaultdict(list)  # for comparison
for uid, r in merged.items():
    d = r[2]
    if not d or r[3] <= 0: continue
    yearly_all[d.year].append(r[3])
    if d >= cutoff:
        if get_suffix(r[1]) != "DEL": continue
    yearly[d.year].append(r[3])

print(f"\n   {'Year':6s} | {'Corrected':>10s} {'Avg $':>8s} | {'Original':>10s} {'Avg $':>8s}")
print(f"   {'-'*50}")
for yr in sorted(yearly.keys()):
    cv = yearly[yr]
    ov = yearly_all[yr]
    print(f"   {yr:6d} | {len(cv):10d} ${sum(cv)/len(cv):8.2f} | {len(ov):10d} ${sum(ov)/len(ov):8.2f}")

print("\n" + "=" * 60)
print("DONE")
print("=" * 60)
