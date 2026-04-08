#!/usr/bin/env python3
"""
Extract Woop bulk run data, calculate nearest-neighbour TSP distance per run,
and output JSON for the analysis page.

Groups by (runname, date) since run names repeat weekly.
Uses Haversine distance with 1.27x road multiplier.
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
for p in ['MW','MO','MA','MT']:
    CITY_BY_PREFIX[p] = 'Regional'
for p in ['PW','PX','PN']:
    CITY_BY_PREFIX[p] = 'Regional'
for p in ['DW','NX','Ru','E/','ED','EB','EC','EH','LM']:
    CITY_BY_PREFIX[p] = 'Regional'

ROAD_MULTIPLIER = 1.27

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

def classify_city(runname, depot_lat, depot_lng):
    prefix2 = runname[:2] if len(runname) >= 2 else runname
    if prefix2 in CITY_BY_PREFIX:
        return CITY_BY_PREFIX[prefix2]
    if depot_lat is not None:
        if -37.5 < depot_lat < -36.0:
            return 'Auckland'
        elif -42.0 < depot_lat < -40.5:
            return 'Wellington'
        elif -44.5 < depot_lat < -43.0:
            return 'Christchurch'
        elif -38.5 < depot_lat < -37.5:
            return 'Hamilton'
        elif -38.0 < depot_lat < -37.5:
            return 'Tauranga'
    return 'Other'

def parse_date(date_str):
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str.split(' ')[0], '%d/%m/%Y')
        return dt.strftime('%Y-%m-%d')
    except:
        return None

def main():
    print("Connecting to Railway PostgreSQL...")
    conn = psycopg2.connect(RAILWAY_DSN)
    cur = conn.cursor()

    print("Querying all Woop bulk run deliveries with geo data...")
    cur.execute("""
        SELECT runname, ucjbdate,
               pickuplatitude, pickuplongitude,
               deliverylatitude, deliverylongitude,
               ucjbamount, rawbaseamount, ucjbclientcode,
               depotid, droprunorder
        FROM tucjobarchive
        WHERE ucjbclientcode IN ('WOOP','WOOPH','WOOPW','WOOPC')
          AND runname IS NOT NULL AND runname != ''
          AND deliverylatitude IS NOT NULL AND deliverylatitude != ''
          AND deliverylongitude IS NOT NULL AND deliverylongitude != ''
          AND (ucjbvoid = 'False' OR ucjbvoid = '0')
    """)

    rows = cur.fetchall()
    conn.close()
    print(f"Fetched {len(rows)} delivery rows")

    # Group by (runname, date)
    runs = defaultdict(lambda: {
        'deliveries': [],
        'depot': None,
        'revenue': 0.0,
        'base_revenue': 0.0,
        'client_code': None
    })

    skipped = 0
    for row in rows:
        runname, date_str, plat, plng, dlat, dlng, amt, base_amt, client, depotid, order = row
        date = parse_date(date_str)
        if not date:
            skipped += 1
            continue
        try:
            dlat_f = float(dlat)
            dlng_f = float(dlng)
            plat_f = float(plat) if plat else None
            plng_f = float(plng) if plng else None
            amt_f = float(amt) if amt else 0
            base_f = float(base_amt) if base_amt else 0
        except (ValueError, TypeError):
            skipped += 1
            continue
        if abs(dlat_f) < 1 or abs(dlng_f) < 1:
            skipped += 1
            continue

        key = (runname, date)
        run = runs[key]
        run['deliveries'].append((dlat_f, dlng_f))
        run['revenue'] += amt_f
        run['base_revenue'] += base_f
        run['client_code'] = client
        if run['depot'] is None and plat_f and plng_f and abs(plat_f) > 1:
            run['depot'] = (plat_f, plng_f)

    print(f"Skipped {skipped} rows with bad data")
    print(f"Grouped into {len(runs)} unique runs (runname + date)")

    # Calculate TSP distance for each run
    results = []
    no_depot = 0
    for (runname, date), run in runs.items():
        if run['depot'] is None:
            no_depot += 1
            continue
        drops = len(run['deliveries'])
        if drops < 1:
            continue

        haversine_km_total = nearest_neighbour_tsp(run['depot'], run['deliveries'])
        road_km = haversine_km_total * ROAD_MULTIPLIER
        city = classify_city(runname, run['depot'][0], run['depot'][1])

        results.append({
            'run': runname,
            'date': date,
            'city': city,
            'drops': drops,
            'km': round(road_km, 1),
            'revenue': round(run['revenue'], 2),
            'base_revenue': round(run['base_revenue'], 2),
            'depot_lat': round(run['depot'][0], 4),
            'depot_lng': round(run['depot'][1], 4),
            'km_per_drop': round(road_km / drops, 2) if drops > 0 else 0,
            'rev_per_km': round(run['revenue'] / road_km, 2) if road_km > 0 else 0,
        })

    print(f"Calculated distances for {len(results)} runs ({no_depot} skipped - no depot)")

    results.sort(key=lambda r: r['date'], reverse=True)

    # Summary stats by city
    city_stats = {}
    for r in results:
        c = r['city']
        if c not in city_stats:
            city_stats[c] = {'runs': 0, 'total_km': 0, 'total_rev': 0, 'total_drops': 0, 'total_base_rev': 0}
        cs = city_stats[c]
        cs['runs'] += 1
        cs['total_km'] += r['km']
        cs['total_rev'] += r['revenue']
        cs['total_base_rev'] += r['base_revenue']
        cs['total_drops'] += r['drops']

    print("\n=== CITY SUMMARY ===")
    for city in sorted(city_stats.keys()):
        s = city_stats[city]
        avg_km = s['total_km'] / s['runs'] if s['runs'] > 0 else 0
        avg_rev = s['total_rev'] / s['runs'] if s['runs'] > 0 else 0
        avg_drops = s['total_drops'] / s['runs'] if s['runs'] > 0 else 0
        rev_per_km = s['total_rev'] / s['total_km'] if s['total_km'] > 0 else 0
        print(f"  {city:15s}: {s['runs']:5d} runs, avg {avg_km:.0f}km, avg ${avg_rev:.0f} rev, avg {avg_drops:.0f} drops, ${rev_per_km:.2f}/km")

    # Monthly summary for time series
    monthly = defaultdict(lambda: defaultdict(lambda: {'runs': 0, 'km': 0, 'rev': 0, 'drops': 0}))
    for r in results:
        month = r['date'][:7]
        city = r['city']
        m = monthly[month][city]
        m['runs'] += 1
        m['km'] += r['km']
        m['rev'] += r['revenue']
        m['drops'] += r['drops']

    monthly_data = {}
    for month in sorted(monthly.keys()):
        monthly_data[month] = {}
        for city, stats in monthly[month].items():
            monthly_data[month][city] = {
                'runs': stats['runs'],
                'avg_km': round(stats['km'] / stats['runs'], 1) if stats['runs'] > 0 else 0,
                'avg_rev': round(stats['rev'] / stats['runs'], 2) if stats['runs'] > 0 else 0,
                'avg_drops': round(stats['drops'] / stats['runs'], 1) if stats['runs'] > 0 else 0,
                'rev_per_km': round(stats['rev'] / stats['km'], 2) if stats['km'] > 0 else 0,
            }

    output = {
        'runs': results,
        'city_stats': city_stats,
        'monthly': monthly_data,
        'total_runs': len(results),
        'total_deliveries': sum(r['drops'] for r in results),
        'generated': datetime.now().strftime('%Y-%m-%d %H:%M'),
    }

    out_path = 'C:/Users/SteveB/1on1/NP-Agent-Management/km_data.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\nOutput written to {out_path}")
    print(f"Total: {len(results)} runs, {output['total_deliveries']} deliveries")

if __name__ == '__main__':
    main()
