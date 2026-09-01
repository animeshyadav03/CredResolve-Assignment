# Collections Recovery — Executive Dashboard (Streamlit)

Python/Streamlit port of `executive_dashboard.html` — same data, same
verdict, same numbers, same layout (verdict banner → 5 KPI cards → 2
trend charts → 3-column detail cards → investment box → footer).

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

Opens at `http://localhost:8501`.

## Structure

```
streamlit_app/
├── app.py                  # the dashboard
├── requirements.txt
└── data/
    ├── metrics_results.json        # all computed metrics (source of truth)
    ├── monthly_funnel_metrics.csv  # month-by-month funnel table
    └── counterfactual_did.json     # DiD counterfactual result
```

`app.py` reads from `./data/` at startup (cached via `@st.cache_data`), so
every number on screen traces back to the same computation that produced
the HTML dashboard, the notebook, and the executive memo — nothing is
hand-typed twice. If you regenerate `metrics_results.json` (e.g. after
re-running `compute_metrics.py` on updated source data), just drop the new
file in `data/` and refresh the app.

## What's on the page

- **Verdict banner** — the headline finding (the "+11%" is one month-pair,
  not a trend).
- **5 KPI cards** — reported claim, Jan→Jul actual change, trend R²,
  naive-vs-corrected recovery rate gap, targeting-strategy DiD effect.
- **Recovered amount trend** (matplotlib line chart, MoM% annotated at
  each point) and **naive vs. corrected recovery rate** (two-line
  comparison) side by side.
- **Channel conversion** (bar rows), **mix-adjustment check** (table),
  **counterfactual DiD** (table) — three columns.
- **₹10 Cr investment recommendation** box with ROI assumptions and an
  honest confidence caveat.

## Notes

- Charts are rendered with matplotlib (`st.pyplot`) rather than Streamlit's
  native chart types, to match the exact annotated look of the original
  HTML version (MoM% labels on each point, dual-line comparison with a
  legend, consistent color coding).
- Card styling (KPI tiles, verdict banner, investment box) uses small
  injected CSS blocks via `st.markdown(..., unsafe_allow_html=True)` to
  mirror the HTML dashboard's visual language; chart/table cards use
  Streamlit's native `st.container(border=True)`.
- This app was validated by executing it against a stub of the Streamlit
  API (to catch data/logic errors offline) and by rendering both
  matplotlib charts to image — but it has not been run against a live
  Streamlit server. Please run `streamlit run app.py` once in your own
  environment to confirm.
