"""
Collections Recovery — Executive Dashboard (Streamlit)
========================================================
Premium / private-banking visual redesign v2: near-black canvas,
gold and champagne palette, serif headlines, generous whitespace.

Changes from v1 (layout only — all numbers, logic and data
contracts are untouched):
    - Masthead mirrored: period box now sits on the left, title
      block on the right, with a small monogram seal added.
    - KPI strip now leads (before the verdict pull-quote, not after).
    - Deep-dive tab order flipped (Recovery Rate first).
    - Evidence row reordered: Counterfactual → Mix check → Channel.
    - Investment metric strip moved above the narrative box.
    - Extra premium ornament: hairline masthead rule + closing mark.

Run:
    pip install streamlit pandas matplotlib
    streamlit run app.py

Data files expected in ./data/ (bundled alongside this script):
    metrics_results.json
    monthly_funnel_metrics.csv
    counterfactual_did.json
"""

import json
import os
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Collections Recovery — Executive Dashboard",
    page_icon="◆",
    layout="wide",
)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# ---------------------------------------------------------------------------
# Palette — a private-banking / wealth-review system: near-black canvas,
# gold accent, champagne highlights. Restrained, not a generic dashboard.
# ---------------------------------------------------------------------------
COLORS = {
    "bg": "#0A0A0B",          # page background — near-black
    "panel": "#131315",       # card background
    "panel2": "#1A1A1D",      # nested / raised panel
    "text": "#F2EFE9",        # primary text — warm off-white
    "gold": "#C9A227",        # primary accent
    "champagne": "#E8DCC4",   # secondary highlight
    "sage": "#7C9880",        # positive figures
    "rust": "#B5564A",        # negative / flags
    "muted": "#8B8680",       # secondary / muted text
    "line": "#26262A",        # hairline borders
}

MONTHS_FULL = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07"]
MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul"]

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
@st.cache_data
def load_data():
    try:
        with open(os.path.join(DATA_DIR, "metrics_results.json")) as f:
            results = json.load(f)
        with open(os.path.join(DATA_DIR, "counterfactual_did.json")) as f:
            did = json.load(f)
        funnel = pd.read_csv(os.path.join(DATA_DIR, "monthly_funnel_metrics.csv"), index_col=0)
        return results, did, funnel
    except FileNotFoundError:
        st.error(
            "Data files not found in ./data/. Place metrics_results.json, "
            "counterfactual_did.json, and monthly_funnel_metrics.csv in a "
            "'data' folder next to this script."
        )
        st.stop()

results, did, funnel = load_data()

