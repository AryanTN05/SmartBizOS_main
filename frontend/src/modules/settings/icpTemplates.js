// Six archetype templates that cover the realistic SmartBiz buyer personas.
// Each draft() takes the user's answers from step 1 and returns a Mad-Libs-
// substituted ICP description. Templates are intentionally short (4-6 lines)
// because the goal is a strong starting point the user edits, not a finished
// document. Edit-forward, not save-forward.
//
// Sourced from the May 2026 PM workflow that identified these as the modes
// SmartBiz can actually convert today: B2B SaaS founder (primary persona),
// agency/services, e-commerce/DTC, dev tools, vertical SaaS, "other".

export const ARCHETYPES = [
  {
    key: 'b2b_saas',
    icon: 'bolt',
    label: 'B2B SaaS founder',
    blurb: 'Selling software to other businesses — pre-Series-A, post-product-market-fit.',
    draft: ({ url, tagline }) => [
      `Segment: B2B SaaS — companies that resemble ${url || 'our buyer'}.`,
      `What we do: ${tagline || '(describe what your product does in one line)'}.`,
      `Headcount: 10-200. Revenue: $1M-$20M ARR, Seed–Series B.`,
      `Pain: spreadsheet-driven RevOps, no SDR yet, founders still doing outbound.`,
      `Buying triggers: recent funding round (<6mo), VP Sales hire, product launch.`,
      `Disqualifiers: <10 employees, NGO, consumer-facing, Series C+, agencies.`,
    ].join('\n'),
  },
  {
    key: 'agency',
    icon: 'flow',
    label: 'Agency / services',
    blurb: 'Marketing, design, dev shops selling expertise to growing companies.',
    draft: ({ url, tagline }) => [
      `Segment: agencies and consultancies similar to ${url || 'our firm'}.`,
      `Service: ${tagline || '(describe your service in one line)'}.`,
      `Team size: 3-30 employees. Revenue: $200K-$5M ARR.`,
      `Pain: feast/famine pipeline, lots of referrals but no outbound system.`,
      `Buying triggers: lost a big retainer, hired a new partner, expanded service line.`,
      `Disqualifiers: solo freelancers, in-house teams, anyone over 50 employees.`,
    ].join('\n'),
  },
  {
    key: 'ecommerce',
    icon: 'leads',
    label: 'E-commerce / DTC',
    blurb: 'Direct-to-consumer brands selling physical or digital products at scale.',
    draft: ({ url, tagline }) => [
      `Segment: DTC e-commerce brands like ${url || 'our buyer'}.`,
      `What they sell: ${tagline || '(describe their category in one line)'}.`,
      `Revenue: $500K-$10M ARR. Order volume: 100-5,000/month.`,
      `Pain: rising CAC on Meta/Google, tools fragmented, no first-party data strategy.`,
      `Buying triggers: post-Black Friday review, new product line, Shopify Plus migration.`,
      `Disqualifiers: marketplaces only, B2B distributors, enterprise retail, <$200K revenue.`,
    ].join('\n'),
  },
  {
    key: 'devtools',
    icon: 'spark',
    label: 'Dev tools / API',
    blurb: 'Infrastructure, APIs, libraries — selling to developers and CTOs.',
    draft: ({ url, tagline }) => [
      `Segment: developer tooling and infrastructure companies similar to ${url || 'our buyer'}.`,
      `Product: ${tagline || '(describe your dev tool in one line)'}.`,
      `Stage: post-launch, paying customers, Seed–Series A.`,
      `Pain: PLG conversion is plateauing, dev-led growth needs sales motion now.`,
      `Buying triggers: enterprise interest, new tier launch, hiring first AE, OSS-to-paid.`,
      `Disqualifiers: pre-launch, no paying users, agencies, non-technical buyers.`,
    ].join('\n'),
  },
  {
    key: 'vertical_saas',
    icon: 'star',
    label: 'Vertical SaaS',
    blurb: 'Single-industry software — dental, legal, fitness, manufacturing, etc.',
    draft: ({ url, tagline }) => [
      `Segment: vertical SaaS targeting a single industry, similar to ${url || 'our buyer'}.`,
      `Niche: ${tagline || '(describe your industry niche in one line)'}.`,
      `Customer profile: 5-200 employee single-location or small-multi-location operators.`,
      `Pain: legacy software, paper processes, no integrations, owner is the buyer.`,
      `Buying triggers: generational handoff, new location opening, compliance deadline.`,
      `Disqualifiers: enterprise-only verticals, PE-owned chains, pre-revenue startups.`,
    ].join('\n'),
  },
  {
    key: 'other',
    icon: 'eye',
    label: 'Start blank',
    blurb: "I'll write my own. No template — just a clean slate.",
    draft: () => '',
  },
];

export function archetypeByKey(key) {
  return ARCHETYPES.find((a) => a.key === key) || ARCHETYPES[0];
}
