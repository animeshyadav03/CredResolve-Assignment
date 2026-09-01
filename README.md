# Collections Recovery Analysis

**The question I was asked to answer:** is the reported "+11% month-on-month recovery improvement" real?

**Short answer:** no. It's a single good month (Feb to Mar) sitting inside a flat, noisy seven-month series. The full breakdown is in `executive_memo.docx` and `collections_analysis.ipynb`.

## What's in this repo

| File / folder | What it is |
|---|---|
| `executive_memo.docx` | Start here. Two pages covering what happened, why, how confident I am, and what I'd recommend. |
| `executive_dashboard.html` | One screen, opens in any browser, meant to be read in about a minute. |
| `collections_analysis.ipynb` | The full analysis — data forensics, statistical tests, the counterfactual, every chart and every bit of reasoning behind them. |
| `data_quality_report.md` | Every data issue I found, how I found it, how I handled it, and how much it actually mattered. |
| `architecture_diagram.svg` | How I'd build this as a production pipeline (raw to staging to clean to golden to feature to metrics to dashboard). |
| `sql/` | The SQL behind all of this: `01_staging.sql`, `02_cleaning_dedup.sql`, `03_golden_views.sql`, `04_metrics.sql`, `05_analytical_queries.sql` |
| `etl/` | The Python that actually built the golden dataset: `build_golden_dataset.py`, `compute_metrics.py`, `build_notebook.py` |
| `golden_dataset/` | The cleaned tables as CSVs, plus `etl_log.json`, which logs every cleaning decision I made and what it changed. |

## Suggested reading order

1. **Executive memo** (2 min) — the verdict and what to do about it.
2. **Executive dashboard** (1 min) — same story, visual, easy to share.
3. **Notebook** (15–20 min) — every test, every number, every chart, and the reasoning behind each one.
4. **Data quality report** — for anyone who wants to push back on how I cleaned the data.
5. **SQL and architecture diagram** — for whoever has to turn this into something that runs in production.

## What I actually found

- The "+11%" number lines up almost exactly with the Feb to Mar jump. Look at the full Jan to Jul trend and it's essentially flat (R² of 0.004) and net down about 2%.
- I tested three obvious alternative explanations — a shift in portfolio mix, a mid-year change in targeting strategy (difference-in-differences estimate came out to -0.51pp, not significant), and denominator manipulation — and ruled all three out.
- I also caught a real measurement bug: the old "recovered divided by worked" formula overstates the true recovery rate by 2.5 to 2.9 percentage points every single month, which is roughly 30% inflation. Any dashboard that's been using that definition has been reporting numbers that were too optimistic, consistently.
- The `agents` and `borrowers` tables are basically broken past their ID columns — 1,000 real agents somehow produce 30,000 conflicting rows, and only 10 distinct names show up across all of them. I documented this and worked around it rather than quietly ignoring it.
- My recommendation for where to put the ₹10 Cr: **Field Operations**. I'd flag this as low to medium confidence though — the conversion edge over other channels is only about 0.3 percentage points — so I'd want a four-week A/B test before committing the full amount.
