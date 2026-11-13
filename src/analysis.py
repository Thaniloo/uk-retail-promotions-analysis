"""Retail promotions and basket analysis: every number in the README comes from here.

Usage:  python src/analysis.py        (run src/load_to_sqlite.py first)
Writes: results/*.csv, results/findings.json, charts/*.png
"""
from __future__ import annotations

import json
import re
import sqlite3
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "completejourney.db"
SQL = ROOT / "sql"
RES = ROOT / "results"
CH = ROOT / "charts"
RES.mkdir(exist_ok=True)
CH.mkdir(exist_ok=True)

# ---------- chart style (reference palette, light mode) ----------
BLUE, ORANGE, AQUA, GREY = "#2a78d6", "#eb6834", "#1baf7a", "#8a8984"
INK, INK2 = "#0b0b0b", "#52514e"
plt.rcParams.update({
    "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb", "savefig.facecolor": "#fcfcfb",
    "font.size": 10, "axes.edgecolor": "#d6d5d0", "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "grid.color": "#ecebe7",
    "grid.linewidth": 0.8, "axes.axisbelow": True, "axes.titleweight": "bold",
    "axes.titlesize": 12, "axes.titlelocation": "left", "axes.titlecolor": INK,
})


def save(fig, name):
    # move the axes title to the figure's left edge so long y-labels never push it off-canvas
    ax = fig.axes[0]
    title = ax.get_title(loc="left")
    if title:
        ax.set_title("", loc="left")
        fig.suptitle(title, x=0.012, ha="left", fontsize=12, fontweight="bold", color=INK)
    fig.tight_layout()
    fig.savefig(CH / name, dpi=160)
    plt.close(fig)


# ---------- SQL helpers ----------
def named_queries(file: str) -> dict[str, str]:
    """Split a .sql file into {name: query} using '-- name: x' markers."""
    text = (SQL / file).read_text()
    parts = re.split(r"^-- name:\s*(\w+)\s*$", text, flags=re.M)
    return {parts[i]: parts[i + 1].strip().rstrip(";") for i in range(1, len(parts), 2)}


def q(con, file, name) -> pd.DataFrame:
    return pd.read_sql_query(named_queries(file)[name], con)


# ---------- analysis steps ----------
def profile(con, F):
    cov = q(con, "01_profile.sql", "coverage").iloc[0]
    miss = q(con, "01_profile.sql", "missing_values")
    dist = q(con, "01_profile.sql", "basket_count_distribution")
    miss.to_csv(RES / "missing_values.csv", index=False)
    dist.to_csv(RES / "basket_count_distribution.csv", index=False)
    F["coverage"] = {k: (v.item() if hasattr(v, "item") else v) for k, v in cov.items()}
    F["households_under_5_baskets"] = int(dist.loc[dist.baskets_in_year == "1-4", "households"].sum())


def baseline(con, F):
    wk = q(con, "02_baseline.sql", "weekly_sales")
    wk = wk[(wk.week >= 2) & (wk.week <= 52)]          # weeks 1 and 53 are partial (1 day each)
    bs = q(con, "02_baseline.sql", "basket_summary").iloc[0]
    top = q(con, "02_baseline.sql", "top_categories")
    wk.to_csv(RES / "weekly_sales.csv", index=False)
    top.to_csv(RES / "top_categories.csv", index=False)
    F["avg_basket_value"] = float(bs.avg_basket_value)
    F["avg_lines_per_basket"] = float(bs.avg_lines_per_basket)
    F["avg_weekly_sales"] = round(float(wk.sales.mean()), 0)
    F["top_category"] = top.iloc[0][["product_category", "revenue"]].to_dict()

    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.plot(pd.to_datetime(wk.week_start), wk.sales / 1000, color=BLUE, lw=2)
    ax.set_title("Weekly sales, 2017 (all 2,469 households)")
    ax.set_ylabel("Sales ($ thousands)")
    ax.set_ylim(0, None)
    peak = wk.loc[wk.sales.idxmax()]
    ax.annotate(f"Peak: week {peak.week}\n${peak.sales/1000:,.0f}k",
                (pd.to_datetime(peak.week_start), peak.sales / 1000),
                xytext=(-80, -6), textcoords="offset points", color=INK2, fontsize=9,
                arrowprops=dict(arrowstyle="-", color=GREY, lw=0.8))
    save(fig, "01_weekly_sales.png")

    t = top.head(10).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.barh(t.product_category.str.title(), t.revenue / 1000, color=BLUE, height=0.6)
    for y, v in enumerate(t.revenue / 1000):
        ax.text(v + 2, y, f"${v:,.0f}k", va="center", color=INK2, fontsize=9)
    ax.set_title("Top 10 categories by revenue")
    ax.set_xlabel("Revenue ($ thousands)")
    ax.grid(axis="y", visible=False)
    save(fig, "02_top_categories.png")


