# Setup string integration

220 source strings were inventoried with Python AST and reviewed call sites; 226 translation rows include the pinned source plus superseded sentences retained as translation memory. Use inventory entries as authoritative, not all memory rows. All seven translations are drafts requiring native review, especially firmware/UI names, license notices, the tagline and security messages. Product names remain invariant.

Replace string concatenation before translating. Inventory integration fields identify complete templates that replace fragments in checks.py, gui.py, installer.py, ps5.py and credit strings. Positional printf placeholder order is preserved. Decode literal \n from the pipe table into actual newlines. Do not strip leading/trailing whitespace before matching.

Three messages still use the English file%s plural suffix. The current table preserves placeholder signatures for traceability, but these messages must migrate to a full count-aware template before deployment: checking files; files copied/already present; old files moved aside. Japanese and Korean do not use the English suffix. Do not interpolate the source English s into translated messages. Use a locale plural rule or invariant count-plus-noun phrasing after removing the suffix parameter.

The source changed during translation to the Java 25/JDownloader acceptance flow. setup-source-hashes.json records the final inspected modules, setup-excluded-candidates.json explains removed parser noise, and setup-validation.json records zero missing entries and zero printf-signature errors for this inventory. Re-extract at integration and review any source delta; this table does not claim to cover future edits. No Python engine files were edited.
