# Localization

User-facing strings for Downloads, Master Control, Setup and the new Omni pages, in English plus Spanish, Brazilian Portuguese, French, German, Japanese, Italian and Korean.

- `locales/<lang>.json`: the runtime tables (key → text).
- `strings.json` / `strings.csv`: the reviewed catalog with context for translators.
- `SETUP-INTEGRATION.md`: how Setup's strings map to the catalog, including the plural forms that still need migrating.

The translations are machine-assisted and flagged for native review before they are switched on. Japanese and Korean need a CJK font; Omni ships Noto Sans CJK, while Inter and Rajdhani cover Latin only.
