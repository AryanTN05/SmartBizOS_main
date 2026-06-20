"""
Enrichment agent powered by Gemini 3.1 Flash-Lite.

Responsible for:
  1. Researching companies across multiple sources in parallel:
       - Funding pre-pass (Crunchbase / LinkedIn / Tracxn / Pitchbook)
       - Hiring pre-pass (Greenhouse / Lever / Ashby / Workable / careers pages)
       - Leadership pre-pass (founders, recent senior hires/departures)
       - Deep website scrape (careers, integrations, customers, pricing, etc.)
  2. Synthesizing everything into a structured enrichment dossier
  3. Scoring leads on a 0–100 scale with a strict, tiered rubric

Extra fields land in the `raw_data` / `factors` JSONB columns without requiring
a schema migration.
"""

import asyncio
import logging
from typing import Any

from pydantic import BaseModel, Field, field_validator
from typing import Any, Optional

from config import settings
from enrichment_engine.tools.scraper import (
    ATS_SEARCH_HINTS,
    LINKEDIN_SEARCH_HINTS,
    PROFILE_SEARCH_HINTS,
    get_scraper,
)

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

# Strings that the model sometimes writes into nullable fields when it doesn't
# know the answer. The prompt tells it to use null, but we coerce as a safety net.
_NULL_TOKENS = {
    "unknown", "n/a", "na", "none", "null", "-", "--", "not available",
    "not found", "no data", "tbd", "?", "",
}


def _nullify_unknown(v: Any) -> Any:
    """Coerce 'Unknown' / 'N/A' / '-' / '' etc. to None on string fields."""
    if isinstance(v, str) and v.strip().lower() in _NULL_TOKENS:
        return None
    return v


# ── Structured Output Models ──────────────────────────────────────────────────

class NewsItem(BaseModel):
    """A single recent news item, launch, or announcement."""
    headline: str = Field(description="Short headline")
    summary: str = Field(description="1–2 sentence summary")
    source: Optional[str] = Field(default=None, description="Source URL or publication")
    date: Optional[str] = Field(default=None, description="Approximate date (ISO if known)")


class FundingDetails(BaseModel):
    """Detailed funding intel pulled from Crunchbase / LinkedIn / Tracxn."""
    stage: Optional[str] = Field(default=None, description="e.g. seed, series-a, series-b, bootstrapped")
    total_raised: Optional[str] = Field(default=None, description="e.g. '$12.4M'")
    last_round_amount: Optional[str] = Field(default=None, description="Most recent round size")
    last_round_date: Optional[str] = Field(default=None, description="ISO date if known")
    months_since_last_round: Optional[int] = Field(
        default=None, description="Best estimate in months"
    )
    lead_investors: list[str] = Field(default_factory=list)
    notable_investors: list[str] = Field(default_factory=list)
    source: Optional[str] = Field(
        default=None,
        description="Primary source, e.g. crunchbase/linkedin/tracxn/inferred_from_absence",
    )

    _coerce_strings = field_validator(
        "stage", "total_raised", "last_round_amount", "last_round_date", "source",
        mode="before",
    )(_nullify_unknown)


class HiringRole(BaseModel):
    """A single open role scraped from the careers page / ATS platform."""
    title: str = Field(description="Role title verbatim as posted")
    department: Optional[str] = Field(default=None)
    days_posted: Optional[int] = Field(default=None, description="Days since posting")
    location: Optional[str] = Field(default=None)
    relevance_tag: Optional[str] = Field(
        default=None,
        description="'directly_relevant' | 'adjacent' | 'general'",
    )
    tools_mentioned: list[str] = Field(
        default_factory=list,
        description="Tools/competitors named inside the job description body",
    )

    _coerce_strings = field_validator(
        "department", "location", "relevance_tag", mode="before",
    )(_nullify_unknown)


class ExpansionSignal(BaseModel):
    """Evidence of geographic, market, or product expansion."""
    kind: str = Field(description="'geographic' | 'market' | 'product'")
    description: str
    date: Optional[str] = None

    _coerce_date = field_validator("date", mode="before")(_nullify_unknown)


class Founder(BaseModel):
    """Founder / leadership entry."""
    name: str
    title: Optional[str] = None
    background: Optional[str] = Field(
        default=None, description="Prior roles or notable experience"
    )
    is_notable: bool = Field(
        default=False,
        description="True if the person is a recognized operator in our space",
    )

    _coerce_strings = field_validator(
        "title", "background", mode="before",
    )(_nullify_unknown)