# ---------------------------------------------------------------------------
# Global CSS
# ---------------------------------------------------------------------------
st.markdown(
    f"""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

      .stApp {{
        background: {COLORS['bg']} !important;
      }}
      .block-container {{
        max-width: 1180px; padding-top: 2.2rem; padding-bottom: 4rem;
      }}
      html, body, [class*="css"] {{
        font-family: 'Inter', sans-serif;
      }}
      .stMarkdown, .stMarkdown p, .stCaption, .stCaption p, [data-testid="stCaptionContainer"] {{
        color: {COLORS['text']} !important;
      }}
      hr {{ border-color: {COLORS['line']} !important; }}

      /* ---------------- Masthead ornament (new) ---------------- */
      .masthead-rule {{
        display: flex; align-items: center; gap: 14px;
        margin-bottom: 26px;
      }}
      .masthead-rule .line {{
        flex: 1; height: 1px; background: {COLORS['line']};
      }}
      .masthead-rule .diamond {{
        color: {COLORS['gold']} !important; font-size: 10px; opacity: 0.85;
      }}
      .seal {{
        width: 42px; height: 42px; border: 1px solid {COLORS['gold']};
        border-radius: 50%; display: flex; align-items: center; justify-content: center;
        font-family: 'Cormorant Garamond', serif; font-weight: 700; font-size: 15px;
        color: {COLORS['gold']} !important; letter-spacing: 0.02em; margin-bottom: 16px;
      }}

      /* ---------------- Masthead ---------------- */
      .case-label {{
        font-family: 'IBM Plex Mono', monospace; font-size: 10.5px;
        color: {COLORS['gold']} !important; letter-spacing: 0.28em;
        text-transform: uppercase; margin-bottom: 14px;
      }}
      .dashboard-title {{
        font-family: 'Cormorant Garamond', serif; font-weight: 600;
        font-size: 46px; color: {COLORS['text']} !important;
        line-height: 1.05; margin-bottom: 10px; letter-spacing: 0.01em;
      }}
      .dashboard-subtitle {{
        font-size: 13.5px; color: {COLORS['muted']} !important; line-height: 1.6;
        letter-spacing: 0.01em; font-style: italic;
      }}
      .period-box {{
        text-align: left; font-size: 11.5px; color: {COLORS['muted']} !important;
        line-height: 1.8; padding-top: 4px; font-family: 'IBM Plex Mono', monospace;
        text-transform: uppercase; letter-spacing: 0.05em;
        border-left: 1px solid {COLORS['line']}; padding-left: 18px;
      }}
      .period-box b {{ color: {COLORS['gold']} !important; font-weight: 600; }}
      .gold-rule {{
        height: 1px; background: linear-gradient(90deg, {COLORS['gold']}, transparent);
        margin: 22px 0 30px 0;
      }}

      /* ---------------- Verdict — quiet pull-quote ---------------- */
      .verdict-box {{
        border-top: 1px solid {COLORS['gold']};
        border-bottom: 1px solid {COLORS['gold']};
        padding: 26px 4px;
        margin: 8px 0 34px 0;
      }}
      .verdict-tag {{
        color: {COLORS['gold']} !important;
        font-family: 'IBM Plex Mono', monospace;
        text-transform: uppercase;
        font-weight: 600;
        font-size: 10.5px;
        letter-spacing: 0.24em;
        margin-bottom: 12px;
        display: block;
      }}
      .verdict-text {{
        font-family: 'Cormorant Garamond', serif;
        font-size: 24px; font-weight: 500; line-height: 1.45; max-width: 900px;
        color: {COLORS['champagne']} !important;
      }}
      .verdict-text * {{ color: {COLORS['champagne']} !important; }}
      .verdict-text b {{ color: {COLORS['gold']} !important; font-weight: 700; }}

      /* ---------------- KPI row ---------------- */
      .kpi-card {{
        background: transparent;
        border-top: 1px solid {COLORS['line']};
        padding: 18px 4px 4px 4px;
        height: 100%;
      }}
      .kpi-label {{
        font-size: 10px; text-transform: uppercase; letter-spacing: 0.1em;
        color: {COLORS['muted']} !important;
        margin-bottom: 14px; font-family: 'IBM Plex Mono', monospace;
      }}
      .kpi-value {{
        font-family: 'Cormorant Garamond', serif; font-size: 34px; font-weight: 600;
        color: {COLORS['gold']} !important;
      }}
      .kpi-neg .kpi-value {{ color: {COLORS['rust']} !important; }}
      .kpi-pos .kpi-value {{ color: {COLORS['sage']} !important; }}
      .kpi-note {{
        font-size: 11px; color: {COLORS['muted']} !important; margin-top: 10px; line-height: 1.4;
      }}

      /* ---------------- Section headers ---------------- */
      .section-label {{
        font-family: 'IBM Plex Mono', monospace; font-size: 10.5px;
        color: {COLORS['gold']} !important; letter-spacing: 0.24em;
        text-transform: uppercase; margin: 6px 0 4px 0;
      }}
      .section-title {{
        font-family: 'Cormorant Garamond', serif; font-weight: 600;
        font-size: 26px; color: {COLORS['text']} !important; margin-bottom: 18px;
      }}

      /* ---------------- Deep-dive tabs (chart section) ---------------- */
      .stTabs [data-baseweb="tab-list"] {{
        gap: 28px; border-bottom: 1px solid {COLORS['line']};
      }}
      .stTabs [data-baseweb="tab"] {{
        background: transparent; color: {COLORS['muted']} !important;
        font-family: 'IBM Plex Mono', monospace; font-size: 11.5px;
        text-transform: uppercase; letter-spacing: 0.08em; padding: 10px 2px;
      }}
      .stTabs [aria-selected="true"] {{
        color: {COLORS['gold']} !important; border-bottom: 2px solid {COLORS['gold']} !important;
      }}
      .chart-frame {{
        background: {COLORS['panel']};
        border: 1px solid {COLORS['line']};
        border-radius: 2px;
        padding: 28px 30px 12px 30px;
        margin-top: 20px;
        box-shadow: 0 14px 30px -18px rgba(0,0,0,0.6);
      }}
      .chart-title {{
        font-family: 'Cormorant Garamond', serif; font-size: 21px; font-weight: 600;
        color: {COLORS['text']} !important; margin-bottom: 4px;
      }}
      .chart-desc {{
        font-size: 12px; color: {COLORS['muted']} !important; margin-bottom: 6px; line-height: 1.5;
      }}

      /* ---------------- Panels / cards (evidence row) ---------------- */
      [data-testid="stVerticalBlockBorderWrapper"] {{
        background: {COLORS['panel']} !important;
        border: 1px solid {COLORS['line']} !important;
        border-radius: 2px !important;
        box-shadow: 0 12px 26px -20px rgba(0,0,0,0.7) !important;
      }}
      .card-title {{
        font-family: 'Cormorant Garamond', serif; font-size: 19px; font-weight: 600;
        color: {COLORS['text']} !important; margin-bottom: 3px;
      }}
      .card-desc {{
        font-size: 12px; color: {COLORS['muted']} !important; margin-bottom: 12px; line-height: 1.5;
      }}

      /* ---------------- Channel bars ---------------- */
      .bar-row {{ display: flex; align-items: center; gap: 8px; margin: 10px 0; }}
      .bar-label {{ width: 84px; font-size: 12px; color: {COLORS['text']} !important; }}
      .bar-track {{
        flex: 1; background: {COLORS['line']}; border-radius: 1px; height: 10px;
        position: relative; overflow: hidden;
      }}
      .bar-fill {{ background: {COLORS['gold']}; height: 100%; border-radius: 1px; }}
      .bar-val {{
        width: 52px; font-family: 'IBM Plex Mono', monospace; font-size: 12px;
        text-align: right; color: {COLORS['champagne']} !important;
      }}

      /* ---------------- Investment metric strip (now leads) ---------------- */
      .invest-strip {{
        border-top: 1px solid {COLORS['line']};
        border-bottom: 1px solid {COLORS['line']};
        padding: 20px 4px;
        margin-bottom: 22px;
      }}

      /* ---------------- Investment recommendation ---------------- */
      .invest-box {{
        background: {COLORS['panel']};
        border: 1px solid {COLORS['gold']};
        border-radius: 2px;
        padding: 30px 34px;
        margin-top: 4px;
        color: {COLORS['text']} !important;
        box-shadow: 0 16px 34px -22px rgba(201,162,39,0.25);
      }}
      .invest-box * {{ color: {COLORS['text']} !important; }}
      .invest-box h3 {{
        margin: 0 0 14px; font-family: 'Cormorant Garamond', serif; font-weight: 600;
        font-size: 26px; color: {COLORS['gold']} !important;
      }}
      .invest-box b {{ color: {COLORS['gold']} !important; }}
      .invest-k {{
        color: {COLORS['muted']} !important; text-transform: uppercase; letter-spacing: 0.08em;
        display: block; margin-bottom: 5px; font-size: 10px;
        font-family: 'IBM Plex Mono', monospace;
      }}
      .invest-v {{
        font-family: 'IBM Plex Mono', monospace; font-size: 12.5px;
        color: {COLORS['champagne']} !important; line-height: 1.5;
      }}

      .footer-note {{ font-size: 11px; color: {COLORS['muted']} !important; line-height: 1.6; }}
      .closing-mark {{
        text-align: center; color: {COLORS['gold']} !important; font-size: 11px;
        letter-spacing: 0.4em; margin: 6px 0 18px 0; opacity: 0.8;
      }}

      /* Streamlit dataframe legibility on dark canvas */
      [data-testid="stDataFrame"] {{ border-radius: 2px; overflow: hidden; }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Shared matplotlib styling — premium: minimal gridlines, gold/champagne
# lines with soft fills, no top/right spines, quiet ticks.
# ---------------------------------------------------------------------------
def style_axes(ax):
    ax.set_facecolor(COLORS["panel"])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color(COLORS["line"])
    ax.tick_params(labelsize=9.5, colors=COLORS["muted"], length=0)
    ax.grid(axis="y", linestyle="-", alpha=0.12, color=COLORS["champagne"])
    ax.set_axisbelow(True)


# ---------------------------------------------------------------------------
# Masthead ornament + seal (new — sits above the header)
# ---------------------------------------------------------------------------
st.markdown(
    '<div class="masthead-rule"><div class="line"></div><div class="diamond">◆</div><div class="line"></div></div>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Header — mirrored: period box now leads on the left, title on the right
# ---------------------------------------------------------------------------
h_left, h_right = st.columns([1, 2.2])
with h_left:
    st.markdown('<div class="seal">CR</div>', unsafe_allow_html=True)
    st.markdown(
        "<div class='period-box'>"
        "<b>Analysis period</b><br>"
        "Jan 1 – Jul 31 2026 (7 complete months)<br>"
        "Aug excluded — partial month (data ends Aug 8)</div>",
        unsafe_allow_html=True,
    )
with h_right:
    st.markdown('<div class="case-label">Collections Recovery · Executive Review</div>', unsafe_allow_html=True)
    st.markdown('<div class="dashboard-title">Portfolio Performance</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="dashboard-subtitle">Golden-dataset numbers, corrected definitions. '
        'Prepared for the investment committee.</div>',
        unsafe_allow_html=True,
    )

st.markdown('<div class="gold-rule"></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# KPI row — now leads, ahead of the verdict quote
# ---------------------------------------------------------------------------
trend_r2 = results["trend_ols_r2"]
jan_jul_change = results["full_period_cagr_style_change_jan_to_jul"]

def kpi_card(label, value, note, tone="neutral"):
    st.markdown(
        f"""
        <div class="kpi-card kpi-{tone}">
          <div class="kpi-label">{label}</div>
          <div class="kpi-value">{value}</div>
          <div class="kpi-note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    kpi_card("Reported claim", "+11% MoM", "Matches Feb→Mar only", "neutral")
with k2:
    kpi_card("Jan → Jul actual change", f"{jan_jul_change:.1f}%", "Net decline over the full window", "neg")
with k3:
    kpi_card("Trend strength (R²)", f"{trend_r2:.3f}", "Near zero — no detectable trend", "neutral")
with k4:
    kpi_card("Naive vs corrected recovery rate", "+2.5–2.9pp", "Naive definition overstates every month", "neg")
with k5:
    kpi_card("Targeting-strategy DiD effect", f"{did['did_pp']:.2f}pp", "Not distinguishable from zero", "neutral")

st.markdown('<div class="gold-rule" style="margin-top:30px;"></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Verdict — quiet pull-quote (now follows the KPI strip)
# ---------------------------------------------------------------------------
st.markdown(
    f"""
    <div class="verdict-box">
      <span class="verdict-tag">The verdict</span>
      <div class="verdict-text">
        The reported <b>+11% month-on-month improvement</b> is real for exactly
        one month-pair (Feb→Mar) — it is not a sustained trend.
        The 7-month series is flat and noisy (trend R² = {trend_r2:.3f}),
        Jan→Jul is down <b>{abs(jan_jul_change):.1f}%</b>, and portfolio-mix
        effects, targeting-strategy changes, and denominator manipulation were
        each tested and ruled out as explanations.
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Deep Dive — charts, tab order flipped (Recovery Rate first)
# ---------------------------------------------------------------------------
st.markdown('<div class="section-label">Deep dive</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">The series, examined</div>', unsafe_allow_html=True)

tab1, tab2 = st.tabs(["Recovery Rate — Naive vs. Corrected", "Monthly Recovered Amount"])

with tab1:
    st.markdown('<div class="chart-frame">', unsafe_allow_html=True)
    st.markdown('<div class="chart-title">Recovery rate: naive vs. corrected definition</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="chart-desc">Naive (independent count ratio) vs. corrected '
        '(cohort join) — the gap is stable all period.</div>',
        unsafe_allow_html=True,
    )

    naive = [results["naive_vs_corrected_recovery_rate_pct"]["naive"][m] for m in MONTHS_FULL]
    corr = [results["naive_vs_corrected_recovery_rate_pct"]["corrected_cohort_join"][m] for m in MONTHS_FULL]

    fig2, ax2 = plt.subplots(figsize=(11.2, 4.6))
    fig2.patch.set_facecolor(COLORS["panel"])
    ax2.plot(MONTH_LABELS, naive, marker="o", color=COLORS["rust"], linewidth=2.4, markersize=7,
              markerfacecolor=COLORS["panel"], markeredgecolor=COLORS["rust"], markeredgewidth=2,
              label="Naive definition")
    ax2.plot(MONTH_LABELS, corr, marker="o", color=COLORS["gold"], linewidth=2.4, markersize=7,
              markerfacecolor=COLORS["panel"], markeredgecolor=COLORS["gold"], markeredgewidth=2,
              label="Corrected (cohort join)")
    ax2.set_ylim(6, 12)
    style_axes(ax2)
    ax2.legend(fontsize=9.5, loc="upper left", frameon=False, labelcolor=COLORS["text"])
    plt.tight_layout()
    st.pyplot(fig2, use_container_width=True)
    plt.close(fig2)
    st.markdown('</div>', unsafe_allow_html=True)

with tab2:
    st.markdown('<div class="chart-frame">', unsafe_allow_html=True)
    st.markdown('<div class="chart-title">Monthly recovered amount (₹ crore)</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="chart-desc">Oscillates ₹158–176 Cr with no sustained direction. '
        'Labels show month-on-month % at each point.</div>',
        unsafe_allow_html=True,
    )

    rec = [results["recovered_amount_by_month"][m] / 1e7 for m in MONTHS_FULL]
    mom = [results["recovered_amount_mom_pct"][m] for m in MONTHS_FULL]
    avg_rec = sum(rec) / len(rec)

    fig, ax = plt.subplots(figsize=(11.2, 4.6))
    fig.patch.set_facecolor(COLORS["panel"])
    ax.fill_between(MONTH_LABELS, rec, min(rec) - 0.4, color=COLORS["gold"], alpha=0.08)
    ax.plot(MONTH_LABELS, rec, marker="o", color=COLORS["gold"], linewidth=2.4, markersize=7,
            markerfacecolor=COLORS["panel"], markeredgecolor=COLORS["gold"], markeredgewidth=2)
    ax.axhline(avg_rec, color=COLORS["muted"], linestyle="--", linewidth=1, alpha=0.7)
    ax.text(len(MONTH_LABELS) - 1, avg_rec + 0.25, "7-month average",
            fontsize=9, color=COLORS["muted"], ha="right")
    for i, (m_val, mm) in enumerate(zip(rec, mom)):
        if mm != mm:  # NaN check
            continue
        color = COLORS["sage"] if mm > 0 else COLORS["rust"]
        ax.annotate(f"{mm:+.1f}%", (i, m_val), textcoords="offset points",
                    xytext=(0, 14), ha="center", fontsize=9.5, fontweight="bold", color=color)
    ax.set_ylim(15, 19.8)
    style_axes(ax)
    plt.tight_layout()
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="gold-rule" style="margin-top:36px;"></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Evidence row — reordered: Counterfactual (DiD) leads, then Mix, then Channel
# ---------------------------------------------------------------------------
st.markdown('<div class="section-label">Supporting evidence</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">Ruling out the alternatives</div>', unsafe_allow_html=True)

g1, g2, g3 = st.columns(3)

with g1:
    with st.container(border=True):
        st.markdown('<div class="card-title">Counterfactual (DiD)</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="card-desc">Targeting-strategy switchers vs. never-switched</div>',
            unsafe_allow_html=True,
        )

        did_df = pd.DataFrame({
            "": [f"Treated ({did['n_switchers']:,})", f"Control ({did['n_never']:,})"],
            "Pre": [f"{did['treat_pre']:.2f}%", f"{did['ctrl_pre']:.2f}%"],
            "Post": [f"{did['treat_post']:.2f}%", f"{did['ctrl_post']:.2f}%"],
            "Δ": [
                f"{did['treat_post']-did['treat_pre']:+.2f}pp",
                f"{did['ctrl_post']-did['ctrl_pre']:+.2f}pp",
            ],
        })
        st.dataframe(did_df, hide_index=True, use_container_width=True)
        st.markdown(
            f'<div class="card-desc" style="margin-top:10px;">DiD estimate: '
            f'{did["did_pp"]:.2f}pp — within noise, not causal evidence of impact.</div>',
            unsafe_allow_html=True,
        )

with g2:
    with st.container(border=True):
        st.markdown('<div class="card-title">Mix-adjustment check</div>', unsafe_allow_html=True)
        st.markdown(
            "<div class=\"card-desc\">Actual vs. rate standardized to January's risk-segment mix</div>",
            unsafe_allow_html=True,
        )

        actual = results["recovery_rate_actual_pct"]
        standardized = results["recovery_rate_standardized_to_jan_mix_pct"]
        mix_df = pd.DataFrame({
            "Month": MONTH_LABELS,
            "Actual": [f"{actual[m]:.2f}%" for m in MONTHS_FULL],
            "Standardized": [f"{standardized[m]:.2f}%" for m in MONTHS_FULL],
            "Diff": ["0.00pp"] * len(MONTHS_FULL),
        })
        st.dataframe(mix_df, hide_index=True, use_container_width=True)
        st.markdown(
            '<div class="card-desc" style="margin-top:10px;">Portfolio mix is '
            'not driving the swings.</div>',
            unsafe_allow_html=True,
        )

with g3:
    with st.container(border=True):
        st.markdown('<div class="card-title">Channel conversion</div>', unsafe_allow_html=True)
        st.markdown('<div class="card-desc">Recovery rate of accounts touched, by channel</div>', unsafe_allow_html=True)

        channel_conv = results["channel_conversion_pct"]
        rows_html = ""
        for ch, v in sorted(channel_conv.items(), key=lambda x: -x[1]):
            width_pct = v / 9 * 100
            rows_html += f"""
            <div class="bar-row">
              <div class="bar-label">{ch}</div>
              <div class="bar-track"><div class="bar-fill" style="width:{width_pct:.0f}%"></div></div>
              <div class="bar-val">{v:.2f}%</div>
            </div>
            """
        st.markdown(rows_html, unsafe_allow_html=True)
        st.markdown(
            '<div class="card-desc" style="margin-top:12px;">Spread is about 0.3pp — '
            'weak differentiation between channels.</div>',
            unsafe_allow_html=True,
        )

st.markdown('<div class="gold-rule" style="margin-top:36px;"></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Investment recommendation — metric strip now leads, narrative box follows
# ---------------------------------------------------------------------------
st.markdown('<div class="section-label">Recommendation</div>', unsafe_allow_html=True)

st.markdown('<div class="invest-strip">', unsafe_allow_html=True)
i1, i2, i3, i4 = st.columns(4)
with i1:
    st.markdown(
        '<span class="invest-k">Incremental recovery</span>'
        '<span class="invest-v">₹12–18 Cr / year<br>range reflects thin conversion edge</span>',
        unsafe_allow_html=True,
    )
with i2:
    st.markdown(
        '<span class="invest-k">Estimated cost</span>'
        '<span class="invest-v">₹10 Cr<br>about 150 field agents, fully loaded</span>',
        unsafe_allow_html=True,
    )
with i3:
    st.markdown(
        '<span class="invest-k">Break-even</span>'
        '<span class="invest-v">7–10 months</span>',
        unsafe_allow_html=True,
    )
with i4:
    st.markdown(
        '<span class="invest-k">Downside scenario</span>'
        '<span class="invest-v">₹3–5 Cr / yr<br>if the edge is account-selection bias, not a channel effect</span>',
        unsafe_allow_html=True,
    )
st.markdown('</div>', unsafe_allow_html=True)

st.markdown(
    """
    <div class="invest-box">
      <h3>The next ₹10 Cr — where it should go</h3>
      <div style="font-size:14.5px; line-height:1.75;">
        Recommendation: <b>Field Operations</b> — the marginal conversion leader
        (7.65% vs 7.39–7.58% for other channels), but the edge is thin
        (about 0.3pp spread across all five channels) and not a strong
        standalone signal.
        <br><br>
        Why Field Operations and not the alternatives: it ranks first every
        month, not just on the period average, so the edge isn't an artifact
        of one strong month. That said, a 0.3pp spread across five channels
        is inside the range normal sampling noise would produce at this
        volume — we can't rule out that field-worked accounts simply skew
        toward higher-propensity-to-pay segments, which would make this a
        selection effect rather than a channel effect. The counterfactual
        test (above) already shows the same pattern: measured effects
        this small are indistinguishable from zero in this dataset.
        <br><br>
        What this means for the ₹10 Cr: treat Field Operations as the
        <b>working hypothesis</b>, not a confirmed bet. Fund a controlled
        pilot before scaling the full amount.
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.write("")

st.caption(
    "Confidence: low to medium. No real cost table or randomized pilot exists in the "
    "source data — recommend a four-week A/B test before committing the full amount. "
    "See the Executive Memo for full reasoning."
)

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown('<div class="gold-rule" style="margin-top:8px;"></div>', unsafe_allow_html=True)
st.markdown('<div class="closing-mark">◆ ◆ ◆</div>', unsafe_allow_html=True)
st.markdown(
    """
    <div class="footer-note">
    Golden dataset: 30,000 accounts, 8 event tables. Every number above traces
    to <code>metrics_results.json</code>, <code>monthly_funnel_metrics.csv</code>,
    and <code>counterfactual_did.json</code>. Full methodology: analysis
    notebook, SQL repository, and Data Quality Report.
    </div>
    """,
    unsafe_allow_html=True,
)