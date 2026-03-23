## Diagnosis

Looking at the edge cases, I identify several systematic weaknesses:

**1. "Habitable" boundary confusion (75% of edge cases)**
The current prompt defines "habitable" as functional but not recently updated, which creates a fuzzy middle ground. Most edge cases show properties that are clearly maintained and livable but use older design styles (wood paneling, traditional tiles, older fixtures). The model struggles to distinguish between "dated but well-maintained" (habitable) vs "recently updated" (renovated).

**2. Standard vs. Premium finish ambiguity**
Properties with solid wood cabinetry, granite counters, and quality fixtures are being classified as "standard" when they should be "premium." The model seems to conflate "traditional style" with "lower quality."

**3. Missing temporal/style cues**
The prompt lacks guidance on distinguishing between "old but high-quality" vs "basic quality." Traditional Portuguese tiles, solid wood, and classic fixtures can be premium materials even if not contemporary.

**4. Insufficient examples of maintenance indicators**
The model needs clearer signals for what constitutes "well-maintained" vs "needing updates."

## Specific Improvements

1. **Redefine "habitable"** to focus on maintenance quality rather than age/style
2. **Clarify "renovated"** to require evidence of recent work, not just good condition
3. **Expand "premium" finish** to include high-quality traditional materials
4. **Add specific visual indicators** for each condition category
5. **Include Portuguese market context** (traditional tiles, wood finishes are often premium)

## Revised Prompt

```markdown
You are a Portuguese real estate image analyst. Analyze these property listing images and return a single JSON object with exactly these fields:

{
  "is_render": true/false,
  "render_confidence": 0.0-1.0,
  "condition_label": "needs_renovation" | "habitable" | "renovated",
  "condition_confidence": 0.0-1.0,
  "finish_quality": "basic" | "standard" | "premium",
  "finish_quality_confidence": 0.0-1.0
}

Definitions:

- is_render: TRUE if 3D render/CGI. Look for: perfect lighting, unnaturally clean surfaces, no lived-in details, digital artifacts.

- condition_label:
  - needs_renovation: visible damage, wear, or outdated elements requiring work — peeling paint, worn floors, damaged surfaces, very dated fixtures, poor maintenance
  - habitable: well-maintained and clean but showing age — older fixtures/finishes in good condition, everything functional, no visible damage, properly maintained
  - renovated: clear evidence of recent updates — fresh paint, new/modern fixtures, contemporary finishes, recently installed materials, pristine condition suggesting recent work

- finish_quality:
  - basic: laminate flooring, basic white tiles, builder-grade fixtures, no-name appliances, plastic fittings, low-cost materials
  - standard: ceramic tiles, decent cabinetry, functional bathrooms, mid-range appliances, adequate but unremarkable finishes
  - premium: high-quality materials regardless of style — solid hardwood, natural stone, granite/marble counters, traditional Portuguese tiles, quality wood cabinetry, branded appliances, custom fixtures, expensive traditional or modern finishes

Key indicators:
- Focus on material quality and maintenance, not design style
- Traditional Portuguese elements (azulejo tiles, solid wood) often indicate premium quality
- Well-maintained older finishes = habitable, not needs_renovation
- Renovated requires evidence of recent work, not just good condition
- Premium can be traditional or modern if materials are high-quality

Return ONLY a single JSON object, no other text. Do NOT return an array.
```

## Expected Impact

**Condition classification improvements:**
- **Habitable confidence**: +15-20% (0.75→0.90+) by clarifying maintenance vs. age
- **Reduced over-classification of "renovated"**: 10-15% of current "renovated" should shift to "habitable"
- **Edge case resolution**: 80%+ of the low-confidence habitable cases should improve

**Finish quality improvements:**
- **Premium recognition**: +20-25% confidence when traditional high-quality materials present
- **Standard/Premium boundary**: Clearer distinction based on material quality vs. style
- **Portuguese market accuracy**: Better recognition of traditional premium finishes

**Overall confidence boost**: Average confidences should increase by 10-15% across all categories due to clearer definitions and specific visual indicators.