class EnrichmentResult(BaseModel):
    """
    Structured enrichment data. Core fields map to `enrichment` table columns;
    the rest are persisted inside the `raw_data` JSONB column.
    """

    # ── Core firmographics (DB columns) ────────────────────────────────────
    company_size: Optional[str] = Field(
        default=None,
        description="Bucket: startup, small, medium, large, enterprise",
    )
    employee_count: Optional[int] = Field(
        default=None, description="Best integer estimate"
    )
    industry: Optional[str] = Field(default=None)
    funding_stage: Optional[str] = Field(default=None)
    funding_amount: Optional[str] = Field(default=None, description="e.g. '$5.2M'")
    tech_stack: list[str] = Field(default_factory=list)
    pain_points: Optional[str] = Field(default=None)
    recent_news: list[NewsItem] = Field(default_factory=list)
    competitor_tools: list[str] = Field(default_factory=list)

    # ── Tier 1 — critical signals ─────────────────────────────────────────
    funding_details: FundingDetails | None = Field(default=None)
    hiring_signals: list[HiringRole] = Field(default_factory=list)
    competitor_tools_in_jds: list[str] = Field(
        default_factory=list,
        description="Tools explicitly named inside job description text",
    )
    expansion_signals: list[ExpansionSignal] = Field(default_factory=list)
    headcount_trend: Optional[str] = Field(
        default=None, description="'growing' | 'flat' | 'declining'"
    )

    # ── Tier 2 — supporting context ───────────────────────────────────────
    linkedin_headcount_delta: Optional[str] = Field(
        default=None, description="e.g. '+12% in 90 days'"
    )
    competitor_activity: Optional[str] = Field(
        default=None,
        description="Summary of recent funding / launches by direct competitors",
    )
    product_launches: list[NewsItem] = Field(default_factory=list)
    founders: list[Founder] = Field(default_factory=list)

    # ── Tier 3 — negative / meta signals ──────────────────────────────────
    negative_signals: list[str] = Field(
        default_factory=list,
        description="Layoffs, leadership departures, no careers page, etc.",
    )

    # ── Confidence + provenance (added to combat hallucination risk) ──────
    # 0.0–1.0. Tracks how many of the upstream pre-passes (funding, hiring,
    # leadership, headcount, website scrape) returned real content vs ""
    # /"NONE". The scorer is wired to penalize low-confidence dossiers so
    # we don't ship confident-looking scores grounded in invented signal.
    data_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="0–1; fraction of grounded pre-passes that returned non-empty content",
    )
    # Per-claim source URLs from the grounded search. Empty list ⇒ the
    # model produced the claim without a verifiable citation (treat with
    # suspicion). Populated lazily by the synthesis prompt — model is
    # asked to attribute each fact to one of the URLs it saw.
    source_citations: list[str] = Field(
        default_factory=list,
        description="URLs the grounded search returned that the dossier cites",
    )

    _coerce_strings = field_validator(
        "company_size", "industry", "funding_stage", "funding_amount",
        "pain_points", "headcount_trend", "linkedin_headcount_delta",
        "competitor_activity",
        mode="before",
    )(_nullify_unknown)


class ScoreCategory(BaseModel):
    """One line-item in the scoring breakdown."""
    points: int = Field(description="Points awarded in this category")
    max_points: int = Field(description="Maximum points possible in this category")
    reason: str = Field(description="One-line reasoning for the points awarded")


class ScoringFactors(BaseModel):
    """
    Breakdown of the rubric. 70 pts high + 20 pts mid + 10 pts low = 100.
    Negative flags are applied AFTER summing and floored at 0.
    """
    # High priority — 70 pts
    funding_recency: ScoreCategory         # max 25
    hiring_signals: ScoreCategory          # max 25
    company_size: ScoreCategory            # max 10
    expansion: ScoreCategory               # max 10

    # Mid priority — 20 pts
    competitor_tools_in_jds: ScoreCategory  # max 8
    headcount_delta: ScoreCategory          # max 7
    product_launches: ScoreCategory         # max 5

    # Low priority — 10 pts
    data_completeness: ScoreCategory        # max 5
    founder_signals: ScoreCategory          # max 5


