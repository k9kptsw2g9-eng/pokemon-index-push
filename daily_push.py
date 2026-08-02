import os
import sys
import requests
import statistics

# 从环境变量读取 PushPlus Token，避免直接写在代码里
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN")
if not PUSHPLUS_TOKEN:
    print("错误：请设置环境变量 PUSHPLUS_TOKEN")
    sys.exit(1)

INDEX_API = "https://api.pokeca-chart.com/php/get-index-chart-data.php?mode=cache&cache_name=index_2"
PUSH_API = "http://www.pushplus.plus/send"


def fetch_index_data():
    """抓取 PSA10 指数原始数据"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://pokeca-chart.com/",
    }
    resp = requests.get(INDEX_API, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    data.sort(key=lambda x: x["date"])
    return data


def compute_metrics(data):
    """计算最新价、20 日均价、布林上下轨、成交量等"""
    latest = data[-1]
    prev = data[-2]

    window = data[-20:]
    prices = [d["price"] for d in window]
    volumes = [d["volume"] for d in window]

    sma20 = sum(prices) / len(prices)
    std20 = statistics.stdev(prices)
    upper = sma20 + 2 * std20
    lower = sma20 - 2 * std20
    avg_vol = sum(volumes) / len(volumes)

    change = latest["price"] - prev["price"]
    change_pct = change / prev["price"] * 100

    # 月度、年度涨跌（按页面口径：30 天、252 个交易日近似）
    month_start = data[-31] if len(data) >= 31 else data[0]
    year_start = data[-252] if len(data) >= 252 else data[0]
    month_change_pct = (latest["price"] - month_start["price"]) / month_start["price"] * 100
    year_change_pct = (latest["price"] - year_start["price"]) / year_start["price"] * 100

    return {
        "date": latest["date"],
        "price": latest["price"],
        "volume": latest["volume"],
        "prev_price": prev["price"],
        "change": change,
        "change_pct": change_pct,
        "sma20": sma20,
        "boll_upper": upper,
        "boll_lower": lower,
        "avg_vol": avg_vol,
        "month_change_pct": month_change_pct,
        "year_change_pct": year_change_pct,
    }


def build_report(m):
    """生成微信推送文案"""
    report = (
        f"📊 宝可梦指数日报（{m['date']}）\n\n"
        f"最新价：{m['price']:,} 日元\n"
        f"前日涨跌：{m['change']:+,.0f} 日元（{m['change_pct']:+.2f}%）\n"
        f"月度涨跌：{m['month_change_pct']:+.2f}%\n"
        f"年度涨跌：{m['year_change_pct']:+.2f}%\n\n"
        f"技术指标（4 根线）：\n"
        f"• 最新价：{m['price']:,} 日元\n"
        f"• 20 日均价：{m['sma20']:,.0f} 日元\n"
        f"• 布林上轨：{m['boll_upper']:,.0f} 日元\n"
        f"• 布林下轨：{m['boll_lower']:,.0f} 日元\n\n"
        f"成交量：{m['volume']} 件（20 日均量 {m['avg_vol']:.0f} 件）\n\n"
    )

    if m["price"] > m["boll_upper"]:
        report += (
            "📈 短线判断：价格突破布林上轨，处于短期超买区，"
            "追涨风险较大。\n"
            "💡 操作建议：已有仓位可继续持有但建议分批止盈；"
            "新仓等待回调至 20 日均价附近再考虑建仓。"
        )
    elif m["price"] < m["boll_lower"]:
        report += (
            "📉 短线判断：价格跌破布林下轨，短期可能存在超跌反弹机会。\n"
            "💡 操作建议：可小仓位试探性建仓，跌破下轨后若持续走弱则止损。"
        )
    else:
        report += (
            "➡️ 短线判断：价格在布林带内部运行，趋势未出现极端偏离。\n"
            "💡 操作建议：按原有趋势持有，靠近上轨减仓，靠近下轨加仓。"
        )

    return report


def push_to_wechat(title, content):
    """调用 PushPlus 推送到微信"""
    payload = {
        "token": PUSHPLUS_TOKEN,
        "title": title,
        "content": content,
        "template": "txt",
    }
    resp = requests.post(PUSH_API, data=payload, timeout=30)
    resp.raise_for_status()
    print("推送成功：", resp.text)


def main():
    data = fetch_index_data()
    metrics = compute_metrics(data)
    report = build_report(metrics)
    print(report)
    push_to_wechat("宝可梦指数日报", report)


if __name__ == "__main__":
    main()
