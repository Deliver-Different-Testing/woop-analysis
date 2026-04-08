#!/usr/bin/env python3
"""
Extract Woop MFV run economics data.

Post-March 2025 (new model): DEL suffix, rel=20, speed=95
Pre-March 2025 (old model): rel=1, speed=95

For each run (runname + date):
  - DEL-only revenue (ucjbAmount) = MFV base
  - Actual MFV paid (sum fuelsurchargeamount)
  - TSP-estimated driven KM with 1.27x road multiplier
  - Extra fuel cost vs $1.84/L baseline
  - Total run revenue (all job types in the run, for proportion comparison)

Also queries total run revenue (including non-DEL components) for the
post-March period to show DEL vs total proportion.
"""
import psycopg2
import json
import math
from collections import defaultdict
from datetime import datetime

RAILWAY_DSN = "postgresql://postgres:QUCLoTKRmLWvkDwnpfGQSerEwEavctOP@hopper.proxy.rlwy.net:20735/railway"

# City classification by run name prefix
CITY_BY_PREFIX = {}
for p in ['AW','AH','A1','A2','A3','A4','A5','A6','A7','A8','A9','AC','AM','AU','AX','NW','Aw']:
    CITY_BY_PREFIX[p] = 'Auckland'
for p in ['WW','W0','W1','W2','W3','W4','W5','W6','W7','W8','W9','WA','WC','WE','WM','WX','WT','WO','WH','WP','WF','WL']:
    CITY_BY_PREFIX[p] = 'Wellington'
for p in ['CW','C0','C1','C2','C3','C4','C5','C6','C7','C8','C9','CC','CR','CX','CM','CA','CD','CI']:
    CITY_BY_PREFIX[p] = 'Christchurch'
for p in ['HW','H1','H2','H3','H4','H5','H6','HX','HR']:
    CITY_BY_PREFIX[p] = 'Hamilton'
for p in ['TW','T0','T1','T2','T3','T4','T5','TX','TG']:
    CITY_BY_PREFIX[p] = 'Tauranga'

ROAD_MULTIPLIER = 1.27
BASE_FUEL_PRICE = 1.84   # $/L baseline
PUMP_PRICE = 3.70        # $/L current
CONSUMPTION = 13.0       # L/100km

