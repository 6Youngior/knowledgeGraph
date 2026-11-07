"""Export presentation-size scientific figures from the delivered market cache."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

from graph_store import GraphStore
from market import MarketData


ROOT = Path(__file__).resolve().parents[1]


def generate():
    font = Path("C:/Windows/Fonts/msyh.ttc")
    if font.exists():
        font_manager.fontManager.addfont(str(font))
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(font)).get_name()
    plt.rcParams.update({"axes.unicode_minus": False, "font.size": 12, "pdf.fonttype": 42,
                         "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
                         "axes.edgecolor": "#cbd5e1", "xtick.color": "#64748b", "ytick.color": "#64748b"})
    store = GraphStore(ROOT / "data", persist=False)
    window = MarketData(ROOT / "data").event_window("02513.HK", store.event("event:glm5-release"))
    prices = [p for p in window["prices"] if -3 <= p["relative_day"] <= 4]
    fig, ax = plt.subplots(figsize=(9.3, 4.8), layout="constrained")
    fig.set_facecolor("white")
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#e8edf3", linewidth=.9)
    ax.axhline(100, color="#cbd5e1", lw=1)
    ax.axvline(0, color="#8296ae", lw=1.1, ls=(0, (4, 4)))
    x = [p["relative_day"] for p in prices]
    ax.plot(x, [p["normalized"] for p in prices], color="#2563eb", lw=2.8, marker="o", ms=6,
            label="智谱 · 02513.HK")
    ax.plot(x, [p["benchmark_normalized"] for p in prices], color="#0f8c83", lw=2.1, marker="o", ms=4.5,
            label="恒生指数 · 同窗口基准")
    labels = [("T0" if p["relative_day"] == 0 else f"T{p['relative_day']:+}") + "\n" + p["date"][5:]
              for p in prices]
    ax.set_xticks(x, labels, fontsize=10)
    ax.tick_params(axis="both", length=0, pad=8)
    ax.set_ylabel("收盘价归一化 · T−1 = 100", color="#334155", labelpad=12)
    ax.set_xlim(x[0] - .25, x[-1] + 1.3)
    ax.set_ylim(min(p["normalized"] for p in prices) * .94, max(p["normalized"] for p in prices) * 1.13)
    ax.legend(loc="upper left", frameon=False, ncol=2, fontsize=11)
    endpoint = prices[-1]
    ax.annotate(f"5日 {window['returns']['5']:+.2%}", (endpoint["relative_day"], endpoint["normalized"]),
                xytext=(12, 0), textcoords="offset points", va="center", color="#2563eb", fontweight="bold", fontsize=12)
    ax.annotate(f"{window['benchmark_returns']['5']:+.2%}", (endpoint["relative_day"], endpoint["benchmark_normalized"]),
                xytext=(12, -2), textcoords="offset points", va="center", color="#0f8c83", fontsize=12)
    out = ROOT / "docs" / "presentation" / "generated"
    out.mkdir(exist_ok=True, parents=True)
    fig.savefig(out / "market_comparison.pdf", facecolor="white")
    fig.savefig(out / "market_comparison.png", dpi=220, facecolor="white")
    plt.close(fig)
    # A wide, presentation-specific comparison keeps labels readable when the
    # figure occupies a complete Beamer content area.
    ali = MarketData(ROOT / "data").event_window("09988.HK", store.event("event:glm5-release"))
    ali_by_date = {p["date"]: p["normalized"] for p in ali["prices"]}
    fig, ax = plt.subplots(figsize=(7.1, 2.2), layout="constrained")
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#e8edf3", linewidth=.8)
    ax.axhline(100, color="#cbd5e1", lw=.9)
    ax.axvline(0, color="#94a3b8", lw=1, ls=(0, (4, 4)))
    ax.plot(x, [p["normalized"] for p in prices], color="#2563eb", lw=2.3, marker="o", ms=4.5,
            label="智谱 · 直接研发")
    ax.plot(x, [ali_by_date.get(p["date"]) for p in prices], color="#b47a19", lw=1.8, marker="o", ms=3.5,
            label="阿里巴巴 · 云接入")
    ax.plot(x, [p["benchmark_normalized"] for p in prices], color="#0f8c83", lw=1.6, ls="--", label="恒生指数")
    selected = [p for p in prices if p["relative_day"] in {-3, -1, 0, 2, 4}]
    ax.set_xticks([p["relative_day"] for p in selected],
                  [("T0" if p["relative_day"] == 0 else f"T{p['relative_day']:+}") + "\n" + p["date"][5:] for p in selected], fontsize=12.5)
    ax.set_yticks([80, 100, 140, 180])
    ax.tick_params(axis="both", length=0, pad=5, labelsize=12.5)
    ax.set_ylabel("T−1 收盘 = 100", fontsize=13.5, color="#475569", labelpad=8)
    ax.set_xlim(x[0] - .25, x[-1] + 1.5)
    ax.set_ylim(72, 204)
    ax.legend(loc="upper left", frameon=False, ncol=3, fontsize=12.5, handlelength=1.5, columnspacing=1.0)
    for y, value, color, shift in [
        (endpoint["normalized"], window["returns"]["5"], "#2563eb", 0),
        (ali_by_date[endpoint["date"]], ali["returns"]["5"], "#b47a19", -8),
        (endpoint["benchmark_normalized"], window["benchmark_returns"]["5"], "#0f8c83", 7)]:
        ax.annotate(f"{value:+.2%}", (4, y), xytext=(9, shift), textcoords="offset points",
                    va="center", color=color, fontsize=14.0, fontweight="bold")
    fig.savefig(out / "market_roles.pdf", facecolor="white")
    fig.savefig(out / "market_roles.png", dpi=240, facecolor="white")
    plt.close(fig)
    print("Exported market_comparison and market_roles figures from real cached observations")


if __name__ == "__main__":
    generate()