def rfm(con, F):
    df = q(con, "03_rfm.sql", "rfm")
    df.to_csv(RES / "rfm_households.csv", index=False)
    seg = (df.groupby("segment")
             .agg(households=("household_id", "count"),
                  avg_recency_days=("recency_days", "mean"),
                  avg_baskets=("frequency", "mean"),
                  avg_spend=("monetary", "mean"),
                  total_spend=("monetary", "sum"))
             .sort_values("total_spend", ascending=False))
    seg["share_of_households"] = seg.households / seg.households.sum()
    seg["share_of_spend"] = seg.total_spend / seg.total_spend.sum()
    plain = {
        "Champions": "Shop every few days, spend the most, still active. Protect them; don't discount to them by default.",
        "Loyal regulars": "Weekly-ish shoppers with solid spend. The core of the business; upsell, not acquire.",
        "Middle of the road": "Average on all three measures. Best target for 'complete the basket' offers.",
        "At risk": "Used to shop often but haven't been seen lately. Worth a win-back coupon now.",
        "New or occasional": "Seen recently but rarely. Either new, or a top-up shopper using another main store.",
        "Lapsed": "Rare and not recent. Cheapest to let go; low return on promotional spend.",
    }
    seg["in_plain_english"] = seg.index.map(plain)
    seg.round(3).to_csv(RES / "rfm_segments.csv")
    F["rfm_segments"] = seg[["households", "share_of_households", "share_of_spend", "avg_spend"]].round(3).reset_index().to_dict("records")

    s = seg.sort_values("share_of_spend")
    fig, ax = plt.subplots(figsize=(8, 3.8))
    y = np.arange(len(s))
    ax.barh(y + 0.2, s.share_of_households * 100, height=0.36, color=GREY, label="% of households")
    ax.barh(y - 0.2, s.share_of_spend * 100, height=0.36, color=BLUE, label="% of spend")
    for i, (h, sp) in enumerate(zip(s.share_of_households * 100, s.share_of_spend * 100)):
        ax.text(sp + 0.6, i - 0.2, f"{sp:.0f}%", va="center", fontsize=8.5, color=INK2)
        ax.text(h + 0.6, i + 0.2, f"{h:.0f}%", va="center", fontsize=8.5, color=INK2)
    ax.set_yticks(y, s.index)
    ax.set_title("RFM segments: share of households vs share of spend")
    ax.set_xlabel("Percent")
    ax.grid(axis="y", visible=False)
    ax.legend(frameon=False, loc="lower right")
    save(fig, "03_rfm_segments.png")