# MFV matrix from run-economics.html
MFV_MATRIX = {
    1.84:0,1.85:0,1.86:0,1.87:0,1.88:0,1.89:0,1.90:0,1.91:0,
    1.92:0.001,1.93:0.002,1.94:0.003,1.95:0.004,1.96:0.004,1.97:0.005,1.98:0.006,1.99:0.007,
    2.00:0.008,2.01:0.009,2.02:0.010,2.03:0.011,2.04:0.012,2.05:0.013,2.06:0.013,2.07:0.014,
    2.08:0.015,2.09:0.016,2.10:0.017,2.11:0.018,2.12:0.019,2.13:0.020,2.14:0.021,2.15:0.021,
    2.16:0.022,2.17:0.023,2.18:0.024,2.19:0.025,2.20:0.026,2.21:0.027,2.22:0.028,2.23:0.028,
    2.24:0.029,2.25:0.030,2.26:0.031,2.27:0.032,2.28:0.032,2.29:0.034,2.30:0.035,2.31:0.036,
    2.32:0.037,2.33:0.038,2.34:0.039,2.35:0.040,2.36:0.041,2.37:0.042,2.38:0.043,2.39:0.044,
    2.40:0.045,2.41:0.046,2.42:0.047,2.43:0.048,2.44:0.049,2.45:0.050,2.46:0.051,2.47:0.052,
    2.48:0.052,2.49:0.054,2.50:0.055,2.51:0.056,2.52:0.057,2.53:0.057,2.54:0.059,2.55:0.060,
    2.56:0.061,2.57:0.062,2.58:0.063,2.59:0.064,2.60:0.065,2.61:0.066,2.62:0.067,2.63:0.068,
    2.64:0.069,2.65:0.070,2.66:0.071,2.67:0.072,2.68:0.073,2.69:0.074,2.70:0.075,2.71:0.075,
    2.72:0.077,2.73:0.078,2.74:0.079,2.75:0.080,2.76:0.081,2.77:0.082,2.78:0.083,2.79:0.084,
    2.80:0.085,2.81:0.086,2.82:0.087,2.83:0.088,2.84:0.089,2.85:0.090,2.86:0.091,2.87:0.092,
    2.88:0.093,2.89:0.094,2.90:0.095,2.91:0.096,2.92:0.097,2.93:0.098,2.94:0.099,2.95:0.100,
    2.96:0.101,2.97:0.102,2.98:0.103,2.99:0.104,3.00:0.105,3.01:0.106,3.02:0.107,3.03:0.108,
    3.04:0.109,3.05:0.110,3.06:0.111,3.07:0.112,3.08:0.113,3.09:0.114,3.10:0.115,3.11:0.116,
    3.12:0.117,3.13:0.118,3.14:0.119,3.15:0.120,3.16:0.121,3.17:0.122,3.18:0.123,3.19:0.124,
    3.20:0.125,3.21:0.126,3.22:0.127,3.23:0.128,3.24:0.129,3.25:0.130,3.26:0.131,3.27:0.132,
    3.28:0.133,3.29:0.134,3.30:0.135,3.31:0.136,3.32:0.137,3.33:0.138,3.34:0.139,3.35:0.140,
    3.36:0.141,3.37:0.142,3.38:0.143,3.39:0.144,3.40:0.145,3.41:0.146,3.42:0.147,3.43:0.148,
    3.44:0.149,3.45:0.150,3.46:0.151,3.47:0.152,3.48:0.153,3.49:0.154,3.50:0.155,
    3.51:0.156,3.52:0.157,3.53:0.158,3.54:0.159,3.55:0.160,3.56:0.161,3.57:0.162,3.58:0.163,
    3.59:0.164,3.60:0.165,3.61:0.166,3.62:0.167,3.63:0.168,3.64:0.169,3.65:0.170,
    3.66:0.171,3.67:0.172,3.68:0.173,3.69:0.174,3.70:0.175,3.71:0.176,3.72:0.177,3.73:0.178,
    3.74:0.179,3.75:0.180,3.76:0.181,3.77:0.182,3.78:0.183,3.79:0.184,3.80:0.185,
    3.81:0.186,3.82:0.187,3.83:0.188,3.84:0.189,3.85:0.190,3.86:0.191,3.87:0.192,3.88:0.193,
    3.89:0.194,3.90:0.195,3.91:0.196,3.92:0.197,3.93:0.198,3.94:0.199,3.95:0.200,
    3.96:0.201,3.97:0.202,3.98:0.203,3.99:0.204,4.00:0.205
}

def calc_mfv_rate(pump_price):
    key = round(pump_price * 100) / 100
    if key in MFV_MATRIX:
        return MFV_MATRIX[key]
    keys = sorted(MFV_MATRIX.keys())
    for i in range(len(keys) - 1, -1, -1):
        if keys[i] <= key:
            return MFV_MATRIX[keys[i]]
    return 0

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def nearest_neighbour_tsp(depot, points):
    if not points:
        return 0.0
    unvisited = list(range(len(points)))
    current = depot
    total_dist = 0.0
    while unvisited:
        best_idx = None
        best_dist = float('inf')
        for idx in unvisited:
            d = haversine_km(current[0], current[1], points[idx][0], points[idx][1])
            if d < best_dist:
                best_dist = d
                best_idx = idx
        total_dist += best_dist
        current = points[best_idx]
        unvisited.remove(best_idx)
    total_dist += haversine_km(current[0], current[1], depot[0], depot[1])
    return total_dist