class LeadScoreResult(BaseModel):
    """Scoring output. Persists to the `score_history` table."""
    score: int = Field(
        ge=0, le=100,
        description="Final score after negative deductions, floored at 0",
    )
    reason: str = Field(
        description="One-sentence summary of why this lead is/isn't a strong fit",
    )
    factors: ScoringFactors
    negative_flags: list[str] = Field(
        default_factory=list,
        description="List of applied deductions with reasons (e.g. 'layoffs: -10')",
    )


# ── Prompts ───────────────────────────────────────────────────────────────────

FUNDING_LOOKUP_PROMPT = """\
You are a B2B funding researcher. Use Google Search to pull precise, verifiable
funding details for the target company.

MANDATORY SOURCES — you MUST run explicit site-restricted queries against all
three of these before reporting "unknown":
  1. crunchbase.com  (primary funding truth source)
     Queries: `site:crunchbase.com/organization {company}`,
              `site:crunchbase.com {company} funding`
  2. linkedin.com/company  (secondary — employee count, about section)
     Queries: `site:linkedin.com/company {company}`,
              `site:linkedin.com/company {company} about`
  3. tracxn.com  (India/APAC-heavy coverage, often has pre-seed rounds)
     Queries: `site:tracxn.com {company}`,
              `site:tracxn.com/d/companies {company}`

SECONDARY SOURCES (use if the three above come up empty):
  4. pitchbook.com
  5. Major tech press (TechCrunch, SaaStr, The Ken, YourStory, press releases)

Extract ONLY facts you can cite:
  - Current funding stage (e.g. seed, series-a, series-b, bootstrapped)
  - Total capital raised to date (e.g. '$12.4M')
  - MOST RECENT round: amount, ISO date, lead investor(s), notable participants
  - Months since that most recent round (best estimate)
  - Any layoffs, down rounds, or CRO/founder departures in the last 12 months

Return a compact plain-text summary with clear labels. For each data point,
cite which source it came from. If a field is not found in any source, write
"unknown" for that field. Do NOT fabricate dates or amounts.

BOOTSTRAPPED INFERENCE:
  - If Crunchbase, LinkedIn, AND Tracxn all return no funding record AND you
    find no announcements of funding, classify the company as "bootstrapped"
    with source: "inferred_from_absence". This is the correct answer — not "unknown".
"""


HIRING_LOOKUP_PROMPT = """\
You are a B2B hiring-signals researcher. Use Google Search aggressively to locate
the target company's open roles. You MUST try multiple query shapes before
concluding there are no roles.

SEARCH STRATEGY (run queries in this order, stop when you find real roles):
  1. "{company} careers"
  2. "{company} jobs"
  3. "{company} open roles" / "{company} we're hiring"
  4. site:greenhouse.io "{company}"
  5. site:boards.greenhouse.io "{company}"
  6. site:jobs.lever.co "{company}"
  7. site:ashbyhq.com "{company}" OR site:jobs.ashbyhq.com "{company}"
  8. site:workable.com "{company}" OR site:jobs.workable.com "{company}"
  9. site:smartrecruiters.com "{company}"
  10. site:linkedin.com/jobs "{company}"

For EACH open role found, extract:
  - Role title verbatim as posted
  - Department (Sales, Engineering, Product, Marketing, Finance, Ops, etc.)
  - Location
  - Posted date or days-since-posted if visible
  - Any tool / software / competitor names mentioned in the JD body
    (e.g. Outreach, Salesloft, HubSpot, Gong, Apollo, Salesforce, Marketo)

Classify relevance using these rules (our ICP is sales-automation buyers):
  - directly_relevant: Sales Ops, RevOps, BDR, SDR, AE, Account Executive,
    Account Manager, Growth, Marketing Ops, Head of Sales, CRO, VP Sales
  - adjacent: Any other Sales/Marketing/Product role, Founding Recruiter,
    Chief of Staff
  - general: Engineering, Design, Finance, Ops, HR

Return a plain-text list of roles with labels. Also return:
  - Total count of open roles
  - Count that are directly_relevant
  - Any tools extracted from JD bodies (deduplicated)
  - The source URL of the careers/ATS page you used

If after running ALL the above queries you genuinely find zero roles, say
"NO CAREERS FOOTPRINT FOUND" explicitly. Do not return an empty result without
having tried the queries above.
"""