def did(con, F):
    win = q(con, "04_campaign_did.sql", "campaign_windows")
    hw = q(con, "04_campaign_did.sql", "household_window_spend")
    hw["diff"] = hw.during_weekly_spend - hw.pre_weekly_spend
    strata = q(con, "04_campaign_did.sql", "household_strata")
    hw = hw.merge(strata, on="household_id")
    keep = win[win.window_days >= 14].campaign_id          # drop windows clipped to a few days
    rows = []
    for (cid, ctype), g in hw[hw.campaign_id.isin(keep)].groupby(["campaign_id", "campaign_type"]):
        t = g[g.targeted == 1]
        if len(t) < 30:
            continue
        est, se = stratified_did(g)
        p = 2 * (1 - stats.norm.cdf(abs(est / se)))
        c = g[g.targeted == 0]
        rows.append(dict(campaign_id=int(cid), campaign_type=ctype, targeted_hh=len(t), control_hh=len(c),
                         treated_pre=t.pre_weekly_spend.mean(), treated_during=t.during_weekly_spend.mean(),
                         control_pre=c.pre_weekly_spend.mean(), control_during=c.during_weekly_spend.mean(),
                         did_per_week=est, ci_low=est - 1.96 * se, ci_high=est + 1.96 * se, p_value=p,
                         lift_pct=est / t.pre_weekly_spend.mean() * 100))
    res = pd.DataFrame(rows).merge(win[["campaign_id", "start_date", "end_date", "window_days"]].astype({"campaign_id": int}),
                                   on="campaign_id").sort_values("did_per_week", ascending=False)
    res.round(4).to_csv(RES / "campaign_did.csv", index=False)

    # pooled by type: household-weighted average of per-campaign estimates
    by_type = res.groupby("campaign_type").apply(
        lambda g: pd.Series({"campaigns": len(g), "avg_did_per_week": np.average(g.did_per_week, weights=g.targeted_hh),
                             "avg_lift_pct": np.average(g.lift_pct, weights=g.targeted_hh),
                             "significant_campaigns": int((g.p_value < 0.05).sum())}))
    by_type.round(3).to_csv(RES / "campaign_did_by_type.csv")

    # placebo: shift every window back one window length; a real effect should vanish
    placebo = placebo_did(con, win)
    F["did"] = {
        "campaigns_tested": int(len(res)),
        "significant_positive": int(((res.p_value < 0.05) & (res.did_per_week > 0)).sum()),
        "best": res.iloc[0][["campaign_id", "campaign_type", "did_per_week", "lift_pct", "p_value", "targeted_hh"]].to_dict(),
        "worst": res.iloc[-1][["campaign_id", "campaign_type", "did_per_week", "lift_pct", "p_value"]].to_dict(),
        "by_type": by_type.round(3).reset_index().to_dict("records"),
        "median_lift_pct": float(res.lift_pct.median()),
        "placebo_tests": len(placebo),
        "placebo_significant": sum(p["p_value"] < 0.05 for p in placebo),
        "placebo_mean_abs_did": float(np.mean([abs(p["placebo_did"]) for p in placebo])),
    }

    r = res.sort_values("did_per_week")
    colors = [{"Type A": BLUE, "Type B": ORANGE, "Type C": AQUA}[t] for t in r.campaign_type]
    fig, ax = plt.subplots(figsize=(8, 5))
    y = np.arange(len(r))
    ax.hlines(y, r.ci_low, r.ci_high, color="#c9c8c2", lw=2)
    ax.scatter(r.did_per_week, y, color=colors, s=46, zorder=3, edgecolor="#fcfcfb", linewidth=1.5)
    ax.axvline(0, color=INK2, lw=1)
    ax.set_yticks(y, [f"Campaign {c}" for c in r.campaign_id], fontsize=8.5)
    ax.set_xlabel("Extra spend per targeted household per week ($), with 95% CI")
    ax.set_title("Promotion lift by campaign: no campaign clears zero\n(difference-in-differences within shopping-intensity deciles)")
    for t, col in [("Type A", BLUE), ("Type B", ORANGE), ("Type C", AQUA)]:
        ax.scatter([], [], color=col, s=40, label=t)
    ax.legend(frameon=False, loc="lower right", title="Campaign type", title_fontsize=9)
    ax.grid(axis="y", visible=False)
    save(fig, "04_campaign_lift.png")
    return res


