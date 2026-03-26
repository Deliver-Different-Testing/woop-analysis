import pymssql

conn = pymssql.connect(
    server='urgent-couriers-sql-server-urgent-prod.c9wsc8ywswov.ap-southeast-2.rds.amazonaws.com',
    port=1433, user='admin', password='Y3sF0Z9*3Z~WA2yvp$0roJzLGt?f',
    database='Despatch-Urgent-Prod'
)
cur = conn.cursor()

woop_ids = '16867,17534,17535,18005,34155'

cities = {
    'hamilton': {
        'suburbs': "Hamilton%,Hillcrest%,Rototuna%,Chartwell%,Dinsdale%,Frankton%,Te Rapa%,Claudelands%,Hamilton East%,Flagstaff%,Pukete%,Melville%,Nawton%,Tauranga%,Mt Maunganui%,Papamoa%,Bethlehem%,Greerton%,Otumoetai%,Welcome Bay%,Cambridge%,Matamata%,Te Awamutu%,Morrinsville%,Te Puke%,Ngaruawahia%,Huntly%,Raglan%,Katikati%,Rotorua%,Taupo%,Te Puna%,Pyes Pa%,Gate Pa%",
        'rates': [8.54, 8.83, 10.02, 18.56, 29.37, 34.92]
    },
    'wellington': {
        'suburbs': "Wellington%,Thorndon%,Kelburn%,Brooklyn%,Newtown%,Miramar%,Karori%,Khandallah%,Johnsonville%,Tawa%,Porirua%,Paraparaumu%,Petone%,Lower Hutt%,Upper Hutt%,Wainuiomata%,Naenae%,Stokes Valley%,Wadestown%,Ngaio%,Churton Park%,Newlands%,Hataitai%,Kilbirnie%,Lyall Bay%,Island Bay%,Mt Victoria%,Te Aro%,Plimmerton%,Raumati%,Waikanae%,Otaki%,Levin%,Masterton%,Kapiti%,Eastbourne%,Avalon%,Waterloo%,Taita%,Seaview%",
        'rates': [8.85, 9.29, 12.23, 14.43, 33.80, 35.58]
    },
    'christchurch': {
        'suburbs': "Christchurch%,Riccarton%,Ilam%,Fendalton%,Merivale%,St Albans%,Papanui%,Burnside%,Avonhead%,Sockburn%,Hornby%,Wigram%,Belfast%,Redwood%,Northwood%,New Brighton%,Woolston%,Sumner%,Lyttelton%,Cashmere%,Spreydon%,Addington%,Sydenham%,Linwood%,Halswell%,Prebbleton%,Lincoln%,Rolleston%,Rangiora%,Kaiapoi%,Woodend%,Ashburton%,Timaru%,Harewood%,Bishopdale%,Templeton%,Ferrymead%,Mt Pleasant%",
        'rates': [9.50, 9.68, 13.57, 14.53, 19.25, 23.98]
    }
}

for city, cfg in cities.items():
    patterns = cfg['suburbs'].split(',')
    like_clauses = ' OR '.join([f"s.ucsuName LIKE '{p.strip()}'" for p in patterns])
    
    sql = f"""
    SELECT COALESCE(j.RawBaseAmount, j.ucjbAmount) as base_amt, s.ucsuName
    FROM tucJobArchive j
    JOIN tucSuburb s ON j.ucjbTo = s.ucsuID
    WHERE j.ucjbClientID IN ({woop_ids})
      AND j.ucjbVoid = 0
      AND j.ucjbDate >= '2025-04-01' AND j.ucjbDate < '2026-01-01'
      AND j.JobRelationshipTypeID = 20
      AND j.ucjbSpeed IN (94, 95)
      AND COALESCE(j.RawBaseAmount, j.ucjbAmount) > 0
      AND COALESCE(j.RawBaseAmount, j.ucjbAmount) < 200
      AND ({like_clauses})
    """
    
    cur.execute(sql)
    rows = cur.fetchall()
    
    rates = cfg['rates']
    # Calculate midpoint boundaries
    boundaries = []
    for i in range(len(rates)-1):
        boundaries.append((rates[i] + rates[i+1]) / 2)
    # boundaries: between Z1-Z2, Z2-Z3, Z3-Z4, Z4-Z5, Z5-Z6
    
    zones = {i: [] for i in range(1, 7)}
    suburb_data = {}
    
    for amt, suburb in rows:
        amt = float(amt)
        # Classify
        zone = 6
        for i, b in enumerate(boundaries):
            if amt < b:
                zone = i + 1
                break
        zones[zone].append(amt)
        
        if suburb not in suburb_data:
            suburb_data[suburb] = []
        suburb_data[suburb].append(amt)
    
    total = len(rows)
    print(f"\n=== {city.upper()} === (total: {total})")
    print(f"Boundaries: {boundaries}")
    
    for z in range(1, 7):
        vals = zones[z]
        if vals:
            avg = sum(vals) / len(vals)
            share = len(vals) / total if total else 0
            print(f"  Z{z}: avg=${avg:.2f}, n={len(vals)}, share={share:.3f}")
        else:
            print(f"  Z{z}: no data")
    
    # Top suburbs
    print(f"\n  Top suburbs:")
    top = sorted(suburb_data.items(), key=lambda x: -len(x[1]))[:10]
    for name, vals in top:
        print(f"    {name}: n={len(vals)}, avg=${sum(vals)/len(vals):.2f}")

conn.close()
