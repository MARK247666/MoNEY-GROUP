"""每日收盤後抓 證交所(上市)+櫃買中心(上櫃) 收盤價與成交量，更新 data.json。
重點：一定要先確認「資料真正的交易日」，確認不了就不寫入，避免把前一天的價格寫成今天。"""
import json, sys, urllib.request
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
    date = latest_trading_date()
    q = {}
    for name, url in (("上市", TWSE), ("上櫃", TPEX)):
        mq, md = fetch_market(name, url)
        date = date or md
        if not date: continue
        if md and md != date:
            print(f"[略過] {name} 資料日期 {md} 與最新交易日 {date} 不同"); continue
        q.update(mq)
    if not date: sys.exit("無法確認交易日，未更新任何資料")
    print("最新交易日：", date)
    hit, miss = 0, []
    for s in data["S"]:
        if s["c"] not in q: miss.append(s["c"]); continue
        close, vol = q[s["c"]]
        rows = s["r"]
        if rows[-1][0] > date: continue
        if rows[-1][0] != date:
            new = [None] * 28
            new[0], new[1], new[2] = date, s["c"], s["n"]
            new[19] = rows[-1][19]
            rows.append(new)
        r = rows[-1]
        r[3] = close
        if vol: r[26] = round(vol / 1000)
        for i, v in ma(rows).items(): r[i] = v
        r[25] = trend(r) or r[25]
        hit += 1
    print(f"交易日 {date}：更新 {hit} 檔；找不到：{miss}")
    if hit == 0: sys.exit("沒有任何股票被更新")
    data["updated"] = date
    json.dump(data, open("data.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

if __name__ == "__main__":
    main()
