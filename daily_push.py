import base64
import os
import statistics
import subprocess
import sys
from datetime import datetime, timedelta

import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import requests

matplotlib.use("Agg")

# 从环境变量读取 Token，避免直接写在代码里
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "k9kptsw2g9-eng/pokemon-index-push")

INDEX_API = "https://api.pokeca-chart.com/php/get-index-chart-data.php?mode=cache&cache_name=index_2"
PUSH_API = "http://www.pushplus.plus/send"
CHART_FILE = "chart.png"


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


def generate_chart(data, metrics):
    """生成指数走势图并保存为 chart.png"""
    # 只取最近 120 个交易日画图
    chart_data = data[-120:]
    dates = [datetime.strptime(d["date"], "%Y-%m-%d") for d in chart_data]
    prices = [d["price"] for d in chart_data]
    volumes = [d["volume"] for d in chart_data]

    # 计算对应日期的 SMA20、布林上下轨
    sma_line = []
    upper_line = []
    lower_line = []
    for i in range(len(chart_data)):
        start_idx = i - 19
        if start_idx < 0:
            window_prices = [d["price"] for d in chart_data[: i + 1]]
        else:
            window_prices = [d["price"] for d in chart_data[start_idx : i + 1]]
        sma = sum(window_prices) / len(window_prices)
        std = statistics.stdev(window_prices) if len(window_prices) > 1 else 0
        sma_line.append(sma)
        upper_line.append(sma + 2 * std)
        lower_line.append(sma - 2 * std)

    plt.style.use("dark_background")
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(10, 6), gridspec_kw={"height_ratios": [3, 1]}, sharex=True
    )
    fig.patch.set_facecolor("#0d1117")
    ax1.set_facecolor("#0d1117")
    ax2.set_facecolor("#0d1117")

    # 价格与均线
    ax1.plot(dates, prices, color="#58a6ff", linewidth=1.5, label="Price")
    ax1.plot(dates, sma_line, color="#d2a8ff", linewidth=1.2, label="SMA20")
    ax1.fill_between(
        dates, upper_line, lower_line, color="#238636", alpha=0.15, label="Bollinger Band"
    )
    ax1.plot(dates, upper_line, color="#3fb950", linewidth=0.8, linestyle="--")
    ax1.plot(dates, lower_line, color="#3fb950", linewidth=0.8, linestyle="--")

    # 标注最新价
    ax1.annotate(
        f"{metrics['price']:,}",
        xy=(dates[-1], prices[-1]),
        xytext=(10, 0),
        textcoords="offset points",
        color="white",
        fontsize=9,
    )

    ax1.set_title(f"PSA10 Index Chart ({chart_data[0]['date']} ~ {chart_data[-1]['date']})")
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(True, alpha=0.2)

    # 成交量
    colors = ["#3fb950" if prices[i] >= prices[i - 1] else "#f85149" for i in range(len(prices))]
    colors[0] = "#3fb950"
    ax2.bar(dates, volumes, color=colors, alpha=0.6, width=0.8)
    ax2.set_ylabel("Volume")
    ax2.grid(True, alpha=0.2)

    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(CHART_FILE, dpi=150, facecolor="#0d1117")
    plt.close()
    print(f"图表已保存：{CHART_FILE}")


def commit_chart_to_repo():
    """在 GitHub Actions 中把 chart.png 提交回仓库，以便推送中使用图片外链"""
    if not GITHUB_TOKEN or not GITHUB_REPOSITORY:
        print("未检测到 GITHUB_TOKEN，跳过图片提交")
        return

    try:
        remote = f"https://x-access-token:{GITHUB_TOKEN}@github.com/{GITHUB_REPOSITORY}.git"
        subprocess.run(["git", "config", "user.email", "action@github.com"], check=True)
        subprocess.run(["git", "config", "user.name", "GitHub Action"], check=True)
        subprocess.run(["git", "remote", "set-url", "origin", remote], check=True)
        subprocess.run(["git", "add", CHART_FILE], check=True)
        subprocess.run(
            ["git", "commit", "-m", f"Update chart {datetime.now().strftime('%Y-%m-%d %H:%M')}"],
            check=False,
        )
        subprocess.run(["git", "push"], check=True)
        print("图表已提交到仓库")
    except subprocess.CalledProcessError as e:
        print(f"图表提交失败：{e}")


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
        judgment.append(f"当日成交量 {m['volume']} 件，高于 20 日均量 {m['avg_vol']:.0f} 件，放量上涨/下跌确认信号。")
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
    generate_chart(data, metrics)

    # 先提交图片，确保 PushPlus 发送时图片外链可用
    commit_chart_to_repo()

    report = build_report(metrics)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    image_url = f"https://raw.githubusercontent.com/{GITHUB_REPOSITORY}/main/{CHART_FILE}?v={ts}"
    push_to_wechat("宝可梦指数日报", report, image_url)


if __name__ == "__main__":
    main()
