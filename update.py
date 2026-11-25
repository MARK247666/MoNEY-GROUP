"""每日收盤後抓 證交所(上市)+櫃買中心(上櫃) 收盤價與成交量，更新 data.json。
重點：一定要先確認「資料真正的交易日」，確認不了就不寫入，避免把前一天的價格寫成今天。"""
import json, sys, os, csv, io, re, datetime, urllib.request, urllib.parse
SHEET_ID = "1RIUH_M5YA7gcukuH1lPuxNG_jc5LJgnwpn0wcLuw5dA"  # 你的 Google 試算表
FMTQIK = "https://www.twse.com.tw/rwd/en/afterTrading/FMTQIK?response=json"  # 取得最新交易日
TWSE = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))

def num(x):
    try: return float(str(x).replace(",", "").strip())
    except Exception: return None

def pick(d, *keys):
    low = {k.lower(): v for k, v in d.items()}
    for k in keys:
        if k.lower() in low: return low[k.lower()]

def pdate(s):
    s = "".join(c for c in str(s or "") if c.isdigit())
    if len(s) == 7: return f"{int(s[:3])+1911}-{s[3:5]}-{s[5:7]}"
    if len(s) == 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"

def latest_trading_date():
    try:
        d = pdate(get(FMTQIK)["data"][-1][0])
        if d: return d
    except Exception as e:
        print(f"[警告] 取得最新交易日失敗：{e}")

def fetch_market(name, url):
    try: rows = get(url)
    except Exception as e:
        print(f"[警告] {name} 抓取失敗：{e}"); return {}, None
    if not rows: print(f"[警告] {name} 沒有資料"); return {}, None
    print(f"{name} 筆數 {len(rows)}，欄位：{list(rows[0].keys())}")
    q, dates = {}, set()
    for r in rows:
        code = pick(r, "Code", "SecuritiesCompanyCode")
        close = num(pick(r, "ClosingPrice", "Close"))
        vol = num(pick(r, "TradeVolume", "TradingShares", "TradingVolume"))
        if code and close: q[str(code).strip()] = (close, vol)
        d = pdate(pick(r, "Date"))
        if d: dates.add(d)
    return q, (max(dates) if dates else None)

def sdate(s):
    s = str(s).strip()
    m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)
    if m: return f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}"
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m: return f"{m[3]}-{int(m[1]):02d}-{int(m[2]):02d}"

def cell(c, i):
    c = c.strip()
    if c == "": return None
    if i in (1, 2, 25, 27): return c
    if c.endswith("%") and num(c[:-1]) is not None: return num(c[:-1]) / 100
    return num(c) if num(c) is not None else c

def parse_csv(txt):
    rows = []
    for line in csv.reader(io.StringIO(txt)):
        d = sdate(line[0]) if line else None
        if not d: continue
        line = (line + [""] * 28)[:28]
        row = [d] + [cell(c, i + 1) for i, c in enumerate(line[1:])]
        for i in (5, 6):  # 維持率不可能是 0，試算表公式空白時會顯示 0，當成空白
            if row[i] == 0: row[i] = None
        rows.append(row)
    return rows

def sheet_rows(tab):
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&headers=0&sheet=" + urllib.parse.quote(tab)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return parse_csv(urllib.request.urlopen(req, timeout=40).read().decode("utf-8"))

def ma(rows):
    cl = [r[3] for r in rows if isinstance(r[3], (int, float))]
    return {i: round(sum(cl[-n:]) / n, 2) for i, n in ((21, 5), (22, 20), (23, 60)) if len(cl) >= n}

def trend(r):
    a, b, c, p = r[21], r[22], r[23], r[3]
    if None in (a, b, c): return None
    if a < b < c: return "空頭排列(5<20<60)"
    if a > b > c: return "多頭排列(5>20>60)"
    return "站上月線轉強" if p > b else "跌破月線整理"

def market_due(data, now):
    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch": return True
    if now.weekday() >= 5 or now.hour < 15: return False
    try: last = datetime.datetime.fromisoformat(data.get("qt", ""))
    except Exception: return True
    return (now - last).total_seconds() >= 28 * 60

def fetch_quotes(watch):
    q, fallback = {}, None
    for name, url in (("上市", TWSE), ("上櫃", TPEX)):
        mq, md = fetch_market(name, url)
        if not md:
            fallback = fallback or latest_trading_date()
            md = fallback
        if not md:
            print(f"[略過] {name} 無法確認資料日期"); continue
        print(f"{name} 資料日期：{md}")
        for c, (cl, v) in mq.items():
            if c in watch: q[c] = [cl, v, md]
    return q

def is_empty(r):
    return not any(v is not None for i, v in enumerate(r) if i >= 3 and i not in (19, 25))

def main(now=None):
    data = json.load(open("data.json", encoding="utf-8"))
    now = now or (datetime.datetime.utcnow() + datetime.timedelta(hours=8))
    if market_due(data, now):
        q = fetch_quotes({s["c"] for s in data["S"]})
        if q:
            data["q"], data["qt"] = q, now.replace(microsecond=0).isoformat()
        else:
            print("[警告] 這次沒抓到證交所/櫃買資料，沿用上一次的報價")
    else:
        print("本輪只讀試算表（證交所/櫃買資料每 30 分鐘、15:00 後才抓）")
    q = data.get("q", {})
    date = max((v[2] for v in q.values()), default=None)
    hit, miss, sheet_ok = 0, [], 0
    for s in data["S"]:
        try:
            sr = sheet_rows(s["tab"])
            if sr: s["r"] = sr; sheet_ok += 1
            else: print(f"[警告] {s['tab']} 讀不到資料列，沿用舊資料（請確認試算表已開「知道連結的人可檢視」）")
        except Exception as e:
            print(f"[警告] 讀取試算表分頁 {s['tab']} 失敗：{e}")
        rows, today = s["r"], now.strftime("%Y-%m-%d")
        rows[:] = [r for r in rows if not (r[0] < today and is_empty(r))]  # 休市日留下的空白列
        if now.weekday() < 5 and now.hour >= 8 and rows[-1][0] < today:  # 先建立今天的空白列
            t = [None] * 28
            t[0], t[1], t[2], t[19] = today, s["c"], s["n"], rows[-1][19]
            rows.append(t)
        if s["c"] not in q: miss.append(s["c"]); continue
        close, vol, d = q[s["c"]]
        idx = next((i for i, r in enumerate(rows) if r[0] == d), None)
        if idx is None:
            t = [None] * 28
            t[0], t[1], t[2] = d, s["c"], s["n"]
            rows.append(t); rows.sort(key=lambda r: r[0])
            idx = next(i for i, r in enumerate(rows) if r[0] == d)
        r = rows[idx]
        if r[3] is None: r[3] = close
        if r[26] is None and vol: r[26] = round(vol / 1000)
        if r[19] is None and idx > 0: r[19] = rows[idx - 1][19]
        for i, v in ma(rows[:idx + 1]).items():
            if r[i] is None: r[i] = v
        if not r[25]: r[25] = trend(r)
        hit += 1
    print(f"試算表讀取成功 {sheet_ok}/{len(data['S'])} 個分頁")
    print(f"交易日 {date}：更新 {hit} 檔；找不到：{miss}")
    if sheet_ok == 0 and hit == 0: sys.exit("試算表與報價都沒有讀到資料")
    if date: data["updated"] = date
    json.dump(data, open("data.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

if __name__ == "__main__":
    main()
