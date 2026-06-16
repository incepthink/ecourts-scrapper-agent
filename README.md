# eCourts Advocate Collector

Scrapes India's eCourts District Courts portal (`ecourtindia_v6`) **by advocate
name**, stores each advocate's disposed cases with the court's **outcome
("Nature of Disposal" = win/loss signal)**, and downloads the final
order/judgement PDFs. Built to power a "find lawyers who won similar cases"
product. For each advocate it searches **every court complex in the configured
district** so coverage is complete. Current scope: **Mumbai CMM Courts** (all 16
Metropolitan Magistrate complexes).

Built on the [`bharat-courts`](https://pypi.org/project/bharat-courts/) library
(reused for session / token / CAPTCHA / hierarchy), extended here with the
**advocate-name search** (which the library lacks) and the
case-history → order-PDF download chain.

## Setup

Requires **Python 3.12** (the OCR dep `ddddocr`/`onnxruntime` has no 3.14 wheels).

```bash
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
```

## Usage

```bash
P=.venv/Scripts/python
$P src/cli.py init-db                      # create the SQLite DB
$P src/cli.py run-name "Nizam"             # search one advocate, ingest cases + PDFs
$P src/cli.py seed "Patil" "Shaikh"        # queue names for the crawl
$P src/cli.py run --limit 5                # process 5 queued names (self-expands)
$P src/cli.py run --limit 5 --no-pdf       # skip PDF downloads (faster)
$P src/cli.py stats                        # row counts
$P src/report.py                           # human-readable dump of enriched cases
```

## How it works

1. `casestatus/submitAdvName` (CAPTCHA via OCR) → results HTML in `adv_data`.
2. Parse rows → cases + advocates + the `viewHistory(...)` args.
3. `home/viewHistory` → case history → status, **nature of disposal**, orders.
4. `home/display_pdf` → order PDF path → download (validated `%PDF`).
5. Advocate names found in results are queued (`seed_names`) to self-expand.

## Data (SQLite by default, MySQL-ready)

`advocates`, `cases` (one per CNR, incl. `nature_of_disposal`), `case_advocates`,
`orders` (with downloaded PDF path), `seed_names` (crawl queue).

Switch to MySQL with **one env var** (no code/schema change):
```bash
ECOURTS_DB_URL=mysql+pymysql://user:pass@localhost:3306/ecourts
```

## District selection

Set `STATE_CODE` + `DISTRICT_NAME` in [`src/config.py`](src/config.py). The
district is **resolved by name** to its code against the live portal dropdown
(bharat-courts' hardcoded state map is stale), then **all** of its court
complexes are searched per advocate. `DISTRICT_NAME` is a case-insensitive
substring and must match exactly one district. Default: Maharashtra (`1`) /
`"Mumbai CMM Courts"` (code `23`, 16 complexes).

## Notes / caveats

- Solving the CAPTCHA circumvents an anti-automation control (ToS gray area);
  data is public court record. Be polite: default ≥1s request delay, single-threaded.
- The portal generates the order PDF on the `display_pdf` call, so the first
  download can 404 — `fetch_order_pdf` retries.
- Wide searches have no pagination; advocate search is naturally scoped.
- `src/_debug_*.py`, `src/_test_*.py`, `src/_check_*.py` are throwaway
  reverse-engineering scripts — safe to delete.

## Next (not built yet)

- AI extraction of the "winning path" (steps/arguments) from order PDFs.
- TypeScript/Next.js frontend reading this DB: advocate win/loss profiles +
  "lawyers who won similar cases".
