#!/usr/bin/env python3
"""
Extract Woop cost decomposition data for 2017-2025.

Breaks down per-box cost increase into: base rate, linehaul, fuel surcharge.
Classifies by region using run name prefixes.
Handles three linehaul periods and geographic expansion analysis.

Database: Railway PostgreSQL (tucjobarchive)
Date format in DB: dd/mm/yyyy hh:mm:ss am
"""
import psycopg2
import json
import os
import re
from collections import defaultdict
from datetime import datetime

RAILWAY_DSN = "postgresql://postgres:QUCLoTKRmLWvkDwnpfGQSerEwEavctOP@hopper.proxy.rlwy.net:20735/railway"

REGION_PREFIXES = {}
for p in ['AW','AH','A1','A2','A3','A4','A5','A6','A7','A8','A9','AC','AM','AU','AX','NW','Aw']:
    REGION_PREFIXES[p] = 'Auckland'
for p in ['HW','H1','H2','H3','H4','H5','H6','HX','HR']:
    REGION_PREFIXES[p] = 'Waikato/BoP'
for p in ['TW','T0','T1','T2','T3','T4','T5','T6','TX','TG']:
    REGION_PREFIXES[p] = 'Waikato/BoP'
for p in ['WW','W0','W1','W2','W3','W4','W5','W6','W7','W8','W9','WA','WC','WE','WM','WX','WT','WO','WH','WP','WF','WL']:
    REGION_PREFIXES[p] = 'Wellington'
for p in ['CW','C0','C1','C2','C3','C4','C5','C6','C7','C8','C9','CC','CR','CX','CM','CA','CD','CI']:
    REGION_PREFIXES[p] = 'Christchurch'

def classify_region(runname):
    if not runname:
        return 'Other'
    rn = runname.strip()
    if len(rn) >= 2:
        prefix = rn[:2]
        if prefix in REGION_PREFIXES:
            return REGION_PREFIXES[prefix]
    return 'Other'

def parse_date(datestr):
    """Parse dd/mm/yyyy hh:mm:ss am format."""
    if not datestr:
        return None
    try:
        # Take just the date part before the time
        dpart = datestr.strip().split(' ')[0]
        return datetime.strptime(dpart, '%d/%m/%Y')
    except Exception:
        try:
            return datetime.strptime(datestr[:10], '%Y-%m-%d')
        except Exception:
            return None

def safe_float(val):
    try:
        return float(val) if val is not None else 0.0
    except (ValueError, TypeError):
        return 0.0

