import os
import statistics
import sys
from datetime import datetime

import requests

# 从环境变量读取 PushPlus Token，避免直接写在代码里
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN")

INDEX_API = "https://api.pokeca-chart.com/php/get-index-chart-data.php?mode=cache&cache_name=index_2"
PUSH_API = "http://www.pushplus.plus/send"
QUICKCHART_API = "https://quickchart.io/chart/create"


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


def compute_rsi(prices, period=14):
    """计算 RSI 指标（Wilder 平滑）"""
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    if len(gains) < period:
        return 50.0

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def compute_metrics(data):
    """计算最新价、20 日均价、布林上下轨、成交量、RSI 等"""
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

    # 布林带位置百分比，>100 表示突破上轨，<0 表示跌破下轨
    boll_pct = (latest["price"] - lower) / (upper - lower) * 100 if upper != lower else 50

    # 月度、年度涨跌
    month_start = data[-31] if len(data) >= 31 else data[0]
    year_start = data[-252] if len(data) >= 252 else data[0]
    month_change_pct = (latest["price"] - month_start["price"]) / month_start["price"] * 100
    year_change_pct = (latest["price"] - year_start["price"]) / year_start["price"] * 100

    # RSI
    all_prices = [d["price"] for d in data]
    rsi = compute_rsi(all_prices, 14)

    # 20 日均线斜率（近 5 日 vs 再前 5 日）
    if len(prices) >= 10:
        sma_recent = sum(prices[-5:]) / 5
        sma_before = sum(prices[-10:-5]) / 5
        sma_slope = (sma_recent - sma_before) / sma_before * 100
    else:
        sma_slope = 0

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
        "rsi": rsi,
        "boll_pct": boll_pct,
        "sma_slope": sma_slope,
    }


def generate_chart_url(data):
    """通过 QuickChart 生成走势图，返回图片外链"""
    chart_data = data[-60:]
    labels = [d["date"][5:] for d in chart_data]  # mm-dd
    prices = [d["price"] for d in chart_data]
    volumes = [d["volume"] for d in chart_data]

    sma_line = []
    upper_line = []
    lower_line = []
    for i in range(len(chart_data)):
        start_idx = max(0, i - 19)
        window_prices = [d["price"] for d in chart_data[start_idx : i + 1]]
        sma = sum(window_prices) / len(window_prices)
        std = statistics.stdev(window_prices) if len(window_prices) > 1 else 0
        sma_line.append(round(sma, 1))
        upper_line.append(round(sma + 2 * std, 1))
        lower_line.append(round(sma - 2 * std, 1))

    # 成交量颜色：涨绿跌红
    vol_colors = []
    for i in range(len(prices)):
        if i == 0 or prices[i] >= prices[i - 1]:
            vol_colors.append("rgba(63,185,80,0.6)")
        else:
            vol_colors.append("rgba(248,81,73,0.6)")

    config = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": "Price",
                    "data": prices,
                    "borderColor": "#58a6ff",
                    "backgroundColor": "#58a6ff",
                    "fill": False,
                    "pointRadius": 0,
                    "yAxisID": "y",
                },
                {
                    "label": "SMA20",
                    "data": sma_line,
                    "borderColor": "#d2a8ff",
                    "backgroundColor": "#d2a8ff",
                    "fill": False,
                    "pointRadius": 0,
                    "yAxisID": "y",
                },
                {
                    "label": "BB Upper",
                    "data": upper_line,
                    "borderColor": "#3fb950",
                    "backgroundColor": "#3fb950",
                    "fill": False,
                    "pointRadius": 0,
                    "borderDash": [5, 5],
                    "yAxisID": "y",
                },
                {
                    "label": "BB Lower",
                    "data": lower_line,
                    "borderColor": "#3fb950",
                    "backgroundColor": "#3fb950",
                    "fill": False,
                    "pointRadius": 0,
                    "borderDash": [5, 5],
                    "yAxisID": "y",
                },
                {
                    "label": "Volume",
                    "data": volumes,
                    "type": "bar",
                    "backgroundColor": vol_colors,
                    "yAxisID": "y-volume",
                },
            ],
        },
        "options": {
            "title": {
                "display": True,
                "text": f"PSA10 Index Chart ({chart_data[0]['date']} ~ {chart_data[-1]['date']})",
                "fontColor": "#c9d1d9",
            },
            "legend": {"labels": {"fontColor": "#c9d1d9"}},
            "scales": {
                "xAxes": [{"ticks": {"fontColor": "#c9d1d9"}, "gridLines": {"color": "#30363d"}}],
                "yAxes": [
                    {
                        "id": "y",
                        "position": "left",
                        "ticks": {"fontColor": "#c9d1d9"},
                        "gridLines": {"color": "#30363d"},
                    },
                    {
                        "id": "y-volume",
                        "position": "right",
                        "ticks": {"fontColor": "#c9d1d9"},
                        "gridLines": {"drawOnChartArea": False},
                    },
                ],
            },
        },
    }

    resp = requests.post(
        QUICKCHART_API,
        json={"chart": config, "width": 800, "height": 450, "backgroundColor": "#0d1117"},
        timeout=30,
    )
    resp.raise_for_status()
    result = resp.json()
    return result["url"]


