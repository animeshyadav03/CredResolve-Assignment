# Collections Recovery Analysis — Deliverables

**Question:** Is the reported "+11% month-on-month recovery improvement" real?
**Answer:** No — it's one month's bounce (Feb→Mar) inside a flat, noisy
7-month series. Full details in `executive_memo.docx` and
`collections_analysis.ipynb`.

## Contents

| File / folder | What it is |
|---|---|
| `executive_memo.docx` | **Start here.** 2-page memo: what happened, why, confidence, recommendation. |
| `executive_dashboard.html` | One-screen dashboard — open in any browser. |
| `collections_analysis.ipynb` | Full analysis notebook: data forensics, statistical tests, counterfactual, all charts, all reasoning. |
| `data_quality_report.md` | Every data-quality issue found, detection method, treatment, quantified impact. |
| `architecture_diagram.svg` | Production pipeline design (Raw→Staging→Clean→Golden→Feature→Metrics→Dashboard), open in a browser or image viewer. |
| `sql/` | SQL repository: `01_staging.sql`, `02_cleaning_dedup.sql`, `03_golden_views.sql`, `04_metrics.sql`, `05_analytical_queries.sql` |
| `etl/` | Python pipeline that actually built the golden dataset: `build_golden_dataset.py`, `compute_metrics.py`, `build_notebook.py` |
| `golden_dataset/` | The cleaned analytical tables (CSV) + `etl_log.json` (every cleaning decision, quantified) |

## How to read this in order

1. **Executive Memo** (2 min) — the verdict and the recommendation.
2. **Executive Dashboard** (1 min) — the same story as a visual, shareable screen.
3. **Notebook** (15–20 min) — every test, every number, every chart, with reasoning.
4. **Data Quality Report** — for anyone who wants to interrogate the cleaning decisions.
5. **SQL repository + architecture diagram** — for the engineering team to productionize this.

## Headline findings

- The "+11%" matches the Feb→Mar month-pair almost exactly. The full
  Jan–Jul trend is statistically flat (R² = 0.004) and net **down** ~2%.
- Portfolio mix shift, a targeting-strategy change (DiD estimate: -0.51pp,
  not significant), and denominator manipulation were each tested and
  **ruled out** as explanations for the swings.
- A real measurement bug was found and fixed: the naive "recovered ÷
  worked" ratio overstates the true recovery rate by 2.5–2.9 points every
  month (~30% relative inflation) — any historical dashboard using that
  definition has been running optimistic.
- The `agents` and `borrowers` dimension tables are unusable beyond their
  ID columns (1,000 real agents produce 30,000 conflicting rows, only 10
  distinct names exist across all of them) — documented and worked around,
  not silently ignored.
- ₹10 Cr investment recommendation: **Field Operations**, with an honest
  low–medium confidence caveat (the channel-conversion edge is only ~0.3pp)
  and a recommended 4-week A/B test before committing the full amount.
