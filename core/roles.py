"""
Role family helpers shared across discovery, scoring, and UI-facing APIs.
"""

from __future__ import annotations

ROLE_FOCUS_OPTIONS = [
    ("engineering", "Engineering"),
    ("data", "Data / AI"),
    ("product", "Product"),
    ("design", "Design"),
    ("sales", "Sales"),
    ("marketing", "Marketing"),
    ("customer_success", "Customer Success"),
    ("leadership", "Leadership"),
    ("all", "All Roles"),
]

_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "engineering": (
        "engineer", "developer", "software", "backend", "front end", "frontend", "full stack",
        "fullstack", "devops", "site reliability", "sre", "platform", "infrastructure", "qa",
        "automation", "mobile", "android", "ios", "security engineer", "architect",
    ),
    "data": (
        "data", "machine learning", "ml ", " ai", "analytics", "scientist", "analyst",
        "business intelligence", "bi ", "data engineer", "research engineer", "research scientist",
        "ai engineer", "mle",
    ),
    "product": ("product manager", "product owner", "product lead", "technical product"),
    "design": ("designer", "design", "ux", "ui", "product design", "visual design", "researcher"),
    "sales": ("sales", "account executive", "account manager", "business development", "bdr", "sdr", "revenue"),
    "marketing": ("marketing", "growth", "content", "seo", "paid media", "brand", "demand generation"),
    "customer_success": ("customer success", "support", "customer support", "implementation", "onboarding", "solutions consultant"),
    "leadership": ("vp", "vice president", "head of", "director", "chief", "cto", "cio", "cpo"),
}

_SERPAPI_QUERIES: dict[str, list[str]] = {
    "engineering": ["software engineer", "backend developer", "frontend developer", "full stack developer", "devops engineer"],
    "data": ["data engineer", "data scientist", "machine learning engineer", "analytics engineer", "ai engineer"],
    "product": ["product manager", "technical product manager", "product owner"],
    "design": ["product designer", "ux designer", "ui designer", "design systems designer"],
    "sales": ["account executive", "sales development representative", "business development representative"],
    "marketing": ["growth marketer", "demand generation manager", "content marketing manager"],
    "customer_success": ["customer success manager", "technical support engineer", "implementation manager"],
    "leadership": ["engineering manager", "director of engineering", "head of product", "vp engineering"],
}


def normalize_role_focus(role_focus: str | None) -> str:
    """Normalize role-focus input to a supported value."""
    clean = (role_focus or "engineering").strip().lower().replace("-", "_").replace(" ", "_")
    supported = {key for key, _ in ROLE_FOCUS_OPTIONS}
    return clean if clean in supported else "engineering"


def role_focus_matches(role_family: str | None, selected_focus: str | None) -> bool:
    """Return whether a posting family should count for the selected role focus."""
    selected = normalize_role_focus(selected_focus)
    if selected == "all":
        return True
    return (role_family or "engineering") == selected


def classify_role_family(title: str | None) -> str:
    """Best-effort mapping from job title to role family."""
    value = f" {str(title or '').strip().lower()} "
    for family, keywords in _ROLE_KEYWORDS.items():
        if any(keyword in value for keyword in keywords):
            return family
    return "engineering"


def get_role_focus_label(role_focus: str | None) -> str:
    """Human-friendly label for a role focus."""
    focus = normalize_role_focus(role_focus)
    return dict(ROLE_FOCUS_OPTIONS).get(focus, "Engineering")


def get_serpapi_queries(role_focus: str | None) -> list[str]:
    """Return search queries tuned to the selected role family."""
    focus = normalize_role_focus(role_focus)
    if focus == "all":
        queries: list[str] = []
        for values in _SERPAPI_QUERIES.values():
            queries.extend(values[:2])
        return queries
    return _SERPAPI_QUERIES.get(focus, _SERPAPI_QUERIES["engineering"])

