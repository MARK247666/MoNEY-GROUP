"""每日收盤後抓 證交所(上市)+櫃買中心(上櫃) 收盤價與成交量，更新 data.json。
重點：一定要先確認「資料真正的交易日」，確認不了就不寫入，避免把前一天的價格寫成今天。"""
import json, sys, os, csv, io, re, time, datetime, urllib.request, urllib.parse
SHEET_ID = "1RIUH_M5YA7gcukuH1lPuxNG_jc5LJgnwpn0wcLuw5dA"  # 你的 Google 試算表
FMTQIK = "https://www.twse.com.tw/rwd/en/afterTrading/FMTQIK?response=json"  # 取得最新交易日
TWSE = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"

TWSE_T86 = "https://www.twse.com.tw/rwd/zh/fund/T86?response=json&selectType=ALL&date="
TWSE_MARGN = "https://www.twse.com.tw/rwd/zh/marginTrade/MI_MARGN?response=json&selectType=ALL&date="
TWSE_SBL = "https://www.twse.com.tw/rwd/zh/marginTrade/TWT93U?response=json&date="
TWSE_DAY = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?response=json&date={ym}01&stockNo={c}"
TPEX_3I = "https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&se=EW&t=D&o=json&d="
TPEX_MARGN = "https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/margin_bal_result.php?l=zh-tw&o=json&d="
TPEX_SBL = "https://www.tpex.org.tw/web/stock/margin_trading/margin_sbl/margin_sbl_result.php?l=zh-tw&o=json&d="
TPEX_DAY = "https://www.tpex.org.tw/web/stock/aftertrading/daily_trading_info/st43_result.php?l=zh-tw&o=json&d={roc}&stkno={c}"
TDCC = "https://opendata.tdcc.com.tw/getOD.ashx?id=1-5"
HIST_PER_RUN = 6  # 每輪最多補抓幾個「個股×月份」的歷史收盤價，避免被限流

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


# ---------- 額外資料：三大法人 / 融資融券 / 借券 / 千張大戶 / 歷史收盤 ----------
def roc(d): y, m, dd = d.split("-"); return f"{int(y)-1911}/{m}/{dd}"

def table(j):
    """回傳 (欄位名稱, 資料列)；相容證交所新舊格式與櫃買 aaData/tables"""
    if not isinstance(j, dict): return [], []
    cands = []
    if j.get("tables"): cands += j["tables"]
    cands.append(j)
    named = [t for t in cands if t.get("fields") and re.search("代號|代碼", str(t["fields"][0]))]
    for t in (named or []) + cands:
        rows = t.get("data") or t.get("aaData") or []
        if rows: return t.get("fields") or [], rows
    return [], []

def lot(v):
    n = num(v)
    return None if n is None else round(n / 1000)

def ok_date(j, d):
    x = "".join(c for c in str(j.get("date", "")) if c.isdigit()) if isinstance(j, dict) else ""
    return (not x) or x == d.replace("-", "")

def fidx(fields, test, last=False):
    hit = [i for i, f in enumerate(fields) if test(str(f))]
    return (hit[-1] if last else hit[0]) if hit else None

def ex_twse_3i(d, w):
    j = getj(TWSE_T86 + d.replace("-", ""))
    if not ok_date(j, d): return {}
    fl, rows = table(j)
    if rows: print(f"上市三大法人 {len(rows)} 筆，欄位：{fl}")
    a = fidx(fl, lambda f: "買賣超" in f and ("外陸資" in f or "外資及陸資" in f) and "不含" in f)
    b = fidx(fl, lambda f: f.startswith("投信買賣超"))
    c = fidx(fl, lambda f: f.strip().startswith("自營商買賣超"))
    if None in (a, b, c): 
        if rows: print("[警告] 上市三大法人欄位名稱對不上"); 
        return {}
    return {str(r[0]).strip(): {"11": lot(r[a]), "12": lot(r[b]), "13": lot(r[c])} for r in rows if str(r[0]).strip() in w}

def ex_twse_margin(d, w):
    j = getj(TWSE_MARGN + d.replace("-", ""))
    if not ok_date(j, d): return {}
    fl, rows = table(j)
    if rows: print(f"上市融資融券 {len(rows)} 筆，欄位：{fl}")
    out = {}
    for r in rows:
        c = str(r[0]).strip()
        if c in w and len(r) >= 13:
            mt, my, st = num(r[6]), num(r[5]), num(r[12])
            out[c] = {"7": mt, "8": None if mt is None or my is None else mt - my, "9": st}
    return out

def sbl_pick(fl, r):
    ib = fidx(fl, lambda f: "當日餘額" in f, last=True)
    isell = fidx(fl, lambda f: "當日賣出" in f, last=True)
    if ib is None or isell is None: return None
    return {"17": lot(r[ib]), "18": lot(r[isell])}

