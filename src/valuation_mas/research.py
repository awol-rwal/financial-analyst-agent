"""Research stage: collect and register evidence, without inventing sources.

MVP scope: user-supplied JSON documents (or SEC-imported JSON). Future search
providers can be plugged in here. Do not let a model invent source URLs.
"""

from .models import SourceDocument, AnalysisInput


SOURCE_PRIORITY = {
    "regulatory_filing": 0,
    "company_report": 1,
    "reputable_news": 2,
    "other": 3,
    "synthetic_demo": 4,
}


def research(input_data: AnalysisInput) -> tuple[list[SourceDocument], list[str]]:
    sources = sorted(
        input_data.sources,
        key=lambda source: (SOURCE_PRIORITY[source.source_type.value], source.source_id),
    )
    notes = []
    ids = {source.source_id for source in sources}
    if len(ids) != len(sources):
        notes.append("Duplicate source IDs: each document needs a unique source ID.")
    for year in input_data.historical_financials:
        if year.source_id not in ids:
            notes.append(f"FY{year.year}: financial data points to missing source {year.source_id!r}.")
    if input_data.is_synthetic_demo:
        notes.append("DEMO ONLY: all source evidence and financial figures are synthetic.")
    return sources, notes