LEADERSHIP_LOOKUP_PROMPT = """\
You are a B2B leadership researcher. Use Google Search to find founders and
senior leadership for the target company.

MANDATORY SOURCES — run explicit site-restricted queries against:
  1. linkedin.com/in  (founder + exec profiles)
     Queries: `site:linkedin.com/in {company} founder`,
              `site:linkedin.com/in {company} CEO`
  2. linkedin.com/company  (People / About section)
     Queries: `site:linkedin.com/company {company} about`
  3. crunchbase.com  (founders + current team section)
     Queries: `site:crunchbase.com/organization {company}`,
              `site:crunchbase.com {company} founders`
  4. tracxn.com  (team + investors)
     Queries: `site:tracxn.com {company}`
  5. Company /about, /team, or /leadership pages
  6. Recent press announcing senior hires or departures

Extract:
  - Founders (full name, current title, prior notable roles — cite LinkedIn URL
    if found)
  - Current C-suite / VPs if publicly listed
  - Any senior departures or new hires in the last 90 days
    (especially CEO, CRO, VP Sales, Head of Growth, CMO)
  - Notable investors, advisors, or board members (from Crunchbase/Tracxn)

Return a compact plain-text summary. Flag anyone with a recognizable track
record (e.g. prior exit, YC alumnus, ex-unicorn exec) as "notable".

If you cannot find a field after running the above queries, say "unknown" —
do not invent names.
"""


HEADCOUNT_LOOKUP_PROMPT = """\
You are a B2B headcount-growth researcher. Your job is to estimate the
company's LinkedIn employee count TODAY and 90 DAYS AGO, and express the
change as a percentage.

MANDATORY SOURCES — run explicit site-restricted queries:
  1. linkedin.com/company  (the About / People tabs)
     Queries: `site:linkedin.com/company {company}`,
              `site:linkedin.com/company {company} employees`,
              `site:linkedin.com/company {company} about`
  2. linkedin.com/posts / linkedin.com/pulse  (recent hiring-announcement posts
     from the company or its recruiters)
     Queries: `site:linkedin.com/posts {company} hiring`,
              `site:linkedin.com/pulse {company}`
  3. crunchbase.com  (employee range — Crunchbase shows bands like "11-50")
  4. tracxn.com  (employee count + recent headcount-related updates)

OUTPUT FORMAT (plain text, labeled):
  - current_employee_count: <int or "unknown">
  - employee_count_90d_ago: <int or "unknown">
  - delta_percentage: <e.g. "+12% in 90 days" or "unknown">
  - trend: <"growing" | "flat" | "declining" | "unknown">
  - notes: <any caveats, e.g. "Crunchbase band used, not LinkedIn exact count">

RULES:
  - If LinkedIn shows an exact employee count today, use that. If it shows a
    band (e.g. 51-200), use the midpoint but label notes accordingly.
  - For the 90-day-ago figure, check archived LinkedIn pages via Wayback Machine
    (`web.archive.org/web/*/linkedin.com/company/{slug}`) if Google returns one.
  - If you cannot find historical data, return "unknown" for that field — do NOT
    invent a prior number.
  - "Growing" requires concrete evidence (>=5% delta OR multiple hiring posts).
"""