def ex_sbl(url, tag):
    def f(d, w):
        j = getj(url + (d.replace("-", "") if tag == "上市" else roc(d)))
        if not ok_date(j, d): return {}
        fl, rows = table(j)
        if rows: print(f"{tag}借券賣出 {len(rows)} 筆，欄位：{fl}")
        out = {}
        for r in rows:
            c = str(r[0]).strip()
            if c in w:
                v = sbl_pick(fl, r)
                if v is None: print(f"[警告] {tag}借券欄位名稱對不上"); return {}
                out[c] = v
        return out
    return f

def ex_tpex_3i(d, w):
    fl, rows = table(getj(TPEX_3I + roc(d)))
    if rows: print(f"上櫃三大法人 {len(rows)} 筆，第一列：{rows[0]}")
    out = {}
    for r in rows:
        c = str(r[0]).strip()
        if c in w and len(r) >= 23:  # 4=外資(不含自營) 13=投信 22=自營商合計
            out[c] = {"11": lot(r[4]), "12": lot(r[13]), "13": lot(r[22])}
    return out

def ex_tpex_margin(d, w):
    fl, rows = table(getj(TPEX_MARGN + roc(d)))
    if rows: print(f"上櫃融資融券 {len(rows)} 筆，第一列：{rows[0]}")
    out = {}
    for r in rows:
        c = str(r[0]).strip()
        if c in w and len(r) >= 15:  # 2=前資餘額 6=資餘額 14=券餘額
            mt, my = num(r[6]), num(r[2])
            out[c] = {"7": mt, "8": None if mt is None or my is None else mt - my, "9": num(r[14])}
    return out

DATASETS = {"上市": [("三大法人", ex_twse_3i), ("融資融券", ex_twse_margin), ("借券", ex_sbl(TWSE_SBL, "上市"))],
            "上櫃": [("三大法人", ex_tpex_3i), ("融資融券", ex_tpex_margin), ("借券", ex_sbl(TPEX_SBL, "上櫃"))]}

def fetch_extras(data, q, watch):
    x, xd = data.setdefault("x", {}), data.setdefault("xd", {})
    dates = {}
    for c, v in q.items():
        if len(v) > 3: dates.setdefault(v[3], v[2])
    for mkt, items in DATASETS.items():
        d = dates.get(mkt)
        if not d: continue
        w = {c for c, v in q.items() if len(v) > 3 and v[3] == mkt}
        for name, fn in items:
            key = f"{mkt}:{name}"
            if key in xd.get(d, []): continue
            try:
                time.sleep(1.5)
                res = fn(d, w)
            except Exception as e:
                print(f"[警告] {key} 抓取失敗：{e}"); continue
            if not res: print(f"{key} {d} 尚無資料（可能還沒公布），下一輪再試"); continue
            for c, vals in res.items():
                x.setdefault(d, {}).setdefault(c, {}).update({k: v for k, v in vals.items() if v is not None})
            xd.setdefault(d, []).append(key)
            print(f"{key} {d}：取得 {len(res)} 檔")
    for old in sorted(x)[:-10]: x.pop(old, None)
    for old in sorted(xd)[:-10]: xd.pop(old, None)

def fetch_tdcc(data, watch):
    """集保戶股權分散表（每週公布）：持股分級 15 = 1,000 張以上"""
    try:
        req = urllib.request.Request(TDCC, headers={"User-Agent": "Mozilla/5.0"})
        txt = urllib.request.urlopen(req, timeout=60).read().decode("utf-8-sig")
    except Exception as e:
        print(f"[警告] 集保大戶資料抓取失敗：{e}"); return
    out, dd = {}, None
    for r in csv.reader(io.StringIO(txt)):
        if len(r) >= 6 and r[2].strip() == "15" and r[1].strip() in watch and num(r[5]) is not None:
            out[r[1].strip()] = num(r[5]) / 100
            dd = sdate(f"{r[0][:4]}-{r[0][4:6]}-{r[0][6:8]}") or dd
    if out: data["w"] = {"d": dd, "v": out}; print(f"千張大戶 {dd}：取得 {len(out)} 檔")
    else: print("[警告] 集保大戶資料沒有解析到任何股票")

