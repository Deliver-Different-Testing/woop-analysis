#!/usr/bin/env python3
"""
Woop linehaul investigation - queries 3-15.
Runs through HTTP proxy tunnel to SQL Server.
"""
import socket, threading, os, urllib.parse, base64, time, sys
import pymssql

proxy_url = os.environ.get('http_proxy', '')
parsed = urllib.parse.urlparse(proxy_url)
proxy_host = parsed.hostname
proxy_port = parsed.port
proxy_user = parsed.username
proxy_pass = parsed.password

TARGET = 'urgent-couriers-sql-server-urgent-prod.c9wsc8ywswov.ap-southeast-2.rds.amazonaws.com'
LOCAL_PORT = 14332

def create_tunnel():
    auth = base64.b64encode(f'{proxy_user}:{proxy_pass}'.encode()).decode()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(30)
    s.connect((proxy_host, proxy_port))
    t = f'{TARGET}:1433'
    s.sendall(f'CONNECT {t} HTTP/1.1\r\nHost: {t}\r\nProxy-Authorization: Basic {auth}\r\n\r\n'.encode())
    resp = b''
    while b'\r\n\r\n' not in resp:
        c = s.recv(4096)
        if not c: break
        resp += c
    if b'200' in resp.split(b'\r\n')[0]: return s
    s.close()
    raise Exception(f'Tunnel failed')

def forward(a, b):
    try:
        while True:
            d = a.recv(65536)
            if not d: break
            b.sendall(d)
    except: pass

srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(('127.0.0.1', LOCAL_PORT))
srv.listen(5)
srv.settimeout(300)

def accept_loop():
    while True:
        try:
            c, _ = srv.accept()
            t = create_tunnel()
            threading.Thread(target=forward, args=(c, t), daemon=True).start()
            threading.Thread(target=forward, args=(t, c), daemon=True).start()
        except: break

threading.Thread(target=accept_loop, daemon=True).start()
time.sleep(0.5)

conn = pymssql.connect(server='127.0.0.1', port=LOCAL_PORT, user='admin',
                       password='Y3sF0Z9*3Z~WA2yvp$0roJzLGt?f',
                       database='Despatch-Urgent-Prod', login_timeout=30)
cur = conn.cursor()
print('CONNECTED\n', flush=True)

def pq(label, sql, max_rows=200):
    print(f'\n{"="*70}', flush=True)
    print(f'  {label}', flush=True)
    print(f'{"="*70}', flush=True)
    cur.execute(sql)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    print(f'  Columns: {cols}', flush=True)
    print(f'  Rows: {len(rows)}', flush=True)
    for i, r in enumerate(rows):
        if i >= max_rows:
            print(f'  ... ({len(rows)-max_rows} more)', flush=True)
            break
        vals = []
        for j, c in enumerate(cols):
            v = r[j]
            if isinstance(v, float): vals.append(f'{c}={v:.2f}')
            else: vals.append(f'{c}={v}')
        print(f'  {" | ".join(vals)}', flush=True)
    return rows

# Q3: Job number suffix patterns
pq('Q3: Job number suffix patterns', """
    SELECT ucjbClientCode, RIGHT(ucjbNumber, 3) as suffix,
           COUNT(*) as cnt, MIN(ucjbDate) as earliest, MAX(ucjbDate) as latest
    FROM tucJobArchive WHERE ucjbClientCode LIKE '%WOOP%'
    GROUP BY ucjbClientCode, RIGHT(ucjbNumber, 3)
    HAVING COUNT(*) > 5
    ORDER BY ucjbClientCode, cnt DESC
""")

# Q4: Jobs with LH in job number
pq('Q4: Jobs with LH in job number', """
    SELECT ucjbClientCode, ucjbSpeed, JobRelationshipTypeID,
           COUNT(*) as cnt, MIN(ucjbDate) as earliest, MAX(ucjbDate) as latest,
           AVG(ucjbAmount) as avg_amt, SUM(ucjbAmount) as total_amt
    FROM tucJobArchive
    WHERE ucjbClientCode LIKE '%WOOP%' AND ucjbNumber LIKE '%LH%'
    GROUP BY ucjbClientCode, ucjbSpeed, JobRelationshipTypeID
    ORDER BY ucjbClientCode, cnt DESC
""")

# Q5: Non-standard speed IDs with details
pq('Q5: Non-standard speed IDs (NOT 95/94/4)', """
    SELECT ucjbClientCode, ucjbSpeed, JobRelationshipTypeID as rel,
           COUNT(*) as cnt, MIN(ucjbDate) as earliest, MAX(ucjbDate) as latest,
           AVG(ucjbAmount) as avg_amt, SUM(ucjbAmount) as total_amt
    FROM tucJobArchive
    WHERE ucjbClientCode LIKE '%WOOP%' AND ucjbSpeed NOT IN (95, 94, 4)
    GROUP BY ucjbClientCode, ucjbSpeed, JobRelationshipTypeID
    ORDER BY cnt DESC
""")

# Q6: Potential linehaul by year 2021-2024
pq('Q6: Non-standard speed jobs by year 2021-2024', """
    SELECT YEAR(ucjbDate) as yr, ucjbClientCode, ucjbSpeed,
           JobRelationshipTypeID as rel, COUNT(*) as cnt,
           AVG(ucjbAmount) as avg_amt, SUM(ucjbAmount) as total_amt
    FROM tucJobArchive
    WHERE ucjbClientCode LIKE '%WOOP%'
      AND ucjbSpeed NOT IN (95, 94, 4)
      AND ucjbDate >= '2021-01-01' AND ucjbDate < '2025-01-01'
      AND ucjbVoid = 0
    GROUP BY YEAR(ucjbDate), ucjbClientCode, ucjbSpeed, JobRelationshipTypeID
    ORDER BY yr, cnt DESC
""")

