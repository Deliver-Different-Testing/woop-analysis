#!/usr/bin/env python3
"""Aggregate km_data.json into compact data structures for the HTML page."""
import json
import random
from collections import defaultdict

with open('C:/Users/SteveB/1on1/NP-Agent-Management/km_data.json') as f:
    data = json.load(f)

runs = data['runs']

# 1. City summary
city_summary = {}
city_runs = defaultdict(list)
for r in runs:
    city_runs[r['city']].append(r)

for city, city_r in city_runs.items():
    total_km = sum(r['km'] for r in city_r)
    total_rev = sum(r['revenue'] for r in city_r)
    total_drops = sum(r['drops'] for r in city_r)
    n = len(city_r)
    city_summary[city] = {
        'runs': n,
        'avg_km': round(total_km / n, 1),
        'avg_rev': round(total_rev / n, 2),
        'avg_drops': round(total_drops / n, 1),
        'rev_per_km': round(total_rev / total_km, 2) if total_km > 0 else 0,
        'total_km': round(total_km, 0),
        'total_rev': round(total_rev, 0),
        'total_drops': total_drops,
        'km_per_drop': round(total_km / total_drops, 2) if total_drops > 0 else 0,
    }

print("=== CITY SUMMARY ===")
for c, s in sorted(city_summary.items()):
    print(f"  {c}: {json.dumps(s)}")

# 2. Scatter plot samples (max 200 per city, skip Other/Regional if small)
scatter_data = {}
main_cities = ['Auckland', 'Wellington', 'Christchurch', 'Hamilton', 'Tauranga']
for city in main_cities:
    cr = city_runs.get(city, [])
    # Filter out extreme outliers (km > 500 or revenue > 3000)
    cr = [r for r in cr if r['km'] < 500 and r['revenue'] < 3000 and r['km'] > 0]
    sample = random.sample(cr, min(200, len(cr)))
    scatter_data[city] = [[r['km'], r['revenue'], r['drops']] for r in sample]

print(f"\nScatter samples: {sum(len(v) for v in scatter_data.values())} points")

# 3. Monthly time series by city
monthly = defaultdict(lambda: defaultdict(lambda: {'runs': 0, 'km': 0, 'rev': 0, 'drops': 0}))
for r in runs:
    month = r['date'][:7]
    city = r['city']
    if city not in main_cities:
        continue
    m = monthly[month][city]
    m['runs'] += 1
    m['km'] += r['km']
    m['rev'] += r['revenue']
    m['drops'] += r['drops']

months_sorted = sorted(monthly.keys())
monthly_series = {}
for city in main_cities:
    monthly_series[city] = {
        'months': months_sorted,
        'avg_km': [round(monthly[m][city]['km'] / monthly[m][city]['runs'], 1) if monthly[m][city]['runs'] > 0 else None for m in months_sorted],
        'rev_per_km': [round(monthly[m][city]['rev'] / monthly[m][city]['km'], 2) if monthly[m][city]['km'] > 0 else None for m in months_sorted],
        'avg_drops': [round(monthly[m][city]['drops'] / monthly[m][city]['runs'], 1) if monthly[m][city]['runs'] > 0 else None for m in months_sorted],
        'runs': [monthly[m][city]['runs'] for m in months_sorted],
    }

print(f"Monthly series: {len(months_sorted)} months")

# 4. KM distribution buckets by city (10km buckets)
km_dist = {}
for city in main_cities:
    cr = city_runs.get(city, [])
    buckets = defaultdict(int)
    for r in cr:
        bucket = min(int(r['km'] / 10) * 10, 250)  # cap at 250+
        buckets[bucket] += 1
    km_dist[city] = dict(sorted(buckets.items()))

# 5. Rev/km distribution buckets by city ($0.50 buckets)
rev_km_dist = {}
for city in main_cities:
    cr = city_runs.get(city, [])
    buckets = defaultdict(int)
    for r in cr:
        if r['km'] > 0:
            rpk = r['revenue'] / r['km']
            bucket = round(min(int(rpk / 0.5) * 0.5, 15.0), 1)  # cap at $15+
            buckets[bucket] += 1
    rev_km_dist[city] = {str(k): v for k, v in sorted(buckets.items())}

# 6. Top/bottom runs per city for table
top_bottom = {}
for city in main_cities:
    cr = [r for r in city_runs.get(city, []) if r['km'] > 0]
    by_rev_km = sorted(cr, key=lambda r: r['revenue'] / r['km'] if r['km'] > 0 else 0, reverse=True)
    top_bottom[city] = {
        'best': [{'run': r['run'], 'date': r['date'], 'km': r['km'], 'rev': r['revenue'], 'drops': r['drops'], 'rpk': round(r['revenue']/r['km'], 2)} for r in by_rev_km[:10]],
        'worst': [{'run': r['run'], 'date': r['date'], 'km': r['km'], 'rev': r['revenue'], 'drops': r['drops'], 'rpk': round(r['revenue']/r['km'], 2)} for r in by_rev_km[-10:]],
    }

output = {
    'city_summary': city_summary,
    'scatter': scatter_data,
    'monthly': monthly_series,
    'months': months_sorted,
    'km_dist': km_dist,
    'rev_km_dist': rev_km_dist,
    'top_bottom': top_bottom,
    'total_runs': data['total_runs'],
    'total_deliveries': data['total_deliveries'],
    'generated': data['generated'],
}

out_path = 'C:/Users/SteveB/1on1/NP-Agent-Management/km_page_data.json'
with open(out_path, 'w') as f:
    json.dump(output, f)

import os
size = os.path.getsize(out_path)
print(f"\nAggregated data written to {out_path} ({size/1024:.0f} KB)")
