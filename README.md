
# Franchisee Agentic Enrichment Pipeline

Accelerate FDD analysis by turning a raw FDD information table into a fully-enriched, prospect-ready dataset-complete with corporate roll-ups, owner  details, contact info and a built-in confidence score - in one run.

**What the pipeline adds**

* **Legal roll-up** — headless browser (Stagehand + Browserbase) hits **OpenCorporates** to fetch the parent LLC, registered address and agent.  
* **Direct outreach data** — **Perplexity Sonar Chat API** supplies working phone, email **and the owner’s personal LinkedIn profile** (never the company page).  
* **Confidence scoring** — each row gets a 0-to-1 score so you can filter or route low-quality leads.  
* **Ready for BI** — writes an enriched spreadsheet and a BigQuery-friendly CSV.

---

## Expected input columns

The script assumes the standard FDD location extract with the columns below
(**bold = actually used for enrichment**):

| Column               | Example                | Notes |
|----------------------|------------------------|-------|
| `FDD`                | *“Golden Chick”*       | Brand, informational |
| `FDD Store No.`      | — _(empty)_            | Ignore if blank|
| `FDD Location Name`  | — _(empty)_            | Ignored if blank |
| **`Franchisee`**     | *“Bo Stover, LLC”*     | Owner or LLC name (core lookup key) |
| `FDD Contact Name`   | — _(empty)_            | Not used |
| `Address`            | *“1001 W University Dr.”* | Preserved |
| `City`               | *“McKinney”*           | Preserved |
| **`State`**          | *“TX”*                 | Two-letter US abbreviation Used (core lookup key) |
| `Zip`                | *75069*                | Preserved |
| `Phone`              | *(972) 548-9600*       | Preserved |

All other columns in the sheet are passed through unchanged.

---

## Repo Layout
```
repo/
├── .env.example            # template for all required API keys
├── requirements.txt
├── input/                  # sample input file(s)
│   └── franchise_input.xlsx
├── src/
│   └── enrichment/
│       └── __init__.py     # full enrichment logic
└── scripts/
    └── enrich_franchise.py     # CLI entry‑point
```

---

## Local Setup
> **Prerequisites:** Python 3.9+, git, Chrome/Chromium libs.

```bash
# 1 clone & enter
git clone <your‑repo‑url>
cd repo

# 2 create virtual‑env
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# 3 install dependencies
pip install -r requirements.txt
playwright install chromium   # Stagehand browser

# 4 add secrets
cp .env.example .env
# edit .env and set:
#   MODEL_API_KEY=<OpenAI key>            # used by Stagehand agent
#   PERPLEXITY_API_KEY=<Perplexity key>
#   BROWSERBASE_PROJECT_ID=6             # your Browserbase project id
#   BROWSERBASE_API_KEY=<browserbase key>
```

> **Where to get the keys:**

• OpenAI (MODEL_API_KEY) – create an API key at https://platform.openai.com/account/api-keys

• Perplexity – request a Sonar API key via https://www.perplexity.ai/api

• Browserbase – sign up at https://browserbase.com, create project 6 (free tier), copy project id and API key.

Stagehand loads MODEL_API_KEY, BROWSERBASE_API_KEY, and BROWSERBASE_PROJECT_ID from the environment to start its cloud-browser sessions. Perplexity calls require PERPLEXITY_API_KEY.

---

## Run the Pipeline
```bash
python scripts/enrich_franchise.py       --input  input/franchise_input.xlsx       --output output/enriched.xlsx
```

---

## Output Columns

| Column            | Source            | Notes                                                  |
|-------------------|-------------------|--------------------------------------------------------|
| Corporate Name    | OpenCorporates    | LLC / Inc name / N/A                                   |
| Corporate Address | OpenCorporates    | registered address / N/A                               |
| Franchisee Owner  | OpenCorporates    | agent / manager / N/A                                  |
| Corporate Phone   | Perplexity        | Fall back to parent franchse if not found              |
| Corporate Email   | Perplexity        | Fall back to parent franchse if not found              |
| LinkedIn          | Perplexity        | personal `/in/…` URL else ""; company pages discarded  |
| url Sources       | OC URL + PPLX     | comma‑sep, deduplicated                                |
| Confidence        | calculated (0–1)  | fraction of 6 enriched fields that are non‑fallback    |

---

## Cloud Architecture (high level)

1. **Cloud Storage** – receives raw .xlsx files
2. **Cloud Function** – fires a Pub/Sub message for each new file
3. **Pub/Sub** – queues work to decouple upload and processing
4. **Cloud Run Job** – pulls message, runs enrichment.main() in parallel
5. **Cloud Storage (enriched)** – stores enriched.xlsx + deadletter.csv
6. **BigQuery** – external table over enriched files, powering Looker
7. **Cloud Monitoring** – logs & alerts on job failure or DLQ volume

See `architecture.png` + `ARCHITECTURE.md` for details.


## Sample “url Sources” Outputs

These rows illustrate the kinds of source links the enrichment pipeline
collects (OpenCorporates, professional directories, company contact pages).

| Example Row | URL |
|-------------|-----|
| **Row 1** | https://opencorporates.com/companies/us_tx/0090725202 |
|           | https://www.texasbar.com/attorneys/member.cfm?id=222487 |
| **Row 2** | https://www.goldenchick.com/contact-us |
|           | https://opencorporates.com/companies/us_tx/0801979572 |
| **Row 3** | https://www.zoominfo.com/pic/golden-tree-maintenance/371566340 |
|           | https://www.tad.org/search-results?searchType=GeoReference&query=35112 |
|           | https://opencorporates.com/companies/us_tx/0802771753 |
|           | http://goldentreematerials.com/contact-us/ |
|           | http://goldentreemaintenance.com/contact-us/ |
| **Row 4** | https://www.yellowpages.com/belton-tx/mip/bo-stover-enterprises-inc-483305366 |
|           | https://opencorporates.com/companies/us_tx/0802323589 |

> These links are **examples only** and not required to run the code. They serve
> as reference for reviewers who want to see typical enrichment sources.


---

## License
GNU General Public License v3.0