ENRICHMENT_SYSTEM_PROMPT = """\
You are a B2B lead intelligence analyst for a sales automation platform.

Your job is to research a company and produce a comprehensive enrichment dossier.
Be thorough, accurate, and cite specifics wherever possible.

You will be given four pre-fetched intelligence blocks and a deep website scrape.
All pre-fetched blocks come from grounded Google Search with explicit site-restricted
queries against LinkedIn, Crunchbase, and Tracxn. Treat them as authoritative unless
you find a newer verified source:
  - FUNDING INTEL    (Crunchbase / LinkedIn / Tracxn / Pitchbook)
  - HIRING INTEL     (Greenhouse / Lever / Ashby / Workable / LinkedIn Jobs)
  - LEADERSHIP INTEL (LinkedIn profiles + Crunchbase / Tracxn founders)
  - HEADCOUNT INTEL  (LinkedIn current vs 90-day-prior employee count)

For each lead, you must determine:

TIER 1 — CRITICAL (retrieve these with highest priority):
1. **Funding**: Stage, total raised, most recent round date and amount, lead investors.
   If the FUNDING INTEL block says "bootstrapped" with source "inferred_from_absence",
   use funding_stage = "bootstrapped" — NOT null.
2. **Hiring signals**: Use the HIRING INTEL block as the primary source. List role
   titles verbatim, department, days since posted, and tools mentioned in JD bodies.
   If HIRING INTEL says "NO CAREERS FOOTPRINT FOUND", set hiring_signals = [] AND
   add "no_visible_careers_page" to negative_signals.
3. **Competitor tools in JDs**: Extract any competitor or adjacent tool names named
   inside job descriptions (Outreach, Salesloft, HubSpot, Gong, Apollo, etc.).
4. **Company size**: Employee count (best estimate as integer), headcount growth trend.
5. **Expansion signals**: New markets, geographies, or product lines announced in the
   last 12 months. Roles open in MULTIPLE GEOGRAPHIES counts as a geographic expansion signal.

TIER 2 — SUPPORTING CONTEXT:
6. **LinkedIn headcount delta**: Use the HEADCOUNT INTEL block as the primary source.
   Express as a percentage — e.g., "+12% in 90 days". >10% growth = strong buying signal.
   If HEADCOUNT INTEL is empty, fall back to searching `site:linkedin.com/company {company}`
   and cross-checking against Crunchbase / Tracxn employee bands.
7. **Competitor activity**: Direct competitors recently funded, launching products, or
   hiring aggressively — flag this pressure.
8. **Product launches & announcements**: Major releases, partnerships, or GTM pivots
   in the last 6 months.
9. **Founder & leadership**: Use LEADERSHIP INTEL. Flag notable operators.

TIER 3 — SUPPLEMENTARY:
10. **Technology**: Tech stack inferred from JDs, GitHub, or the /integrations page.
11. **Recent news**: Anything not captured above (awards, press, thought leadership).
12. **Negative signals**: Layoffs, CRO/VP Sales / founder departures in the last 90
    days, missing or empty careers page, funding > 24 months old with no new round.

ABSOLUTE RULES — violating these is a failure:
- NEVER write the strings "Unknown", "N/A", "-", "TBD", or "" into a string field.
  Use JSON null instead. (Exception: `funding_stage` may be "bootstrapped" when
  FUNDING INTEL says so.)
- If you cannot determine a field with confidence, leave it null. Do NOT guess.
- For employee_count, provide your best INTEGER estimate — not a string.
- For hiring_signals, list role titles VERBATIM as posted — no paraphrasing.
- For competitor_tools_in_jds, list only tools EXPLICITLY NAMED in JD text.
- If the HIRING INTEL block is missing or empty, do NOT return hiring_signals = []
  without confirming there are no signals.
  An empty hiring_signals list is only valid AFTER checking all sources.
"""


SCORING_SYSTEM_PROMPT = """\
You are a lead scoring analyst. Given a company and its enrichment data,
assign a quality score from 0 to 100. The contact name is NOT a scoring input —
ignore it. Score the COMPANY only.

SCORING BREAKDOWN:

HIGH PRIORITY — 70 points total:

- **Funding recency & size** (25 pts):
    25 = funded in last 6 months (Series A or above, or significant seed)
    15 = funded 6–18 months ago, or notable angel/pre-seed
    5  = bootstrapped or no funding data found
    0  = explicitly stated bootstrapped with no growth signals

- **Hiring signals** (25 pts):
    25 = active postings for roles directly relevant to our use case
         (Sales Ops, RevOps, BDR/SDR, AE, Growth, Marketing Ops, CRO, VP Sales)
    15 = hiring in adjacent functions (Sales, Marketing, Product, Chief of Staff,
         Founding Recruiter)
    5  = general hiring with no relevant roles
    0  = no hiring activity found
    BONUS +3 (capped at 25): role has been posted 30+ days unfilled = urgent pain

- **Company size & employee count** (10 pts):
    10 = 50–500 employees (ideal ICP range)
    6  = 500–2000 employees
    3  = <50 employees (early, may lack budget)
    1  = 2000+ employees (complex sales cycle)

- **Expansion & future scope** (10 pts):
    10 = actively entering new markets, geographies, or launching new product lines
         (hiring across 3+ geographies counts)
    5  = stable growth with clear upward trajectory
    0  = no signals of expansion

MID PRIORITY — 20 points total:

- **Competitor tools mentioned in job descriptions** (8 pts):
    8 = JDs explicitly name a direct competitor or adjacent tool we displace
        (e.g., Outreach, Salesloft, HubSpot, Gong, Apollo)
    4 = JDs mention a tool in our category but not a direct competitor
    0 = no tool mentions found in JDs

- **LinkedIn headcount delta — 90-day growth** (7 pts):
    7 = headcount grew >10% in last 90 days
    4 = grew 5–10%
    1 = flat or <5% growth
    0 = headcount declined or no data

- **Product launches & announcements** (5 pts):
    5 = major product launch, partnership, or GTM pivot in last 6 months
    2 = minor release or announcement
    0 = no recent activity

LOW PRIORITY — 10 points total:

- **Data completeness** (5 pts):
    5 = Tier 1 fields fully populated
    3 = Tier 1 mostly populated, some gaps
    1 = significant gaps in Tier 1 data

- **Founder / leadership signals** (5 pts):
    5 = founders with relevant prior experience or notable endorsers in our space
    2 = general credibility signals
    0 = no data

NEGATIVE SIGNALS — deduct AFTER summing categories, then floor at 0:
- Recent layoffs announced: -10 pts
- Founder or CRO/VP Sales departed in last 90 days: -5 pts
- No careers page or zero open roles: -5 pts

OUTPUT RULES:
- `score` = max(0, sum(category points) + negatives). Must be an integer 0–100.
- Every category MUST include a one-line `reason` citing the specific enrichment
  fact that justified the points (e.g. "series-b closed 3 months ago" not "good funding").
- `negative_flags` lists each applied deduction with its reason; empty list if none.
- `reason` (top-level) is a single sentence summarizing fit.
"""