def build_report(m):
    """生成微信推送文案，包含更详细的短线判断与操作建议"""
    report = (
        f"<h3>📊 宝可梦指数日报（{m['date']}）</h3>"
        f"<p><b>最新价：</b>{m['price']:,} 日元</p>"
        f"<p><b>前日涨跌：</b>{m['change']:+,.0f} 日元（{m['change_pct']:+.2f}%）</p>"
        f"<p><b>月度涨跌：</b>{m['month_change_pct']:+.2f}%</p>"
        f"<p><b>年度涨跌：</b>{m['year_change_pct']:+.2f}%</p>"
        f"<hr/>"
        f"<p><b>技术指标（4 根线）：</b></p>"
        f"<ul>"
        f"<li>最新价：{m['price']:,} 日元</li>"
        f"<li>20 日均价：{m['sma20']:,.0f} 日元</li>"
        f"<li>布林上轨：{m['boll_upper']:,.0f} 日元</li>"
        f"<li>布林下轨：{m['boll_lower']:,.0f} 日元</li>"
        f"</ul>"
        f"<p><b>成交量：</b>{m['volume']} 件（20 日均量 {m['avg_vol']:.0f} 件）</p>"
        f"<p><b>RSI(14)：</b>{m['rsi']:.1f}</p>"
        f"<p><b>布林带位置：</b>{m['boll_pct']:.1f}%（100% 为中轨，>100 偏上轨，<0 偏下轨）</p>"
        f"<hr/>"
    )

    # 短线判断
    judgment = []
    if m["price"] > m["boll_upper"]:
        judgment.append(
            f"价格（{m['price']:,}）突破布林上轨（{m['boll_upper']:,.0f}），"
            "处于短期超买区。"
        )
    elif m["price"] < m["boll_lower"]:
        judgment.append(
            f"价格跌破布林下轨（{m['boll_lower']:,.0f}），短期超卖，存在反弹可能。"
        )
    else:
        judgment.append("价格在布林带内部运行，未出现极端偏离。")

    if m["rsi"] > 70:
        judgment.append(f"RSI 为 {m['rsi']:.1f}，进入超买区间（>70），追涨风险大。")
    elif m["rsi"] < 30:
        judgment.append(f"RSI 为 {m['rsi']:.1f}，进入超卖区间（<30），短线或有反弹。")
    else:
        judgment.append(f"RSI 为 {m['rsi']:.1f}，处于中性区域。")

    if m["volume"] > m["avg_vol"] * 1.2:
        judgment.append(
            f"当日成交量 {m['volume']} 件，高于 20 日均量 {m['avg_vol']:.0f} 件，"
            "放量上涨/下跌确认信号。"
        )
    elif m["volume"] < m["avg_vol"] * 0.8:
        judgment.append(
            f"当日成交量 {m['volume']} 件，低于 20 日均量 {m['avg_vol']:.0f} 件，"
            "量能萎缩，当前价格波动可能缺乏持续动能。"
        )
    else:
        judgment.append(f"成交量 {m['volume']} 件，与 20 日均量 {m['avg_vol']:.0f} 件基本持平。")

    if m["sma_slope"] > 0:
        judgment.append(f"20 日均线斜率向上（+{m['sma_slope']:.2f}%），中期趋势偏多。")
    else:
        judgment.append(f"20 日均线斜率向下（{m['sma_slope']:.2f}%），中期趋势偏空。")

    report += "<p><b>📈 短线判断：</b></p><ul>"
    for item in judgment:
        report += f"<li>{item}</li>"
    report += "</ul>"

    # 操作建议
    report += "<p><b>💡 操作建议：</b></p><ul>"
    if m["price"] > m["boll_upper"] and m["rsi"] > 70:
        report += (
            "<li><b>已有仓位：</b>不建议清仓，但建议在上轨附近分批止盈。"
            f"例如价格每涨 {max(500, int((m['boll_upper'] - m['sma20']) * 0.3)):,} 日元，减仓 10%-20%；"
            f"若收盘跌破 20 日均价 {m['sma20']:,.0f}，再减仓 30%。</li>"
            "<li><b>没有仓位：</b>当前处于超买区，不要追涨建仓。"
            f"可等待价格回踩 20 日均价 {m['sma20']:,.0f} 附近，再考虑小仓位试多。</li>"
        )
    elif m["price"] < m["boll_lower"]:
        report += (
            "<li><b>已有仓位：</b>若已持仓且被套，不建议恐慌清仓，可等反弹至中轨再减仓。</li>"
            "<li><b>没有仓位：</b>可小仓位左侧试多，止损设在布林下轨下方 2%-3%。</li>"
        )
    else:
        report += (
            f"<li><b>已有仓位：</b>趋势未坏，继续持有；若放量跌破 {m['sma20']:,.0f} 再考虑减仓。</li>"
            f"<li><b>没有仓位：</b>可在 {m['sma20']:,.0f} 附近分批建仓，跌破 {m['boll_lower']:,.0f} 止损。</li>"
        )

    report += (
        f"<li><b>关键观察位：</b>上方压力 {m['boll_upper']:,.0f}，下方支撑 {m['sma20']:,.0f}，"
        f"强支撑 {m['boll_lower']:,.0f}。</li>"
        "</ul>"
    )

    return report


def push_to_wechat(title, content, image_url=None):
    """调用 PushPlus 推送到微信，使用 HTML 模板以便显示图片"""
    if image_url:
        content += f"<p><b>📉 走势图：</b></p><img src='{image_url}' style='max-width:100%;'/>"

    payload = {
        "token": PUSHPLUS_TOKEN,
        "title": title,
        "content": content,
        "template": "html",
    }
    resp = requests.post(PUSH_API, data=payload, timeout=30)
    resp.raise_for_status()
    print("推送结果：", resp.text)


def main():
    if not PUSHPLUS_TOKEN:
        print("错误：请设置环境变量 PUSHPLUS_TOKEN")
        sys.exit(1)

    data = fetch_index_data()
    metrics = compute_metrics(data)
    image_url = generate_chart_url(data)
    report = build_report(metrics)
    push_to_wechat("宝可梦指数日报", report, image_url)


if __name__ == "__main__":
    main()
