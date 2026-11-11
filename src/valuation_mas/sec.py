"""Optional SEC XBRL loader for US-listed reporting companies.

This importer is intentionally cautious. Many US GAAP companyfacts concepts are
issuer-specific. Unavailable data is LEFT NULL rather than guessed. Review the
original 10-K before turning the exported starter JSON into a valuation input.
"""

import json
from datetime import date
from urllib.request import Request, urlopen


TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"


def get_json(url: str, email: str):
    req = Request(url, headers={
        "User-Agent": f"valuation-mas research {email}",
        "Accept": "application/json",
        "Accept-Encoding": "identity",
    })
    with urlopen(req, timeout=25) as response:
        return json.load(response)


def annual_record(companyfacts: dict, concepts: list[str], year: int,
                  unit: str = "USD", flow: bool = True):
    """Pick the latest-filed 10-K observation for a specific full fiscal year.

    For flows, require a period of roughly 12 months. For balances, use the
    year-end value. We return provenance to make manual review possible.
    """
    rows = []
    for concept in concepts:
        entry = companyfacts.get("facts", {}).get("us-gaap", {}).get(concept, {})
        items = entry.get("units", {}).get(unit, [])
        for item in items:
            if item.get("form") != "10-K" or not item.get("end", "").startswith(str(year)):
                continue
            if flow:
                if not item.get("start"):
                    continue
                span = (date.fromisoformat(item["end"]) - date.fromisoformat(item["start"])).days
                if not 330 <= span <= 380:
                    continue
            else:
                if item.get("start"):
                    continue
            rows.append((item.get("filed", ""), concept, item))
    if not rows:
        return None, "Missing matching SEC XBRL tag"
    # Prefer most recent filing for the same fiscal period, not the latest quarter.
    _, concept, chosen = sorted(rows, key=lambda row: row[0], reverse=True)[0]
    return chosen.get("val"), f"us-gaap:{concept}, accession {chosen.get('accn', 'unknown')}"


def make_sec_template(ticker: str, email: str, years: int = 3) -> dict:
    if not 1 <= years <= 10:
        raise ValueError("years must be between 1 and 10")
    directory = get_json(TICKERS_URL, email)
    item = next((row for row in directory.values() if row["ticker"].upper() == ticker.upper()), None)
    if not item:
        raise ValueError(f"Ticker not found in SEC directory: {ticker}")
    cik = item["cik_str"]
    url = COMPANYFACTS_URL.format(cik=cik)
    facts = get_json(url, email)
    available = sorted({
        int(x.get("end", "")[:4])
        for fact in facts.get("facts", {}).get("us-gaap", {}).values()
        for per_unit in fact.get("units", {}).values()
        for x in per_unit
        if x.get("form") == "10-K" and x.get("end", "")[:4].isdigit()
    }, reverse=True)
    history = []
    for year in sorted(available[:years]):
        tags = {
            "revenue": (["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"], True),
            "ebit": (["OperatingIncomeLoss"], True),
            "depreciation_amortization": (["DepreciationDepletionAndAmortization",
                                           "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment"], True),
            "capex": (["PaymentsToAcquirePropertyPlantAndEquipment"], True),
            "cash": (["CashAndCashEquivalentsAtCarryingValue"], False),
            "debt": (["LongTermDebt", "LongTermDebtNoncurrent"], False),
        }
        picked = {}
        notes = []
        for key, (concepts, flow) in tags.items():
            number, provenance = annual_record(facts, concepts, year, flow=flow)
            picked[key] = number / 1_000_000 if number is not None else None
            notes.append(f"{key}: {provenance}")
        shares, provenance = annual_record(facts, ["CommonStockSharesOutstanding"], year,
                                           unit="shares", flow=False)
        picked["shares_outstanding"] = shares / 1_000_000 if shares is not None else None
        notes.append(f"shares: {provenance}")
        history.append({
            "year": year, **picked,
            "change_in_nwc": None,  # Can't safely infer from a single GAAP tag.
            "source_id": "sec_companyfacts", "units": "millions",
            "page_reference": "SEC companyfacts API; review original 10-K",
            "notes": "; ".join(notes),
        })
    return {
        "company_name": item["title"], "ticker": ticker.upper(), "currency": "USD",
        "valuation_date": date.today().isoformat(), "is_synthetic_demo": False,
        "sources": [{"source_id": "sec_companyfacts", "title": "SEC companyfacts XBRL (not a full 10-K review)",
                     "url": url, "source_type": "regulatory_filing", "date": None,
                     "notes": "Cross-check each tag, cash/debt, and shares against the original 10-K."}],
        "historical_financials": history,
        "capital": {"tax_rate": None, "risk_free_rate": None, "beta": None,
                    "equity_risk_premium": None, "pre_tax_cost_of_debt": None,
                    "debt_weight": None,
                    "reasoning": "REQUIRED: independently source and justify capital costs.",
                    "supporting_evidence": ["sec_companyfacts"]},
        "scenarios": {
            name: {"revenue_growth": None, "ebit_margin": None,
                   "da_as_pct_of_revenue": None, "capex_as_pct_of_revenue": None,
                   "nwc_investment_as_pct_revenue": None, "terminal_growth": None,
                   "wacc_adjustment": 0,
                   "reasoning": f"REQUIRED: {name} forecast justification and sources",
                   "supporting_evidence": ["sec_companyfacts"]}
            for name in ("bear", "base", "bull")
        },
        "forecast_years": 5, "market_price": None,
        "_read_me": "Template intentionally contains null values: do not run until all required fields are verified and filled.",
    }