def backfill_hist(data, now, budget=HIST_PER_RUN):
    """補抓每檔近 3 個月歷史收盤價，只用來算 20/60 日線"""
    hist, hm = data.setdefault("hist", {}), data.setdefault("hm", {})
    mk = {c: v[3] for c, v in data.get("q", {}).items() if len(v) > 3}
    today = now.strftime("%Y-%m-%d")
    months = []
    y, m = now.year, now.month
    for _ in range(4):
        months.append(f"{y}-{m:02d}"); m -= 1
        if m == 0: y, m = y - 1, 12
    for c, mkt in mk.items():
        for ym in months:
            if budget <= 0: return
            if hm.get(c, {}).get(ym) and (ym != months[0] or hm[c][ym] == today): continue
            try:
                time.sleep(2.5)
                if mkt == "上市":
                    j = getj(TWSE_DAY.format(ym=ym.replace("-", ""), c=c)); rows = table(j)[1]; di, ci = 0, 6
                else:
                    j = getj(TPEX_DAY.format(roc=roc(ym + "-01")[:-3], c=c)); rows = table(j)[1]; di, ci = 0, 6
            except Exception as e:
                print(f"[警告] 歷史價 {c} {ym} 失敗：{e}"); budget -= 1; continue
            budget -= 1
            h = hist.setdefault(c, {})
            for r in rows:
                dt = pdate(str(r[di]).replace("*", "").strip().replace("/", ""))
                cl = num(r[ci])
                if dt and cl: h[dt] = cl
            hm.setdefault(c, {})[ym] = today
            print(f"歷史價 {c} {ym}：{len(rows)} 筆")

def ma_at(closes, d):
    ds = sorted(k for k in closes if k <= d)
    cl = [closes[k] for k in ds]
    return {i: round(sum(cl[-n:]) / n, 2) for i, n in ((21, 5), (22, 20), (23, 60)) if len(cl) >= n}

def getj(url): return get(url)

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
    if now.weekday() >= 5 or now.hour < 14: return False
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
            if c in watch: q[c] = [cl, v, md, name]
    return q

def is_empty(r):
    return not any(v is not None for i, v in enumerate(r) if i >= 3 and i not in (19, 25))

def main(now=None):
    data = json.load(open("data.json", encoding="utf-8"))
    now = now or (datetime.datetime.utcnow() + datetime.timedelta(hours=8))
    if market_due(data, now):
        q = fetch_quotes({s["c"] for s in data["S"]})
        watch = {s["c"] for s in data["S"]}
        if q:
            data["q"], data["qt"] = q, now.replace(microsecond=0).isoformat()
            fetch_extras(data, q, watch)
            if data.get("wt") != now.strftime("%Y-%m-%d"):
                fetch_tdcc(data, watch); data["wt"] = now.strftime("%Y-%m-%d")
        else:
            print("[警告] 這次沒抓到證交所/櫃買資料，沿用上一次的報價")
    else:
        print("本輪只讀試算表（證交所/櫃買資料每 30 分鐘、14:00 後才抓）")
    try: backfill_hist(data, now)
    except Exception as e: print(f"[警告] 補抓歷史價失敗：{e}")
    q = data.get("q", {})
    x, w = data.get("x", {}), data.get("w") or {}
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
            t[0], t[1], t[2] = today, s["c"], s["n"]
            rows.append(t)
        c = s["c"]
        if c in q:
            close, vol, d = q[c][:3]
            idx = next((i for i, r in enumerate(rows) if r[0] == d), None)
            if idx is None:
                t = [None] * 28
                t[0], t[1], t[2] = d, c, s["n"]
                rows.append(t); rows.sort(key=lambda r: r[0])
                idx = next(i for i, r in enumerate(rows) if r[0] == d)
            r = rows[idx]
            if r[3] is None: r[3] = close
            if r[26] is None and vol: r[26] = round(vol / 1000)
            hit += 1
        else: miss.append(c)
        # 歷史收盤（補抓）+ 試算表收盤 → 20/60 日線
        closes = dict(data.get("hist", {}).get(c, {}))
        closes.update({r[0]: r[3] for r in rows if isinstance(r[3], (int, float))})
        for i, r in enumerate(rows):
            if i < len(rows) - 6: continue
            for k, v in x.get(r[0], {}).get(c, {}).items():
                if r[int(k)] is None: r[int(k)] = v
            if isinstance(r[3], (int, float)):
                for k, v in ma_at(closes, r[0]).items():
                    if r[k] is None: r[k] = v
                if not r[25]: r[25] = trend(r)
            if r[19] is None:
                if c in w.get("v", {}) and w.get("d") and r[0] >= w["d"]: r[19] = w["v"][c]
                elif i > 0: r[19] = rows[i - 1][19]
    print(f"試算表讀取成功 {sheet_ok}/{len(data['S'])} 個分頁")
    print(f"交易日 {date}：更新 {hit} 檔；找不到：{miss}")
    if sheet_ok == 0 and hit == 0: sys.exit("試算表與報價都沒有讀到資料")
    if date: data["updated"] = date
    json.dump(data, open("data.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

if __name__ == "__main__":
    main()
