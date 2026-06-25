"""
HubSpot → Geocode → stores.json
================================
This script:
1. Pulls companies from a specific HubSpot List (ID 458)
2. Geocodes each address using Nominatim (OpenStreetMap, free, no API key)
3. Saves the result as stores.json for use in the store locator widget

SETUP:
  pip3 install requests

USAGE:
  python3 hubspot_geocode.py
"""

import json
import time
import os
import requests

# ── CONFIG ──────────────────────────────────────────────────────────────────
HUBSPOT_TOKEN = os.environ.get("HUBSPOT_TOKEN", "YOUR_TOKEN_HERE")
LIST_ID       = 458

PROPS = ["name", "address", "city", "state", "zip", "phone", "website"]

OUTPUT_FILE = "stores.json"
GEOCODE_DELAY = 1.1  # seconds between geocoding (Nominatim rate limit)

# ── HUBSPOT: FETCH COMPANIES IN LIST 458 ─────────────────────────────────────
def fetch_hubspot_companies():
    print(f"Fetching companies from HubSpot List {LIST_ID}...")
    headers = {"Authorization": f"Bearer {HUBSPOT_TOKEN}"}
    companies = []
    after = None

    while True:
        url = f"https://api.hubapi.com/crm/v3/lists/{LIST_ID}/memberships"
        params = {"limit": 100}
        if after:
            params["after"] = after

        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()

        # Collect company IDs from this page
        record_ids = [str(m["recordId"]) for m in data.get("results", [])]

        if record_ids:
            # Batch fetch full company details
            batch_url = "https://api.hubapi.com/crm/v3/objects/companies/batch/read"
            batch_body = {
                "inputs": [{"id": rid} for rid in record_ids],
                "properties": PROPS
            }
            batch_resp = requests.post(batch_url, headers=headers, json=batch_body)
            batch_resp.raise_for_status()
            batch_data = batch_resp.json()

            for result in batch_data.get("results", []):
                props = result.get("properties", {})
                companies.append({
                    "id": result["id"],
                    "name":    props.get("name", ""),
                    "address": props.get("address", ""),
                    "city":    props.get("city", ""),
                    "state":   props.get("state", ""),
                    "zip":     props.get("zip", ""),
                    "phone":   props.get("phone", ""),
                    "website": props.get("website", ""),
                })

        print(f"  Fetched {len(companies)} companies so far...")

        paging = data.get("paging", {})
        after  = paging.get("next", {}).get("after")
        if not after:
            break

    print(f"Total companies fetched: {len(companies)}")
    return companies


# ── GEOCODING VIA NOMINATIM (FREE, NO KEY) ───────────────────────────────────
def geocode_address(store):
    candidates = []

    if store.get("address") and store.get("city"):
        full = f"{store['address']}, {store['city']}, {store['state']} {store['zip']}"
        candidates.append(full.strip(", "))

    if store.get("city") and store.get("state"):
        candidates.append(f"{store['city']}, {store['state']} {store['zip']}".strip())

    if store.get("zip"):
        candidates.append(store["zip"])

    headers = {"User-Agent": "StoreLocator/1.0 (your@email.com)"}

    for query in candidates:
        if not query.strip():
            continue
        try:
            resp = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "json", "limit": 1, "countrycodes": "us"},
                headers=headers,
                timeout=10,
            )
            results = resp.json()
            if results:
                return float(results[0]["lat"]), float(results[0]["lon"])
        except Exception as e:
            print(f"    Geocode error for '{query}': {e}")

        time.sleep(GEOCODE_DELAY)

    return None, None


# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    companies = fetch_hubspot_companies()

    print("\nGeocoding addresses (this takes ~8-10 min for 450 locations)...")
    stores = []
    failed = []

    for i, company in enumerate(companies):
        name = company.get("name") or f"Store #{company['id']}"
        print(f"  [{i+1}/{len(companies)}] {name}")

        lat, lng = geocode_address(company)

        if lat is None:
            print(f"    ⚠ Could not geocode: {company.get('address')}, {company.get('city')}")
            failed.append(company)
        else:
            company["lat"] = lat
            company["lng"] = lng
            stores.append(company)

        time.sleep(GEOCODE_DELAY)

    with open(OUTPUT_FILE, "w") as f:
        json.dump(stores, f, indent=2)

    print(f"\n✅ Done! {len(stores)} stores saved to {OUTPUT_FILE}")

    if failed:
        with open("geocode_failures.json", "w") as f:
            json.dump(failed, f, indent=2)
        print(f"⚠  {len(failed)} locations could not be geocoded → geocode_failures.json")
        print("   Fix their addresses in HubSpot and re-run, or add lat/lng manually.")

if __name__ == "__main__":
    main()