# Q7: All relationship types
pq('Q7: All relationship types for Woop', """
    SELECT ucjbClientCode, JobRelationshipTypeID, COUNT(*) as cnt,
           MIN(ucjbDate) as earliest, MAX(ucjbDate) as latest
    FROM tucJobArchive WHERE ucjbClientCode LIKE '%WOOP%'
    GROUP BY ucjbClientCode, JobRelationshipTypeID
    ORDER BY ucjbClientCode, cnt DESC
""")

# Q8: Billing/invoice/linehaul tables
pq('Q8: Billing/invoice/linehaul tables', """
    SELECT TABLE_NAME, TABLE_TYPE
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME LIKE '%linehaul%' OR TABLE_NAME LIKE '%invoice%'
       OR TABLE_NAME LIKE '%billing%' OR TABLE_NAME LIKE '%charge%'
       OR TABLE_NAME LIKE '%surcharge%'
    ORDER BY TABLE_NAME
""")

# Q9: Woop client records
pq('Q9: Woop client records from tucclient', """
    SELECT ucclID, ucclCode, ucclName
    FROM tucclient
    WHERE ucclCode LIKE '%WOOP%' OR ucclName LIKE '%Woop%' OR ucclName LIKE '%WOOP%'
    ORDER BY ucclCode
""")

# Q10: Sample non-standard speed jobs 2021-2024
pq('Q10: Sample non-standard speed jobs 2021-2024', """
    SELECT TOP 30 ucjbNumber, ucjbDate, ucjbClientCode, ucjbSpeed,
           JobRelationshipTypeID as rel, ucjbAmount, RawBaseAmount,
           FuelSurchargeAmount, RunName, ucjbVoid
    FROM tucJobArchive
    WHERE ucjbClientCode LIKE '%WOOP%'
      AND ucjbSpeed NOT IN (95, 94, 4)
      AND ucjbDate >= '2021-01-01' AND ucjbDate < '2025-01-01'
    ORDER BY ucjbDate
""")

# Q11: Jobs with LH-related RunName
pq('Q11: Jobs with LH-related RunName', """
    SELECT ucjbClientCode, RunName, ucjbSpeed,
           COUNT(*) as cnt, MIN(ucjbDate) as earliest, MAX(ucjbDate) as latest,
           AVG(ucjbAmount) as avg_amt
    FROM tucJobArchive
    WHERE ucjbClientCode LIKE '%WOOP%'
      AND (RunName LIKE '%LH%' OR RunName LIKE '%linehaul%' OR RunName LIKE '%Linehaul%')
    GROUP BY ucjbClientCode, RunName, ucjbSpeed
    ORDER BY cnt DESC
""")

# Q12: Speed reference table
pq('Q12: Speed reference - what are the speed names?', """
    SELECT ucspID, ucspName, ucspDescription
    FROM tucSpeed
    WHERE ucspID IN (4, 94, 95, 96, 110, 120, 126, 142)
    ORDER BY ucspID
""")

# Q13: Jobs by client ID (not code) for Woop-related clients
pq('Q13: Jobs by Woop client IDs (by ID not code)', """
    SELECT j.ucjbClientCode, j.ucjbClientID, c.ucclCode, c.ucclName,
           j.ucjbSpeed, j.JobRelationshipTypeID as rel,
           COUNT(*) as cnt
    FROM tucJobArchive j
    JOIN tucclient c ON j.ucjbClientID = c.ucclID
    WHERE (c.ucclCode LIKE '%WOOP%' OR c.ucclName LIKE '%Woop%')
    GROUP BY j.ucjbClientCode, j.ucjbClientID, c.ucclCode, c.ucclName,
             j.ucjbSpeed, j.JobRelationshipTypeID
    ORDER BY c.ucclCode, cnt DESC
""")

# Q14: Monthly linehaul-speed jobs 2021-2024
pq('Q14: Monthly non-standard speed by month 2021-2024', """
    SELECT FORMAT(ucjbDate, 'yyyy-MM') as month,
           ucjbSpeed, COUNT(*) as cnt, SUM(ucjbAmount) as total_amt
    FROM tucJobArchive
    WHERE ucjbClientCode LIKE '%WOOP%'
      AND ucjbDate >= '2021-01-01' AND ucjbDate < '2025-01-01'
      AND ucjbVoid = 0
      AND ucjbSpeed NOT IN (95, 94, 4)
    GROUP BY FORMAT(ucjbDate, 'yyyy-MM'), ucjbSpeed
    ORDER BY month, ucjbSpeed
""", max_rows=500)

# Q15: All Woop jobs by year for total counts
pq('Q15: All Woop jobs by year (all speeds)', """
    SELECT YEAR(ucjbDate) as yr, ucjbSpeed,
           COUNT(*) as cnt, SUM(ucjbAmount) as total_amt,
           AVG(ucjbAmount) as avg_amt
    FROM tucJobArchive
    WHERE ucjbClientCode LIKE '%WOOP%'
      AND ucjbVoid = 0
      AND ucjbDate >= '2017-01-01'
    GROUP BY YEAR(ucjbDate), ucjbSpeed
    ORDER BY yr, cnt DESC
""")

conn.close()
srv.close()
print('\n\nALL QUERIES COMPLETE.', flush=True)
