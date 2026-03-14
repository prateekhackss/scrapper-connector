"""
ConnectorOS Scout — Company Deduplicator

Normalizes domains and uses fuzzy name matching to merge duplicate
company records from different sources.

Security:
  - No external API calls — pure in-memory computation
  - Domain normalization prevents injection of variant spellings
"""

from __future__ import annotations

from urllib.parse import urlparse

from thefuzz import fuzz

from core.models import CompanyBase
from core.logger import get_logger

logger = get_logger("discovery.deduplicator")

# Minimum Levenshtein similarity ratio to consider two company names a match
FUZZY_THRESHOLD = 85

# Common suffixes to strip before fuzzy matching
_COMPANY_SUFFIXES = [
    " inc.", " inc", " ltd.", " ltd", " llc", " corp.", " corp",
    " co.", " co", " plc", " gmbh", " ag", " sa", " sas",
    " pvt.", " pvt", " private limited", " limited",
    " technologies", " technology", " tech", " software",
    " solutions", " labs", " io",
]


def normalize_domain(raw: str) -> str:
    """
    Normalize a domain to a canonical form for deduplication.
    Strips protocol, www., trailing slash, query params.
    """
    domain = raw.strip().lower()

    # Remove protocol
    for prefix in ("https://", "http://"):
        if domain.startswith(prefix):
            domain = domain[len(prefix):]

    # Remove www.
    if domain.startswith("www."):
        domain = domain[4:]

    # Remove path, query, fragment
    domain = domain.split("/")[0].split("?")[0].split("#")[0]

    return domain.rstrip(".")


def _clean_company_name(name: str) -> str:
    """Strip common legal/corporate suffixes for better fuzzy matching."""
    clean = name.strip().lower()
    for suffix in _COMPANY_SUFFIXES:
        if clean.endswith(suffix):
            clean = clean[: -len(suffix)].strip()
    return clean


def _merge_company(existing: CompanyBase, new: CompanyBase) -> CompanyBase:
    """Merge two company records, keeping the most complete data."""
    # Keep the longer / more descriptive name
    if len(new.company_name) > len(existing.company_name):
        existing.company_name = new.company_name

    # Merge optional fields — prefer non-None
    if new.website_url and not existing.website_url:
        existing.website_url = new.website_url
    if new.industry and not existing.industry:
        existing.industry = new.industry
    if new.headquarters and not existing.headquarters:
        existing.headquarters = new.headquarters
    if new.employee_count and not existing.employee_count:
        existing.employee_count = new.employee_count

    # Union tech stacks
    existing_set = set(existing.tech_stack)
    for tech in new.tech_stack:
        if tech not in existing_set:
            existing.tech_stack.append(tech)
            existing_set.add(tech)

    # Union discovery sources
    existing_sources = set(existing.discovery_sources)
    for src in new.discovery_sources:
        if src not in existing_sources:
            existing.discovery_sources.append(src)
            existing_sources.add(src)

    return existing


def deduplicate_companies(companies: list[CompanyBase]) -> list[CompanyBase]:
    """
    Deduplicate a list of companies by:
    1. Primary: exact domain match
    2. Secondary: fuzzy name match (Levenshtein ≥ 85%)

    Merged records keep the union of tech_stack, discovery_sources,
    and the most complete data from both records.

    Args:
        companies: List of potentially duplicate company records.

    Returns:
        Deduplicated list of companies.
    """
    # Phase 1: Group by normalized domain
    domain_map: dict[str, CompanyBase] = {}

    for company in companies:
        domain = normalize_domain(company.company_domain)
        company.company_domain = domain  # Normalize in place

        if domain in domain_map:
            domain_map[domain] = _merge_company(domain_map[domain], company)
        else:
            domain_map[domain] = company

    # Phase 2: Fuzzy name matching across remaining unique entries
    unique = list(domain_map.values())
    merged_indices: set[int] = set()

    for i in range(len(unique)):
        if i in merged_indices:
            continue
        name_i = _clean_company_name(unique[i].company_name)

        for j in range(i + 1, len(unique)):
            if j in merged_indices:
                continue
            name_j = _clean_company_name(unique[j].company_name)

            similarity = fuzz.ratio(name_i, name_j)
            if similarity >= FUZZY_THRESHOLD:
                logger.info(
                    "dedup_fuzzy_merge",
                    company_a=unique[i].company_name,
                    company_b=unique[j].company_name,
                    similarity=similarity,
                )
                unique[i] = _merge_company(unique[i], unique[j])
                merged_indices.add(j)

    result = [c for idx, c in enumerate(unique) if idx not in merged_indices]
    logger.info("dedup_complete", input_count=len(companies), output_count=len(result))

    return result