def stratified_did(g: pd.DataFrame) -> tuple[float, float]:
    """DiD within shopping-intensity deciles, weighted by targeted households per decile."""
    ests, vars_, w = [], [], []
    for _, s in g.groupby("intensity_decile"):
        t, c = s[s.targeted == 1]["diff"], s[s.targeted == 0]["diff"]
        if len(t) < 3 or len(c) < 3:
            continue
        ests.append(t.mean() - c.mean())
        vars_.append(t.var() / len(t) + c.var() / len(c))
        w.append(len(t))
    w = np.array(w) / sum(w)
    return float(np.dot(w, ests)), float(np.sqrt(np.dot(w ** 2, vars_)))


def placebo_did(con, win) -> list:
    hw = q(con, "04_campaign_did.sql", "household_window_spend").merge(
        q(con, "04_campaign_did.sql", "household_strata"), on="household_id")
    # placebo uses the two windows *before* the campaign: pre-pre vs pre
    daily = pd.read_sql_query("SELECT household_id, DATE(transaction_timestamp) d, SUM(sales_value) s "
                              "FROM transactions GROUP BY 1, 2", con)
    daily["d"] = pd.to_datetime(daily.d)
    out = []
    for _, w in win.iterrows():
        start, days = pd.Timestamp(w.start_date), int(w.window_days)
        pre_s, pp_s = start - pd.Timedelta(days=days), start - pd.Timedelta(days=2 * days)
        if pp_s < pd.Timestamp("2017-01-01"):
            continue
        sub = daily[(daily.d >= pp_s) & (daily.d < start)]
        a = sub[sub.d < pre_s].groupby("household_id").s.sum()
        b = sub[sub.d >= pre_s].groupby("household_id").s.sum()
        if days < 14:
            continue
        g = hw[hw.campaign_id == w.campaign_id][["household_id", "targeted", "intensity_decile"]].set_index("household_id")
        g["diff"] = (b.reindex(g.index).fillna(0) - a.reindex(g.index).fillna(0)) * 7 / days
        if (g.targeted == 1).sum() < 30:
            continue
        est, se = stratified_did(g)
        out.append({"campaign_id": int(w.campaign_id), "placebo_did": est, "p_value": float(2 * (1 - stats.norm.cdf(abs(est / se))))})
    pd.DataFrame(out).round(4).to_csv(RES / "campaign_did_placebo.csv", index=False)
    return out


def promotions(con, F):
    cp = q(con, "05_promotions.sql", "coupon_already_buyer")
    share = cp.bought_before.mean()
    by_cat = (cp.groupby("product_category")
                .agg(coupon_lines=("bought_before", "size"), already_buyer_rate=("bought_before", "mean"),
                     coupon_cost=("coupon_disc", "sum"))
                .query("coupon_lines >= 25").sort_values("coupon_cost", ascending=False))
    by_cat.round(3).to_csv(RES / "coupon_already_buyer_by_category.csv")
    F["coupons"] = {"lines": int(len(cp)), "already_buyer_share": float(share),
                    "coupon_cost_on_existing_buyers": float(cp.loc[cp.bought_before == 1, "coupon_disc"].sum()),
                    "coupon_cost_total": float(cp.coupon_disc.sum()),
                    "top_categories": by_cat.head(5).round(3).reset_index().to_dict("records")}

    halo = q(con, "05_promotions.sql", "basket_halo")
    wide = halo.pivot(index="household_id", columns="has_promo_item", values=["avg_full_price_spend", "baskets"]).dropna()
    wide = wide[(wide[("baskets", 0)] >= 5) & (wide[("baskets", 1)] >= 5)]
    d = wide[("avg_full_price_spend", 1)] - wide[("avg_full_price_spend", 0)]
    F["basket_halo"] = {"households": int(len(wide)),
                        "full_price_spend_no_promo": float(wide[("avg_full_price_spend", 0)].mean()),
                        "full_price_spend_with_promo": float(wide[("avg_full_price_spend", 1)].mean()),
                        "mean_within_household_diff": float(d.mean()),
                        "share_households_positive": float((d > 0).mean())}

    dep = q(con, "05_promotions.sql", "category_discount_dependence")
    dep.to_csv(RES / "category_discount_dependence.csv", index=False)
    F["discount_dependence_top"] = dep.head(5).to_dict("records")

    c = by_cat.head(10).iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 4.4))
    ax.barh(c.index.str.title(), c.already_buyer_rate * 100, color=ORANGE, height=0.6)
    for yy, (v, cost) in enumerate(zip(c.already_buyer_rate * 100, c.coupon_cost)):
        ax.text(v + 1, yy, f"{v:.0f}%  (${cost:,.0f} coupons)", va="center", fontsize=8.5, color=INK2)
    ax.axvline(share * 100, color=INK2, lw=1, ls="--")
    ax.text(share * 100 + 0.6, -0.9, f"All categories: {share*100:.0f}%", fontsize=8.5, color=INK2)
    ax.set_ylim(-1.3, len(c) - 0.4)
    ax.set_xlim(0, 62)
    ax.set_xlabel("% of coupon uses by a household that bought the item at full price in the prior 8 weeks")
    ax.set_title("Coupons that paid for habits\n(top 10 categories by coupon cost)")
    ax.grid(axis="y", visible=False)
    save(fig, "05_coupon_subsidy.png")