# ── Pre-pass helpers ──────────────────────────────────────────────────────────

async def _run_grounded_search(
    system_prompt: str,
    user_prompt: str,
    label: str,
) -> str:
    """
    Run a single Google-Search-grounded pass and return the plain-text output.
    Never raises — returns '' on failure so the overall pipeline stays resilient.
    """
    model_name = settings.gemini_model.split("/")[-1]
    try:
        from lara_smartbiz.utils.llm import complete_text
        text = await complete_text(
            user_prompt,
            system=system_prompt,
            model=model_name,
            temperature=1.0,
            max_output_tokens=4096,
            google_search=True,
        )
        if text:
            logger.info(f"Pre-pass OK: {label} ({len(text)} chars)")
        else:
            logger.warning(f"Pre-pass returned empty text: {label}")
        return text
    except Exception as e:
        logger.warning(f"Pre-pass failed: {label} - {e}")
        return ""


def _format_hints(hints: tuple[str, ...], company: str) -> str:
    """Render a tuple of query templates into a bulleted list for injection."""
    return "\n".join(f"  - {h.format(company=company)}" for h in hints)


async def _fetch_funding_intel(company: str, website: Optional[str]) -> str:
    """
    Dedicated funding pre-pass. Hits Crunchbase + LinkedIn + Tracxn + Pitchbook
    via explicit site-restricted queries (see PROFILE_SEARCH_HINTS).
    """
    site_hint = f" (website: {website})" if website else ""
    query_hints = _format_hints(PROFILE_SEARCH_HINTS, company)
    prompt = (
        f'Research funding details for the company: "{company}"{site_hint}.\n\n'
        f"Profile-page queries you MUST run (at minimum the first three):\n"
        f"{query_hints}\n\n"
        "Follow the extraction rules in the system prompt strictly, including "
        "the bootstrapped-inference rule when Crunchbase/LinkedIn/Tracxn all "
        "return no funding record."
    )
    return await _run_grounded_search(FUNDING_LOOKUP_PROMPT, prompt, "funding")


async def _fetch_hiring_intel(company: str, website: Optional[str]) -> str:
    """
    Dedicated hiring pre-pass. Runs the ATS-heavy search strategy from
    HIRING_LOOKUP_PROMPT. Most important pre-pass — most B2B companies use
    Greenhouse / Lever / Ashby rather than self-hosted pages.
    """
    site_hint = f" (website: {website})" if website else ""
    query_hints = _format_hints(ATS_SEARCH_HINTS, company)
    prompt = (
        f'Research open roles and hiring signals for the company: "{company}"{site_hint}.\n\n'
        f"Suggested search queries (run several of these):\n{query_hints}\n\n"
        "Follow the extraction rules in the system prompt strictly. List role titles "
        "verbatim, extract tool mentions from JD bodies, and classify relevance."
    )
    return await _run_grounded_search(HIRING_LOOKUP_PROMPT, prompt, "hiring")


