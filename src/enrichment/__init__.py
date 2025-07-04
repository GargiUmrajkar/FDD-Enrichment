"""
End-to-end franchisee enrichment

• Stagehand ⟶ OpenCorporates → corporate name, address, owner, OC URL
• Perplexity Chat API        → phone, email, LinkedIn, extra URLs
• Writes combined data back to Excel
"""

import asyncio
import json
import os
import re
from typing import List, Union

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel
from stagehand import Stagehand, StagehandConfig
from playwright.async_api import TimeoutError as PlaywrightTimeoutError  

# ───────────────────────────  ENV & PERPLEXITY  ────────────────────────────
load_dotenv()

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
MODEL_API_KEY      = os.getenv("MODEL_API_KEY")       

pplx_client = OpenAI(api_key=PERPLEXITY_API_KEY,
                     base_url="https://api.perplexity.ai")

FALLBACK_CONTACT = {
    "corporate_phone": "(972) 831-0911",
    "corporate_email": "gfcinfo@goldenchick.com",
    "linkedin_url":   "",
    "url Sources":    ["https://www.goldenchick.com/contact-us"],
}

def enrich_contact_info(franchise_name: str, address: str, owner_name: str) -> dict:
    """
    Query Perplexity for phone, email, LinkedIn; fall back if nothing usable.
    """
    prompt = f"""
You are an AI assistant tasked with finding real-time contact information using the web.

1. Search for business contact info (email, phone) for this specific franchise location:
   • Franchise: {franchise_name}
   • Address: {address}

2. If unavailable, search for contact info for the owner:
   • Owner: {owner_name}

3. Find the **owner’s personal LinkedIn profile and make sure that owner's LinkedIn URL actually has the franchise name associated with it** (URL must contain “/in/”,
   not “/company/”). If the owner is an LLC, look for the manager/agent’s
   personal profile.

4. Return only fields you are confident about. Include the URLs where each datum was found
   in an array called "url Sources".

Return JSON only:
{{"corporate_phone":"...", "corporate_email":"...", "linkedin_url":"...",
  "url Sources":["https://..."]}}
"""
    try:
        resp = pplx_client.chat.completions.create(
            model="sonar-pro",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        raw = resp.choices[0].message.content
        cleaned = re.sub(r"^```json|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        data = json.loads(cleaned or "{}")
        # ── ensure LinkedIn is a personal profile ─────────────────────────
        lnk = data.get("linkedin_url", "")
        if lnk and "/company/" in lnk.lower():
            data["linkedin_url"] = ""          # discard company pages

    except Exception as e:
        print(f"Perplexity error: {e}")
        data = {}

    return {
        "corporate_phone": data.get("corporate_phone") or FALLBACK_CONTACT["corporate_phone"],
        "corporate_email": data.get("corporate_email") or FALLBACK_CONTACT["corporate_email"],
        "linkedin_url":    data.get("linkedin_url")    or FALLBACK_CONTACT["linkedin_url"],
        "url Sources":     data.get("url Sources")     or FALLBACK_CONTACT["url Sources"],
    }

# ────────────────────────────  STAGEHAND PART  ─────────────────────────────
class CompanyInfo(BaseModel):
    corporate_name: str
    registered_address: str
    owner_name: Union[str, List[dict]]
    source_url: str

async def enrich_opencorporates(franchise_name: str, state_abbr: str) -> dict:
    """
    Original Stagehand-scraper you provided (no logic changed).
    """
    config = StagehandConfig(
        env="BROWSERBASE",
        model_name="openai/gpt-4.1-mini",
        model_client_options={"apiKey": MODEL_API_KEY},
    )

    stagehand = Stagehand(config)
    try:
        await stagehand.init()
        page = stagehand.page

        await page.goto("https://opencorporates.com/")
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(2)

        search_input = page.locator('input[name="q"]')
        await search_input.wait_for(state="visible", timeout=5000)
        await search_input.fill(franchise_name)
        await search_input.press("Enter")

        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(2)

        await page.act(
            f"Click the company link whose address contains the state abbreviation {state_abbr}"
        )
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(2)

        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(3)

        source_url = page.url

        corporate_name = "N/A"
        try:
            h1 = await page.query_selector("h1.wrapping_heading.fn.org")
            corporate_name = await h1.inner_text() if h1 else "N/A"
        except:
            pass

        registered_address = "N/A"
        try:
            li_list = await page.query_selector_all(
                "dd.registered_address.adr ul.address_lines li.address_line"
            )
            address_parts = [await li.inner_text() for li in li_list]
            registered_address = ", ".join(address_parts) if address_parts else "N/A"
        except:
            pass

        owner_name = "N/A"
        try:
            agent_el = await page.query_selector("dd.agent_name")
            if agent_el:
                owner_name = await agent_el.inner_text()
        except:
            pass

        return CompanyInfo(
            corporate_name=corporate_name,
            registered_address=registered_address,
            owner_name=owner_name,
            source_url=source_url,
        ).model_dump()

    finally:
        await stagehand.close()

# ──────────────────────────────  MAIN LOOP  ────────────────────────────────
async def process_excel(input_path: str, output_path: str) -> None:
    df = pd.read_excel(input_path)

    # Ensure the Perplexity columns exist
    for col in ["Corporate Phone", "Corporate Email", "LinkedIn"]:
        if col not in df.columns:
            df[col] = ""

    for idx, row in df.iterrows():
        franchise = str(row["Franchisee"]).strip()
        state     = str(row["State"]).strip()

        if not franchise or pd.isna(franchise):
            continue

        print(f"Row {idx+1}: {franchise} ({state})")

        # ── Stagehand enrichment ────────────────────────────────
        try:
            enriched = await enrich_opencorporates(franchise, state)
        except Exception as e:
            print(f"Stagehand error: {e}")
            enriched = {
                "corporate_name": "N/A",
                "registered_address": "N/A",
                "owner_name": "N/A",
                "source_url": "",
            }

        # Write Stagehand fields
        df.at[idx, "Corporate Name"]    = enriched["corporate_name"]
        df.at[idx, "Corporate Address"] = enriched["registered_address"]
        df.at[idx, "Franchisee Owner"]  = enriched["owner_name"]
        df.at[idx, "url Sources"]       = enriched["source_url"]

        # ── Perplexity enrichment ───────────────────────────────
        contact = enrich_contact_info(
            franchise_name=franchise,
            address=state,
            owner_name=enriched["owner_name"],
        )
        df.at[idx, "Corporate Phone"]  = contact["corporate_phone"]
        df.at[idx, "Corporate Email"]  = contact["corporate_email"]
        df.at[idx, "LinkedIn"]         = contact["linkedin_url"]

        # Merge URL lists (avoid duplicates)
        combined_urls = set(
            str(df.at[idx, "url Sources"]).split(", ")
            + contact["url Sources"]
        )
        df.at[idx, "url Sources"] = ", ".join(u for u in combined_urls if u)

        # ➋ ── compute confidence score ────────────────────────────
        stagehand_vals = [
            enriched["corporate_name"],
            enriched["registered_address"],
            enriched["owner_name"],
        ]
        contact_vals = [
            contact["corporate_phone"],
            contact["corporate_email"],
            contact["linkedin_url"],
        ]

        # helper: is the value missing or a known fallback?
        fallback_contact_vals = [
            FALLBACK_CONTACT["corporate_phone"],
            FALLBACK_CONTACT["corporate_email"],
            "",
        ]
        def _good(v: str, fallback_pool: list[str]) -> bool:
            return v not in ("", "N/A") and v not in fallback_pool

        good_fields = sum(_good(v, []) for v in stagehand_vals) + \
                      sum(_good(v, fallback_contact_vals) for v in contact_vals)

        confidence = round(good_fields / 6, 2)  
        df.at[idx, "Confidence"] = confidence

    df.to_excel(output_path, index=False)
    print(f"\n Output saved to {output_path}")

# ──────────────────────────────  CLI ENTRY  ───────────────────────────────
def main() -> None:
    import argparse, pathlib
    ap = argparse.ArgumentParser()
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    default_in  = repo_root / "input" / "franchise_input.xlsx"
    default_out = repo_root / "output" / "franchise_data_enriched.xlsx"

    ap.add_argument("--input",  default=str(default_in))
    ap.add_argument("--output", default=str(default_out))
    args = ap.parse_args()

    asyncio.run(process_excel(args.input, args.output))

if __name__ == "__main__":
    main()

