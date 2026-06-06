{#
  normalize_dev_name — canonical name-matching normalization for development
  staging models. Lifted 2026-06-06 from the inline portal_pre CTE in
  silver_properties.unified_developments so all consumers (dedup, search,
  search-index, eventual fuzzy-join) share one definition.

  Steps:
    1. Lowercase + deaccent (Portuguese vowels + ç → ASCII).
    2. Strip typology codes \mt[0-9]+([-+/][0-9]+)*\M (T1, T2, T1+1, T2-3, …).
    3. Strip boilerplate words \m(empreendimento|edificio|the)\M.
    4. Punctuation → space, then trim/collapse via outer TRIM + regex.

  The cross-cutting trailing-concelho strip ("… , Matosinhos" → "…") stays in
  silver — it needs concelho context the staging models can't supply uniformly
  (e.g. CAOP geo_concelho_name vs portal-text concelho).
#}
{% macro normalize_dev_name(col) %}
TRIM(regexp_replace(
    regexp_replace(
        regexp_replace(
            translate(lower(COALESCE({{ col }}, '')),
                      'áàâãäçéèêëíìîïóòôõöúùûü', 'aaaaaceeeeiiiiooooouuuu'),
            '\mt[0-9]+([-+/][0-9]+)*\M', ' ', 'g'),
        '\m(empreendimento|edificio|the)\M', ' ', 'g'),
    '[^a-z0-9]+', ' ', 'g'))
{% endmacro %}