async def _fetch_leadership_intel(company: str, website: Optional[str]) -> str:
    """
    Dedicated leadership pre-pass — founders, senior hires, departures.
    Uses LinkedIn + Crunchbase + Tracxn profile searches.
    """
    site_hint = f" (website: {website})" if website else ""
    query_hints = _format_hints(PROFILE_SEARCH_HINTS, company)
    prompt = (
        f'Research founders and senior leadership for the company: "{company}"{site_hint}.\n\n'
        f"Profile-page queries you MUST run:\n{query_hints}\n\n"
        "Prioritize LinkedIn /in profiles, Crunchbase founders section, Tracxn team "
        "tab, and the company /team or /leadership page. Flag anyone notable in our space."
    )
    return await _run_grounded_search(LEADERSHIP_LOOKUP_PROMPT, prompt, "leadership")


async def _fetch_headcount_intel(company: str, website: Optional[str]) -> str:
    """
    Dedicated headcount pre-pass. Drives the 7-pt `headcount_delta` scoring
    category that was previously unsourced. Uses LinkedIn-specific queries
    plus Crunchbase / Tracxn for secondary employee-count data.
    """
    site_hint = f" (website: {website})" if website else ""
    query_hints = _format_hints(LINKEDIN_SEARCH_HINTS, company)
    prompt = (
        f'Research LinkedIn headcount growth for the company: "{company}"{site_hint}.\n\n'
        f"LinkedIn-focused queries you MUST run:\n{query_hints}\n\n"
        "Also check Crunchbase and Tracxn for employee-count bands as a cross-check. "
        "Follow the output format in the system prompt exactly."
    )
    return await _run_grounded_search(HEADCOUNT_LOOKUP_PROMPT, prompt, "headcount")


async def _deep_scrape(website: str) -> str:
    """Deep scrape wrapper — never raises, returns '' on failure."""
    try:
        logger.info(f"Deep scraping domain: {website}")
        scraper = get_scraper()
        return await scraper.deep_scrape_domain(website)
    except Exception as e:
        logger.warning(f"Failed to scrape {website}: {e}")
        return ""


# ── Public Functions ──────────────────────────────────────────────────────────

async def enrich_lead(
    name: str,
    company: str,
    website: Optional[str] = None,
) -> EnrichmentResult:
    """
    Run the enrichment flow on a lead and return structured data.

    Pipeline (everything before the main call runs in parallel):
      1a. Deep-scrape website (homepage, careers, integrations, customers, ...)
      1b. Funding pre-pass    (Crunchbase / LinkedIn / Tracxn / Pitchbook)
      1c. Hiring pre-pass     (Greenhouse / Lever / Ashby / Workable / careers)
      1d. Leadership pre-pass (founders / senior hires / departures)
      1e. Headcount pre-pass  (LinkedIn 90-day employee-count delta)
      2.  Main structured enrichment call with all five context blocks injected
    """
    logger.info(f"Enriching lead: {name} @ {company}")

    # Fire all context-gathering tasks in parallel.
    scrape_coro = _deep_scrape(website) if website else _empty()
    funding_coro = _fetch_funding_intel(company, website)
    hiring_coro = _fetch_hiring_intel(company, website)
    leadership_coro = _fetch_leadership_intel(company, website)
    headcount_coro = _fetch_headcount_intel(company, website)

    (
        scrape_content,
        funding_intel,
        hiring_intel,
        leadership_intel,
        headcount_intel,
    ) = await asyncio.gather(
        scrape_coro, funding_coro, hiring_coro, leadership_coro, headcount_coro,
    )

    # Build the main enrichment prompt with all context blocks.
    prompt_parts = [
        "Research and enrich this lead:",
        f"- Name: {name}",
        f"- Company: {company}",
    ]
    if website:
        prompt_parts.append(f"- Website: {website}")

    if funding_intel:
        prompt_parts.append(
            "\n=== FUNDING INTEL (Crunchbase/LinkedIn/Tracxn) ===\n"
            f"{funding_intel}\n"
            "=== END FUNDING INTEL ==="
        )

    if hiring_intel:
        prompt_parts.append(
            "\n=== HIRING INTEL (ATS + careers pages) ===\n"
            f"{hiring_intel}\n"
            "=== END HIRING INTEL ==="
        )

    if leadership_intel:
        prompt_parts.append(
            "\n=== LEADERSHIP INTEL ===\n"
            f"{leadership_intel}\n"
            "=== END LEADERSHIP INTEL ==="
        )

    if headcount_intel:
        prompt_parts.append(
            "\n=== HEADCOUNT INTEL (LinkedIn / Crunchbase / Tracxn) ===\n"
            f"{headcount_intel}\n"
            "=== END HEADCOUNT INTEL ==="
        )

    if scrape_content:
        prompt_parts.append(
            "\n=== WEBSITE CONTENT (deep scrape) ===\n"
            f"{scrape_content}\n"
            "=== END WEBSITE CONTENT ==="
        )

    prompt = "\n".join(prompt_parts)

    model_name = settings.gemini_model.split("/")[-1]

    # Compute data confidence from the 5 grounded pre-passes. Each non-empty
    # source contributes 0.2; an empty / "NONE" response from a pre-pass is
    # a real signal of missing data and not invented dossier content.
    def _has_signal(s: Optional[str]) -> bool:
        if not s: return False
        t = s.strip().upper()
        return bool(t) and t not in ("NONE", "NO DATA", "NO CAREERS FOOTPRINT FOUND")

    confidence_inputs = [
        _has_signal(scrape_content),
        _has_signal(funding_intel),
        _has_signal(hiring_intel),
        _has_signal(leadership_intel),
        _has_signal(headcount_intel),
    ]
    computed_confidence = round(sum(confidence_inputs) / 5.0, 2)

    from lara_smartbiz.utils.llm import complete_text
    content = await complete_text(
        prompt,
        system=ENRICHMENT_SYSTEM_PROMPT,
        model=model_name,
        temperature=1.0,
        max_output_tokens=8192,
        response_schema=EnrichmentResult,
    )

    logger.info(f"Enrichment complete for {name} @ {company} (confidence={computed_confidence})")

    try:
        result = EnrichmentResult.model_validate_json(content)
        # Overwrite the model-supplied confidence with the deterministic one
        # we computed from pre-pass output. The model may have invented a
        # high-confidence number, but the proof is in whether the grounded
        # search actually returned content.
        result.data_confidence = computed_confidence
        return result
    except Exception as e:
        logger.error(f"Failed to parse enrichment JSON: {e}\nRaw output:\n{content}")
        raise