def main():
    conn = psycopg2.connect(RAILWAY_DSN)
    cur = conn.cursor()

    # =========================================================================
    # QUERY: All Woop jobs with relevant fields
    # =========================================================================
    print("Querying all Woop jobs...")
    cur.execute("""
        SELECT ucjbnumber, ucjbdate, ucjbamount, rawbaseamount,
               fuelsurchargeamount, ucjbclientcode, runname,
               jobrelationshiptypeid, ucjbspeed
        FROM tucjobarchive
        WHERE ucjbclientcode IN ('WOOP','WOOPH','WOOPW','WOOPC')
          AND (ucjbvoid = 'False' OR ucjbvoid = '0')
          AND ucjbamount IS NOT NULL
        ORDER BY ucjbdate
    """)
    rows = cur.fetchall()
    print(f"  Total rows: {len(rows)}")
    cur.close()
    conn.close()

    # =========================================================================
    # Classify and aggregate
    # =========================================================================
    # Job classification:
    #   DELIVERY (old model): rel=1, speed IN (95, 94, 4)
    #   DELIVERY (new model): rel=20, speed=95, ucjbnumber ends in DEL
    #   LINEHAUL (new model): rel=20, speed IN (142, 126) -> LHP, LH1 jobs
    #   PARENT (new model):   rel=19 -> parent/summary jobs, skip to avoid double-count

    yearly_region = defaultdict(lambda: defaultdict(lambda: {
        'del_count': 0, 'del_revenue': 0.0, 'del_base': 0.0, 'del_fuel': 0.0,
        'lh_count': 0, 'lh_revenue': 0.0, 'lh_base': 0.0, 'lh_fuel': 0.0
    }))

    yearly_totals = defaultdict(lambda: {
        'del_count': 0, 'del_revenue': 0.0, 'del_base': 0.0, 'del_fuel': 0.0,
        'lh_count': 0, 'lh_revenue': 0.0, 'lh_base': 0.0, 'lh_fuel': 0.0
    })

    monthly_data = defaultdict(lambda: {
        'del_count': 0, 'del_revenue': 0.0, 'del_base': 0.0, 'del_fuel': 0.0,
        'lh_count': 0, 'lh_revenue': 0.0
    })

    lh_first_seen = None
    lh_jobs_by_year = defaultdict(int)

    skipped = defaultdict(int)
    classified = defaultdict(int)

    for row in rows:
        ucjbnumber, ucjbdate, ucjbamount, rawbaseamount, fuelsurchargeamount, \
            clientcode, runname, rel_type, speed = row

        amt = safe_float(ucjbamount)
        base = safe_float(rawbaseamount)
        fuel = safe_float(fuelsurchargeamount)

        if amt <= 0 or amt > 500:
            skipped['amt_filter'] += 1
            continue

        dt = parse_date(str(ucjbdate) if ucjbdate else '')
        if dt is None:
            skipped['date_parse'] += 1
            continue

        year = dt.year
        if year < 2017 or year > 2025:
            skipped['year_range'] += 1
            continue

        month_key = dt.strftime('%Y-%m')
        region = classify_region(runname)
        rel = str(rel_type).strip() if rel_type else ''
        spd = str(speed).strip() if speed else ''

        job_type = None

        if rel == '20' and spd in ('142', '126'):
            # Linehaul job (LHP or LH1)
            job_type = 'linehaul'
        elif rel == '20' and spd in ('95', '94'):
            # New model delivery (DEL suffix)
            job_type = 'delivery'
        elif rel == '19':
            # Parent/summary job in new model - skip to avoid double-counting
            skipped['parent_job'] += 1
            continue
        elif rel == '1' and spd in ('95', '94', '4'):
            # Old model delivery
            job_type = 'delivery'
        elif rel == '1' and spd in ('120', '110', '96'):
            # Other delivery speeds (less common but still Woop)
            job_type = 'delivery'
        else:
            skipped['other_rel_speed'] += 1
            continue

        classified[job_type] += 1

        if job_type == 'linehaul':
            yearly_region[year][region]['lh_count'] += 1
            yearly_region[year][region]['lh_revenue'] += amt
            yearly_region[year][region]['lh_base'] += base if base > 0 else amt
            yearly_region[year][region]['lh_fuel'] += fuel
            yearly_totals[year]['lh_count'] += 1
            yearly_totals[year]['lh_revenue'] += amt
            yearly_totals[year]['lh_base'] += base if base > 0 else amt
            yearly_totals[year]['lh_fuel'] += fuel
            monthly_data[month_key]['lh_count'] += 1
            monthly_data[month_key]['lh_revenue'] += amt
            lh_jobs_by_year[year] += 1
            if lh_first_seen is None or dt < lh_first_seen:
                lh_first_seen = dt

        elif job_type == 'delivery':
            yearly_region[year][region]['del_count'] += 1
            yearly_region[year][region]['del_revenue'] += amt
            yearly_region[year][region]['del_base'] += base if base > 0 else amt
            yearly_region[year][region]['del_fuel'] += fuel
            yearly_totals[year]['del_count'] += 1
            yearly_totals[year]['del_revenue'] += amt
            yearly_totals[year]['del_base'] += base if base > 0 else amt
            yearly_totals[year]['del_fuel'] += fuel
            monthly_data[month_key]['del_count'] += 1
            monthly_data[month_key]['del_revenue'] += amt
            monthly_data[month_key]['del_base'] += base if base > 0 else amt
            monthly_data[month_key]['del_fuel'] += fuel

    print(f"\nClassification: {dict(classified)}")
    print(f"Skipped: {dict(skipped)}")

    # =========================================================================
    # Build output data
    # =========================================================================
    years = list(range(2017, 2026))
    regions = ['Auckland', 'Waikato/BoP', 'Wellington', 'Christchurch', 'Other']

    # Volume by region per year
    volume_by_region = {}
    for r in regions:
        volume_by_region[r] = [yearly_region[y][r]['del_count'] for y in years]

    # Average per-box delivery cost by region per year
    cost_by_region = {}
    for r in regions:
        costs = []
        for y in years:
            d = yearly_region[y][r]
            if d['del_count'] > 0:
                costs.append(round(d['del_revenue'] / d['del_count'], 2))
            else:
                costs.append(None)
        cost_by_region[r] = costs

    # Overall per-box cost decomposition
    decomposition = []
    for y in years:
        t = yearly_totals[y]
        dc = t['del_count']
        if dc == 0:
            decomposition.append({
                'year': y, 'del_count': 0,
                'avg_total': 0, 'avg_base': 0, 'avg_fuel': 0, 'avg_lh': 0
            })
            continue

        avg_total = t['del_revenue'] / dc
        avg_base_raw = t['del_base'] / dc
        avg_fuel = t['del_fuel'] / dc
        # Linehaul per box = total LH revenue / delivery count
        avg_lh = t['lh_revenue'] / dc if t['lh_revenue'] > 0 else 0

        # If no separate fuel field, base = total amount
        if avg_fuel == 0:
            avg_base = avg_total
        else:
            avg_base = avg_base_raw

        decomposition.append({
            'year': y,
            'del_count': dc,
            'avg_total': round(avg_total, 2),
            'avg_base': round(avg_base, 2),
            'avg_fuel': round(avg_fuel, 2),
            'avg_lh': round(avg_lh, 2)
        })

    # Regional cost detail
    regional_cost_detail = {}
    for r in regions:
        detail = []
        for y in years:
            d = yearly_region[y][r]
            dc = d['del_count']
            if dc == 0:
                detail.append({'year': y, 'del_count': 0, 'avg_total': 0,
                             'avg_base': 0, 'avg_fuel': 0, 'avg_lh': 0})
                continue
            avg_t = d['del_revenue'] / dc
            avg_b = d['del_base'] / dc if d['del_base'] > 0 else avg_t
            avg_f = d['del_fuel'] / dc
            avg_l = d['lh_revenue'] / dc if d['lh_revenue'] > 0 else 0
            if avg_f == 0:
                avg_b = avg_t
            detail.append({
                'year': y, 'del_count': dc,
                'avg_total': round(avg_t, 2), 'avg_base': round(avg_b, 2),
                'avg_fuel': round(avg_f, 2), 'avg_lh': round(avg_l, 2)
            })
        regional_cost_detail[r] = detail

    # Linehaul timeline
    lh_timeline = {
        'first_seen': lh_first_seen.strftime('%Y-%m-%d') if lh_first_seen else None,
        'by_year': {str(y): lh_jobs_by_year.get(y, 0) for y in years}
    }

    # Monthly trend
    sorted_months = sorted(monthly_data.keys())
    monthly_trend = {
        'months': sorted_months,
        'del_count': [monthly_data[m]['del_count'] for m in sorted_months],
        'avg_cost': [
            round(monthly_data[m]['del_revenue'] / monthly_data[m]['del_count'], 2)
            if monthly_data[m]['del_count'] > 0 else None
            for m in sorted_months
        ],
        'avg_fuel': [
            round(monthly_data[m]['del_fuel'] / monthly_data[m]['del_count'], 2)
            if monthly_data[m]['del_count'] > 0 else None
            for m in sorted_months
        ],
        'avg_lh': [
            round(monthly_data[m]['lh_revenue'] / monthly_data[m]['del_count'], 2)
            if monthly_data[m]['del_count'] > 0 else None
            for m in sorted_months
        ]
    }

    # Region share percentages
    region_shares = {}
    for r in regions:
        shares = []
        for y in years:
            total_yr = sum(yearly_region[y][r2]['del_count'] for r2 in regions)
            if total_yr > 0:
                shares.append(round(yearly_region[y][r]['del_count'] / total_yr * 100, 1))
            else:
                shares.append(0)
        region_shares[r] = shares

    # =========================================================================
    # Cost increase attribution (2017 -> 2024)
    # =========================================================================
    b = next(d for d in decomposition if d['year'] == 2017)
    c = next(d for d in decomposition if d['year'] == 2024)
    c25 = next(d for d in decomposition if d['year'] == 2025)

    # Total all-in cost = delivery + linehaul per box
    baseline_allin = b['avg_total'] + b['avg_lh']
    current_allin_24 = c['avg_total'] + c['avg_lh']
    current_allin_25 = c25['avg_total'] + c25['avg_lh']
    total_increase_24 = current_allin_24 - baseline_allin
    total_increase_25 = current_allin_25 - baseline_allin

    # Geographic mix shift: what would 2024 cost be with 2017 regional mix?
    vol_2017 = {r: yearly_region[2017][r]['del_count'] for r in regions}
    total_2017 = sum(vol_2017.values())

    cost_2024_by_region = {}
    for r in regions:
        dc = yearly_region[2024][r]['del_count']
        if dc > 0:
            cost_2024_by_region[r] = (yearly_region[2024][r]['del_revenue'] / dc) + \
                                     (yearly_region[2024][r]['lh_revenue'] / dc if yearly_region[2024][r]['lh_revenue'] > 0 else 0)
        else:
            cost_2024_by_region[r] = 0

    if total_2017 > 0:
        cost_2024_with_2017_mix = sum(
            cost_2024_by_region.get(r, 0) * (vol_2017.get(r, 0) / total_2017)
            for r in regions if vol_2017.get(r, 0) > 0
        )
    else:
        cost_2024_with_2017_mix = 0

    geo_mix_effect = current_allin_24 - cost_2024_with_2017_mix

    attribution = {
        'baseline_year': 2017,
        'comparison_year': 2024,
        'baseline_cost': round(baseline_allin, 2),
        'current_cost_2024': round(current_allin_24, 2),
        'current_cost_2025': round(current_allin_25, 2),
        'total_increase_2024': round(total_increase_24, 2),
        'total_increase_2025': round(total_increase_25, 2),
        'base_rate_increase': round(c['avg_base'] - b['avg_base'], 2),
        'fuel_surcharge': round(c['avg_fuel'], 2),
        'linehaul_component': round(c['avg_lh'], 2),
        'geo_mix_effect': round(geo_mix_effect, 2),
        'zone_mix_residual': 0
    }
    # Residual = total - base_rate - fuel - linehaul - geo
    attribution['zone_mix_residual'] = round(
        attribution['total_increase_2024'] -
        attribution['base_rate_increase'] -
        attribution['fuel_surcharge'] -
        attribution['linehaul_component'] -
        attribution['geo_mix_effect'],
        2
    )

    # =========================================================================
    # Assemble output
    # =========================================================================
    output = {
        'years': years,
        'regions': regions,
        'volume_by_region': volume_by_region,
        'cost_by_region': cost_by_region,
        'decomposition': decomposition,
        'regional_cost_detail': regional_cost_detail,
        'region_shares': region_shares,
        'linehaul_timeline': lh_timeline,
        'monthly_trend': monthly_trend,
        'attribution': attribution,
        'generated': datetime.now().strftime('%Y-%m-%d %H:%M')
    }

    # Print summary
    print("\n=== COST DECOMPOSITION SUMMARY ===")
    print(f"\nLinehaul first seen: {lh_timeline['first_seen']}")
    print(f"LH jobs by year: {dict(lh_jobs_by_year)}")
    print(f"\nDeliveries by year:")
    for d in decomposition:
        print(f"  {d['year']}: {d['del_count']:,} deliveries, "
              f"avg ${d['avg_total']:.2f} (base ${d['avg_base']:.2f} + "
              f"fuel ${d['avg_fuel']:.2f} + LH ${d['avg_lh']:.2f})")

    print(f"\nRegional volumes:")
    for r in regions:
        vols = volume_by_region[r]
        print(f"  {r}: {vols}")

    print(f"\nRegional shares (%):")
    for r in regions:
        print(f"  {r}: {region_shares[r]}")

    print(f"\n=== ATTRIBUTION (2017 -> 2024) ===")
    a = attribution
    print(f"  Baseline (2017): ${a['baseline_cost']:.2f}")
    print(f"  Current (2024):  ${a['current_cost_2024']:.2f}")
    print(f"  Total increase:  ${a['total_increase_2024']:.2f}")
    print(f"  Base rate:       ${a['base_rate_increase']:.2f}")
    print(f"  Fuel surcharge:  ${a['fuel_surcharge']:.2f}")
    print(f"  Linehaul:        ${a['linehaul_component']:.2f}")
    print(f"  Geo mix shift:   ${a['geo_mix_effect']:.2f}")
    print(f"  Zone mix/other:  ${a['zone_mix_residual']:.2f}")

    outdir = os.path.dirname(os.path.abspath(__file__))
    outpath = os.path.join(outdir, 'cost_decomposition_data.json')
    with open(outpath, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\nData written to {outpath}")

if __name__ == '__main__':
    main()