def classify_city(runname, depot_lat):
    prefix2 = runname[:2] if len(runname) >= 2 else runname
    if prefix2 in CITY_BY_PREFIX:
        return CITY_BY_PREFIX[prefix2]
    if depot_lat is not None:
        if -37.5 < depot_lat < -36.0: return 'Auckland'
        elif -42.0 < depot_lat < -40.5: return 'Wellington'
        elif -44.5 < depot_lat < -43.0: return 'Christchurch'
        elif -38.5 < depot_lat < -37.5: return 'Hamilton'
    return 'Other'

def parse_date(date_str):
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str.split(' ')[0], '%d/%m/%Y')
        return dt.strftime('%Y-%m-%d')
    except:
        return None

def safe_float(v, default=0.0):
    if v is None or v == '':
        return default
    try:
        return float(v)
    except:
        return default

def main():
    print("Connecting to Railway PostgreSQL...")
    conn = psycopg2.connect(RAILWAY_DSN)
    cur = conn.cursor()

    # =========================================================
    # PHASE 1: Post-March 2025 — DEL suffix jobs (new model)
    # =========================================================
    print("\n=== PHASE 1: Post-March 2025 DEL-suffix jobs ===")
    cur.execute("""
        SELECT runname, ucjbdate,
               pickuplatitude, pickuplongitude,
               deliverylatitude, deliverylongitude,
               ucjbamount, rawbaseamount, fuelsurchargeamount,
               ucjbclientcode
        FROM tucjobarchive
        WHERE ucjbclientcode IN ('WOOP','WOOPH','WOOPW','WOOPC')
          AND UPPER(ucjbnumber) LIKE '%DEL'
          AND ucjbspeed = '95'
          AND jobrelationshiptypeid = '20'
          AND (ucjbvoid = 'False' OR ucjbvoid = '0')
          AND runname IS NOT NULL AND runname != ''
          AND deliverylatitude IS NOT NULL AND deliverylatitude != ''
          AND deliverylongitude IS NOT NULL AND deliverylongitude != ''
    """)
    del_rows = cur.fetchall()
    print(f"  Fetched {len(del_rows)} DEL delivery rows")

    # Also get ALL jobs in the same runs (to calculate total run revenue)
    cur.execute("""
        SELECT runname, ucjbdate, ucjbamount
        FROM tucjobarchive
        WHERE ucjbclientcode IN ('WOOP','WOOPH','WOOPW','WOOPC')
          AND runname IS NOT NULL AND runname != ''
          AND (ucjbvoid = 'False' OR ucjbvoid = '0')
          AND ucjbdate IN (
              SELECT DISTINCT ucjbdate FROM tucjobarchive
              WHERE ucjbclientcode IN ('WOOP','WOOPH','WOOPW','WOOPC')
                AND UPPER(ucjbnumber) LIKE '%DEL'
                AND ucjbspeed = '95'
                AND jobrelationshiptypeid = '20'
          )
    """)
    all_run_rows = cur.fetchall()
    print(f"  Fetched {len(all_run_rows)} total run rows (for proportion calc)")

    # Build total run revenue lookup
    total_run_rev = defaultdict(float)
    for rn, dt, amt in all_run_rows:
        d = parse_date(dt)
        if d:
            total_run_rev[(rn, d)] += safe_float(amt)

    # =========================================================
    # PHASE 2: Pre-March 2025 — old model (rel=1, speed=95)
    # =========================================================
    print("\n=== PHASE 2: Pre-March 2025 old model jobs ===")
    cur.execute("""
        SELECT runname, ucjbdate,
               pickuplatitude, pickuplongitude,
               deliverylatitude, deliverylongitude,
               ucjbamount, rawbaseamount, fuelsurchargeamount,
               ucjbclientcode
        FROM tucjobarchive
        WHERE ucjbclientcode IN ('WOOP','WOOPH','WOOPW','WOOPC')
          AND ucjbspeed = '95'
          AND jobrelationshiptypeid = '1'
          AND (ucjbvoid = 'False' OR ucjbvoid = '0')
          AND runname IS NOT NULL AND runname != ''
          AND deliverylatitude IS NOT NULL AND deliverylatitude != ''
          AND deliverylongitude IS NOT NULL AND deliverylongitude != ''
    """)
    old_rows = cur.fetchall()
    print(f"  Fetched {len(old_rows)} old model delivery rows")

    conn.close()

    # =========================================================
    # PROCESS BOTH PERIODS
    # =========================================================
    def process_runs(rows, period_label):
        runs = defaultdict(lambda: {
            'deliveries': [], 'depot': None,
            'del_revenue': 0.0, 'base_revenue': 0.0, 'mfv_paid': 0.0,
            'client_code': None
        })
        skipped = 0
        for row in rows:
            rn, dt_str, plat, plng, dlat, dlng, amt, base, mfv, client = row
            date = parse_date(dt_str)
            if not date:
                skipped += 1
                continue
            dlat_f = safe_float(dlat)
            dlng_f = safe_float(dlng)
            plat_f = safe_float(plat)
            plng_f = safe_float(plng)
            if abs(dlat_f) < 1 or abs(dlng_f) < 1:
                skipped += 1
                continue

            key = (rn, date)
            run = runs[key]
            run['deliveries'].append((dlat_f, dlng_f))
            run['del_revenue'] += safe_float(amt)
            run['base_revenue'] += safe_float(base)
            run['mfv_paid'] += safe_float(mfv)
            run['client_code'] = client
            if run['depot'] is None and abs(plat_f) > 1 and abs(plng_f) > 1:
                run['depot'] = (plat_f, plng_f)

        print(f"  {period_label}: {len(runs)} runs, {skipped} skipped")

        results = []
        mfv_rate = calc_mfv_rate(PUMP_PRICE)
        print(f"  MFV rate at ${PUMP_PRICE}/L: {mfv_rate*100:.1f}%")

        for (rn, date), run in runs.items():
            if run['depot'] is None or len(run['deliveries']) < 1:
                continue

            drops = len(run['deliveries'])
            haversine = nearest_neighbour_tsp(run['depot'], run['deliveries'])
            road_km = haversine * ROAD_MULTIPLIER
            city = classify_city(rn, run['depot'][0])
            if city == 'Other':
                continue

            litres = road_km * CONSUMPTION / 100
            extra_fuel = (PUMP_PRICE - BASE_FUEL_PRICE) * litres
            mfv_should_be = run['del_revenue'] * mfv_rate
            mfv_actual = run['mfv_paid']
            surplus = mfv_actual - extra_fuel

            # Total run revenue (for proportion, post-March only)
            tot_rev = total_run_rev.get((rn, date), run['del_revenue'])

            results.append({
                'run': rn, 'date': date, 'city': city, 'drops': drops,
                'km': round(road_km, 1),
                'del_rev': round(run['del_revenue'], 2),
                'base_rev': round(run['base_revenue'], 2),
                'total_rev': round(tot_rev, 2),
                'mfv_paid': round(mfv_actual, 2),
                'mfv_should': round(mfv_should_be, 2),
                'extra_fuel': round(extra_fuel, 2),
                'surplus': round(surplus, 2),
                'litres': round(litres, 1),
            })

        return results

    post_results = process_runs(del_rows, "Post-March 2025")
    pre_results = process_runs(old_rows, "Pre-March 2025")

    # Filter pre-March to only runs that have MFV data
    pre_with_mfv = [r for r in pre_results if r['mfv_paid'] > 0]
    pre_no_mfv = [r for r in pre_results if r['mfv_paid'] <= 0]
    print(f"  Pre-March: {len(pre_with_mfv)} runs with MFV, {len(pre_no_mfv)} without")

    # =========================================================
    # AGGREGATE FOR THE HTML PAGE
    # =========================================================
    import random

    CITIES = ['Auckland', 'Wellington', 'Christchurch', 'Hamilton', 'Tauranga']

    def aggregate(results, label):
        city_stats = {}
        for city in CITIES:
            cr = [r for r in results if r['city'] == city]
            if not cr:
                continue
            n = len(cr)
            city_stats[city] = {
                'runs': n,
                'avg_km': round(sum(r['km'] for r in cr) / n, 1),
                'avg_drops': round(sum(r['drops'] for r in cr) / n, 1),
                'avg_del_rev': round(sum(r['del_rev'] for r in cr) / n, 2),
                'avg_total_rev': round(sum(r['total_rev'] for r in cr) / n, 2),
                'avg_mfv_paid': round(sum(r['mfv_paid'] for r in cr) / n, 2),
                'avg_extra_fuel': round(sum(r['extra_fuel'] for r in cr) / n, 2),
                'avg_surplus': round(sum(r['surplus'] for r in cr) / n, 2),
                'total_mfv': round(sum(r['mfv_paid'] for r in cr), 0),
                'total_fuel': round(sum(r['extra_fuel'] for r in cr), 0),
                'total_surplus': round(sum(r['surplus'] for r in cr), 0),
                'del_pct': round(sum(r['del_rev'] for r in cr) / max(sum(r['total_rev'] for r in cr), 1) * 100, 1),
                'mfv_pct_of_base': round(sum(r['mfv_paid'] for r in cr) / max(sum(r['base_rev'] for r in cr), 1) * 100, 2),
                'fair_mfv_pct': round(sum(r['extra_fuel'] for r in cr) / max(sum(r['del_rev'] for r in cr), 1) * 100, 2),
                'over_count': sum(1 for r in cr if r['surplus'] >= 0),
                'under_count': sum(1 for r in cr if r['surplus'] < 0),
                'under_pct': round(sum(1 for r in cr if r['surplus'] < 0) / max(n, 1) * 100, 1),
                'avg_under_deficit': round(sum(r['surplus'] for r in cr if r['surplus'] < 0) / max(sum(1 for r in cr if r['surplus'] < 0), 1), 2),
                'avg_over_surplus': round(sum(r['surplus'] for r in cr if r['surplus'] >= 0) / max(sum(1 for r in cr if r['surplus'] >= 0), 1), 2),
            }

        # Scatter samples (max 150 per city)
        scatter = {}
        for city in CITIES:
            cr = [r for r in results if r['city'] == city and r['km'] > 0 and r['km'] < 500]
            sample = random.sample(cr, min(150, len(cr)))
            scatter[city] = [[r['km'], r['mfv_paid'], r['extra_fuel'], r['surplus'], r['del_rev']] for r in sample]

        # Distribution: surplus in $5 buckets
        surplus_dist = {}
        for city in CITIES:
            cr = [r for r in results if r['city'] == city]
            buckets = defaultdict(int)
            for r in cr:
                b = int(r['surplus'] / 5) * 5
                b = max(-50, min(50, b))
                buckets[b] += 1
            surplus_dist[city] = dict(sorted(buckets.items()))

        return {
            'city_stats': city_stats,
            'scatter': scatter,
            'surplus_dist': surplus_dist,
        }

    post_agg = aggregate(post_results, "Post-March 2025")
    pre_agg = aggregate(pre_with_mfv, "Pre-March 2025")

    # Monthly trend (post-March only, by month)
    monthly = defaultdict(lambda: defaultdict(lambda: {'runs': 0, 'mfv': 0, 'fuel': 0, 'rev': 0, 'km': 0}))
    for r in post_results:
        m = r['date'][:7]
        city = r['city']
        if city in CITIES:
            ms = monthly[m][city]
            ms['runs'] += 1
            ms['mfv'] += r['mfv_paid']
            ms['fuel'] += r['extra_fuel']
            ms['rev'] += r['del_rev']
            ms['km'] += r['km']

    months_sorted = sorted(monthly.keys())
    monthly_series = {}
    for city in CITIES:
        monthly_series[city] = {
            'months': months_sorted,
            'avg_surplus': [round((monthly[m][city]['mfv'] - monthly[m][city]['fuel']) / max(monthly[m][city]['runs'], 1), 2) if monthly[m][city]['runs'] > 0 else None for m in months_sorted],
            'avg_mfv': [round(monthly[m][city]['mfv'] / max(monthly[m][city]['runs'], 1), 2) if monthly[m][city]['runs'] > 0 else None for m in months_sorted],
            'avg_fuel': [round(monthly[m][city]['fuel'] / max(monthly[m][city]['runs'], 1), 2) if monthly[m][city]['runs'] > 0 else None for m in months_sorted],
            'runs': [monthly[m][city]['runs'] for m in months_sorted],
        }

    # Pre-March comparison stats (aggregate across all pre-March data with MFV)
    pre_summary = {}
    for city in CITIES:
        cr = [r for r in pre_with_mfv if r['city'] == city]
        if not cr:
            continue
        n = len(cr)
        pre_summary[city] = {
            'runs': n,
            'avg_del_rev': round(sum(r['del_rev'] for r in cr) / n, 2),
            'avg_mfv_paid': round(sum(r['mfv_paid'] for r in cr) / n, 2),
            'avg_extra_fuel': round(sum(r['extra_fuel'] for r in cr) / n, 2),
            'avg_surplus': round(sum(r['surplus'] for r in cr) / n, 2),
            'avg_km': round(sum(r['km'] for r in cr) / n, 1),
            'mfv_pct_of_base': round(sum(r['mfv_paid'] for r in cr) / max(sum(r['base_rev'] for r in cr), 1) * 100, 2),
        }

    output = {
        'post': post_agg,
        'pre_summary': pre_summary,
        'monthly': monthly_series,
        'months': months_sorted,
        'params': {
            'base_fuel': BASE_FUEL_PRICE,
            'pump_price': PUMP_PRICE,
            'consumption': CONSUMPTION,
            'road_multiplier': ROAD_MULTIPLIER,
            'mfv_rate': calc_mfv_rate(PUMP_PRICE),
        },
        'post_total_runs': len(post_results),
        'post_total_jobs': len(del_rows),
        'pre_total_runs': len(pre_with_mfv),
        'pre_total_jobs': sum(1 for r in old_rows if safe_float(r[8]) > 0),
        'generated': datetime.now().strftime('%Y-%m-%d %H:%M'),
    }

    out_path = 'C:/Users/SteveB/1on1/NP-Agent-Management/mfv_data.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, separators=(',', ':'))

    import os
    print(f"\nOutput: {os.path.getsize(out_path)/1024:.0f} KB to {out_path}")

    # Print summaries
    print("\n=== POST-MARCH 2025 CITY SUMMARY ===")
    for city in CITIES:
        s = post_agg['city_stats'].get(city)
        if not s: continue
        print(f"  {city:15s}: {s['runs']:>4} runs, avg DEL ${s['avg_del_rev']:.0f}, avg MFV ${s['avg_mfv_paid']:.2f}, avg fuel ${s['avg_extra_fuel']:.2f}, surplus ${s['avg_surplus']:+.2f}, DEL%={s['del_pct']:.0f}%, fair MFV={s['fair_mfv_pct']:.1f}%")

    print("\n=== PRE-MARCH 2025 COMPARISON ===")
    for city in CITIES:
        s = pre_summary.get(city)
        if not s: continue
        print(f"  {city:15s}: {s['runs']:>5} runs, avg rev ${s['avg_del_rev']:.0f}, avg MFV ${s['avg_mfv_paid']:.2f}, avg fuel ${s['avg_extra_fuel']:.2f}, surplus ${s['avg_surplus']:+.2f}")

if __name__ == '__main__':
    main()