def basket_rules(con, F):
    from mlxtend.frequent_patterns import association_rules, fpgrowth
    long = q(con, "05_promotions.sql", "basket_categories")
    n_baskets = long.basket_id.nunique()
    keep = long.product_category.value_counts()
    keep = keep[keep / n_baskets >= 0.01].index
    long = long[long.product_category.isin(keep)]
    m = pd.crosstab(long.basket_id, long.product_category).astype(bool)
    items = fpgrowth(m, min_support=0.01, use_colnames=True, max_len=3)
    rules = association_rules(items, metric="lift", min_threshold=1.2)
    rules = rules[(rules.confidence >= 0.2)]
    rules["antecedents"] = rules.antecedents.apply(lambda s: " + ".join(sorted(x.title() for x in s)))
    rules["consequents"] = rules.consequents.apply(lambda s: " + ".join(sorted(x.title() for x in s)))
    rules = rules[["antecedents", "consequents", "support", "confidence", "lift"]].sort_values("lift", ascending=False)
    rules.round(4).to_csv(RES / "association_rules.csv", index=False)
    single = rules[~rules.antecedents.str.contains(r"\+") & ~rules.consequents.str.contains(r"\+")]
    # drop the mirrored duplicate of each pair
    single = single[single.apply(lambda r: r.antecedents < r.consequents, axis=1)]
    F["basket"] = {"baskets_analysed": int(len(m)), "categories": int(m.shape[1]), "rules": int(len(rules)),
                   "top_pairs": single.head(8).round(3).to_dict("records")}

    top = single.head(10).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    labels = [f"{a}  ↔  {b}" for a, b in zip(top.antecedents, top.consequents)]
    ax.barh(labels, top.lift, color=AQUA, height=0.6)
    for yy, (l, s) in enumerate(zip(top.lift, top.support)):
        ax.text(l + 0.05, yy, f"{l:.1f}×  ·  {s*100:.1f}% of baskets", va="center", fontsize=8.5, color=INK2)
    ax.axvline(1, color=INK2, lw=1)
    ax.set_xlim(0, top.lift.max() * 1.4)
    ax.set_xlabel("Lift (1 = bought together no more than chance)")
    ax.set_title("Categories bought together most often (market basket analysis)")
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", labelsize=8.5)
    save(fig, "06_basket_pairs.png")


def main():
    con = sqlite3.connect(DB)
    F: dict = {}
    for step in (profile, baseline, rfm, did, promotions, basket_rules):
        print(f"→ {step.__name__}")
        step(con, F)
    (RES / "findings.json").write_text(json.dumps(F, indent=2, default=float))
    print(json.dumps(F, indent=2, default=float))


if __name__ == "__main__":
    main()