async def score_lead(
    name: str,
    company: str,
    enrichment_data: EnrichmentResult,
) -> LeadScoreResult:
    """
    Score a lead based on the enrichment dossier. The contact name is accepted
    for API compatibility but intentionally NOT passed into the scoring prompt —
    scoring is company-level only.
    """
    prompt = (
        f"Score the following company. Contact name is not a scoring input.\n"
        f"- Company: {company}\n"
        f"- Enrichment Data:\n{enrichment_data.model_dump_json(indent=2)}"
    )

    logger.info(f"Scoring lead: {name} @ {company}")

    model_name = settings.gemini_model.split("/")[-1]

    from lara_smartbiz.utils.llm import complete_text
    content = await complete_text(
        prompt,
        system=SCORING_SYSTEM_PROMPT,
        model=model_name,
        temperature=1.0,
        max_output_tokens=4096,
        response_schema=LeadScoreResult,
    )

    logger.info(f"Scoring complete for {name}")

    try:
        result = LeadScoreResult.model_validate_json(content)
    except Exception as e:
        logger.error(f"Failed to parse score JSON: {e}\nRaw output:\n{content}")
        raise

    # Deterministic confidence penalty — applied AFTER the model returned its
    # score so a fabricated-looking dossier can't ship a confident number.
    # The model's own "data_completeness" rubric category is fuzzy and
    # routinely overstates fit when pre-passes are empty. This guard is
    # ground-truth: fewer pre-passes returned content → harder cap on score.
    conf = getattr(enrichment_data, "data_confidence", None) or 0.0
    if conf < 0.4:
        penalty = 20
        cap = 50
    elif conf < 0.6:
        penalty = 10
        cap = 70
    else:
        penalty = 0
        cap = 100
    if penalty:
        original = result.score
        result.score = max(0, min(cap, original - penalty))
        result.negative_flags = list(result.negative_flags) + [
            f"low_data_confidence: -{penalty} (conf={conf:.2f}, capped at {cap})"
        ]
        logger.info(f"Score {original} → {result.score} (low-confidence penalty)")
    return result


async def _empty() -> str:
    """No-op awaitable used when website is None to keep asyncio.gather simple."""
    return ""
