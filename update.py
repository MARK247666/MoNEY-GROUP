"""每日收盤後抓 證交所(上市)+櫃買中心(上櫃) 收盤價與成交量，更新 data.json。"""
import json, sys, datetime, urllib.request
TWSE = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))

def num(x):
    try:
        return float(str(x).replace(",", "").strip())
    except Exception:
        return None

def pick(d, *keys):
    low = {k.lower(): v for k, v in d.items()}
    for k in keys:
        if k.lower() in low:
            return low[k.lower()]

def pdate(s):
    s = "".join(c for c in str(s or "") if c.isdigit())
    try:
        if len(s) == 7: return f"{int(s[:3])+1911}-{s[3:5]}-{s[5:7]}"
        if len(s) == 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    except Exception:
        pass

def collect():
    q, dates = {}, []
    for name, url in (("上市", TWSE), ("上櫃", TPEX)):
        try:
            rows = get(url)
        except Exception as e:
            print(f"[警告] {name} 抓取失敗：{e}"); continue
        if rows: print(f"{name} 欄位：{list(rows[0].keys())}")
        for r in rows:
            code = pick(r, "Code", "SecuritiesCompanyCode")
            close = num(pick(r, "ClosingPrice", "Close"))
            vol = num(pick(r, "TradeVolume", "TradingShares", "TradingVolume"))
            if code and close:
                q[str(code).strip()] = (close, vol)
            d = pdate(pick(r, "Date"))
            if d: dates.append(d)
    return q, (max(dates) if dates else None)

def ma(rows):
    cl = [r[3] for r in rows if isinstance(r[3], (int, float))]
    return {i: round(sum(cl[-n:]) / n, 2) for i, n in ((21, 5), (22, 20), (23, 60)) if len(cl) >= n}

def trend(r):
    a, b, c, p = r[21], r[22], r[23], r[3]
    if None in (a, b, c): return None
    if a < b < c: return "空頭排列(5<20<60)"
    if a > b > c: return "多頭排列(5>20>60)"
    return "站上月線轉強" if p > b else "跌破月線整理"

def main():
    data = json.load(open("data.json", encoding="utf-8"))
    q, date = collect()
    date = date or (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y-%m-%d")
    hit, miss = 0, []
    for s in data["S"]:
        if s["c"] not in q: miss.append(s["c"]); continue
        close, vol = q[s["c"]]
        rows = s["r"]
        if rows[-1][0] > date: continue
        if rows[-1][0] != date:
            new = [None] * 28
            new[0], new[1], new[2] = date, s["c"], s["n"]
            new[19] = rows[-1][19]  # 千張大戶比例：週更新，沿用上一筆
            rows.append(new)
        r = rows[-1]
        r[3] = close
        r[26] = round(vol / 1000) if vol else r[26]
        for i, v in ma(rows).items(): r[i] = v
        r[25] = trend(r) or r[25]
        s["r"] = rows[-30:] if len(rows) > 90 else rows
        hit += 1
    print(f"資料日期 {date}：更新 {hit} 檔；找不到：{miss}")
    if hit == 0:
        sys.exit("沒有任何股票被更新（可能休市或資料來源格式改變）")
    data["updated"] = date
    json.dump(data, open("data.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

if __name__ == "__main__":
    main()
