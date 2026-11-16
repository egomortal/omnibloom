// OMNI_UI_LANG_V1 (+ OMNI_UI_LANG_V1_R2): host tests for engine/entry/OmniUiLang.h (written by apply_ui_lang.py).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_ui_lang.cpp -o t && ./t
// <tree> must be a patched tree (OmniUiLang.h) that also has OmniSettingsSearch.h (apply_settings_search.py): the
// two-language settings search is exercised against the real matcher.
#include "OmniUiLang.h"
#include "OmniSettingsSearch.h"
#include <cstdio>
#include <cstring>
#include <set>

static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

using namespace OmniUiLang;

static bool validUtf8(const char* s)
{
    const unsigned char* p = reinterpret_cast<const unsigned char*>(s);
    while (*p) {
        int n = *p < 0x80 ? 0 : (*p >> 5) == 6 ? 1 : (*p >> 4) == 14 ? 2 : (*p >> 3) == 30 ? 3 : -1;
        if (n < 0) return false;
        ++p;
        for (int i = 0; i < n; ++i, ++p) if ((*p >> 6) != 2) return false;
    }
    return true;
}
static int stars(const char* s) { size_t n = std::strlen(s); return n && s[n - 1] == '*'; }
static std::string lower(const char* s) { std::string o(s); for (char& c : o) if (c >= 'A' && c <= 'Z') c = char(c - 'A' + 'a'); return o; }
static bool has(const char* hay, const char* needle) { return lower(hay).find(lower(needle)) != std::string::npos; }
// `word` starts a word of `en` (ASCII, case-insensitive): "bookmark" in "Bookmarked: x", not "tab" in "table".
static bool startsWord(const char* en, const char* word)
{
    const std::string h = lower(en), w = lower(word);
    for (size_t at = h.find(w); at != std::string::npos; at = h.find(w, at + 1)) {
        const bool before = at == 0 || !((h[at - 1] >= 'a' && h[at - 1] <= 'z') || h[at - 1] == '-');
        const size_t end = at + w.size();
        const bool after = end >= h.size() || !(h[end] >= 'a' && h[end] <= 'z') || h[end] == 's' || h[end] == 'e';
        if (before && after) return true;
    }
    return false;
}

// The shell's omniUlSsrView (OmniSettingsSearchShell.h, OMNI_UI_LANG_V1_R2) with a Table in place of omniTr.
static std::vector<size_t> ssrView(const Table& t, const std::vector<OmniSettingsSearch::Entry>& list, const std::string& query, std::vector<int>& shown)
{
    namespace OSSR = OmniSettingsSearch;
    if (t.empty() || OSSR::norm(query).empty()) return OSSR::view(list, query, shown);
    const std::string nq = OSSR::norm(query), fq = OSSR::norm(fold(query));
    const std::vector<std::string> syn = OSSR::synonymPhrases(nq), fsyn = OSSR::synonymPhrases(fq);
    std::vector<int> en, tr, ids;
    for (const auto& e : list) {
        en.push_back(int(OSSR::tierOf(e, nq, syn)));
        OSSR::Entry x;
        x.id = e.id; x.section = fold(t.tr(e.section)); x.label = fold(t.tr(e.label)); x.value = fold(t.tr(e.value));
        tr.push_back(int(OSSR::tierOf(x, fq, fsyn)));
        ids.push_back(e.id);
    }
    return keepShown(bestOf(en, tr, int(OSSR::NoMatch)), ids, shown);
}

int main()
{
    // codes
    CHECK(normCode("es") == "es" && normCode("ES") == "es" && normCode("pt_BR") == "pt" && normCode("fr-CA") == "fr");
    CHECK(normCode("auto") == "auto" && normCode("AUTO") == "auto");
    CHECK(normCode("") == "" && normCode("e") == "" && normCode("engl") == "" && normCode("e1") == "" && normCode("../x") == "");
    CHECK(fromSystem(0) == "ja" && fromSystem(1) == "en" && fromSystem(2) == "fr" && fromSystem(3) == "es" && fromSystem(4) == "de");
    CHECK(fromSystem(7) == "pt" && fromSystem(17) == "pt" && fromSystem(18) == "en" && fromSystem(20) == "es" && fromSystem(22) == "fr");
    CHECK(fromSystem(30) == "uk" && fromSystem(31) == "en" && fromSystem(-1) == "en" && fromSystem(99) == "en");
    CHECK(column("es") == 0 && column("fr") == 1 && column("de") == 2 && column("pt") == 3 && column("en") == -1 && column("it") == -1);
    CHECK(std::strcmp(nativeName("es"), "Espa\xc3\xb1ol") == 0 && std::strcmp(nativeName("fr"), "Fran\xc3\xa7" "ais") == 0);
    CHECK(nativeName("it") == nullptr && std::strcmp(nativeName("en"), "English") == 0);

    // saved choice
    CHECK(parseChoice("") == "auto" && parseChoice("\n\n") == "auto" && parseChoice("es\n") == "es" && parseChoice("  de  \r\n") == "de");
    CHECK(parseChoice("# comment\npt_BR\n") == "pt" && parseChoice("auto") == "auto" && parseChoice("garbage!!\n") == "auto");
    CHECK(parseChoice("fr # chosen in settings\n") == "fr" && parseChoice("it") == "it");

    // Language row cycle
    CHECK(step("auto", 1) == "en" && step("en", 1) == "es" && step("pt", 1) == "auto" && step("auto", -1) == "pt" && step("es", -1) == "en");
    CHECK(step("it", 1) == "auto" && step("it", -1) == "pt" && choices("it").size() == 7 && choices("es").size() == 6);
    CHECK(step("zz-bad", 1) == "auto");   // not in the list: treated as "it" would be (appended), next wraps to auto

    // R2: printf conversions, {tokens}, compatibility
    CHECK(formatSpecs("Page %d of %d") == "dd" && formatSpecs("no format") == "" && formatSpecs("100%% sure") == "");
    CHECK(formatSpecs("%s and %5.2f and %ld and %-3d") == "sfldd" && formatSpecs("50 %") == "!" && formatSpecs("%q") == "!");
    CHECK(braceTokens("Keep {L2} held: {L1} / {R1}") == std::vector<std::string>({ "{L1}", "{L2}", "{R1}" }));
    CHECK(braceTokens("{} {x y} {Cross") .empty() && braceTokens("{Cross}{Circle}").size() == 2);
    CHECK(compatible("Page %d of %d", "Seite %d von %d") && !compatible("Page %d of %d", "Seite %s von %d"));
    CHECK(!compatible("Page %d of %d", "Seite %d") && !compatible("Back", "Zurück %d") && !compatible("Back", "50 %"));
    CHECK(compatible("{Cross} is Enter", "Enter: {Cross}") && !compatible("{Cross} is Enter", "{Circle} ist Enter"));
    CHECK(compatible("A *", "B *") && !compatible("A *", "B") && !compatible("A", "B*"));

    // built-in table: well formed (every row: all four languages, or none = English-only on purpose)
    size_t n = 0;
    const Row* r = rows(n);
    std::set<std::string> keys;
    int unsure = 0, translated = 0, englishOnly = 0, prefixes = 0, formats = 0, tokens = 0;
    for (size_t i = 0; i < n; ++i) {
        CHECK(r[i].en && *r[i].en && validUtf8(r[i].en) && !std::strchr(r[i].en, '\t') && !std::strchr(r[i].en, '\n'));
        CHECK(keys.insert(r[i].en).second);   // no duplicate keys
        const char* tr[] = { r[i].es, r[i].fr, r[i].de, r[i].pt };
        const int present = (tr[0] != nullptr) + (tr[1] != nullptr) + (tr[2] != nullptr) + (tr[3] != nullptr);
        CHECK(present == 0 || present == 4);
        if (present == 0) { ++englishOnly; CHECK(!r[i].unsure); continue; }
        ++translated;
        prefixes += stars(r[i].en);
        formats += !formatSpecs(r[i].en).empty();
        tokens += !braceTokens(r[i].en).empty();
        for (const char* c : tr) {
            if (!c) continue;
            CHECK(*c && validUtf8(c));
            CHECK(!std::strchr(c, '\t') && !std::strchr(c, '\n'));
            CHECK(stars(c) == stars(r[i].en));   // prefix entries: '*' on every side
            if (!compatible(r[i].en, c)) { ++fails; std::printf("FAIL format/tokens: \"%s\" -> \"%s\"\n", r[i].en, c); }
            CHECK(formatSpecs(c) != "!");
        }
        unsure += r[i].unsure;
    }
    CHECK(translated >= 550);
    std::printf("table: %zu rows: %d translated (%d prefix, %d format, %d with {tokens}), %d English-only, %d marked unsure\n",
        n, translated, prefixes, formats, tokens, englishOnly, unsure);

    // glossary: one word for each term in every language (tools/apply_ui_lang.py docstring)
    struct Term { const char* en; const char* es; const char* fr; const char* de; const char* pt; };
    const Term glossary[] = {
        { "tab", "pesta\xc3\xb1", "onglet", "tab", "aba" },
        { "bookmark", "marcador", "favori", "lesezeichen", "favorito" },
        { "reading list", "lista de lectura", "liste de lecture", "leseliste", "lista de leitura" },
        { "uBlock", "uBlock", "uBlock", "uBlock", "uBlock" },
        { "Media downloads", "Media downloads", "Media downloads", "Media downloads", "Media downloads" },
        { "D-pad", "cruceta", "croix", "steuerkreuz", "direcional" },
        { "pointer", "puntero", "pointeur", "zeiger", "ponteiro" },
        { "console", "consola", "console", "konsole", "console" },
        { "controller", "mando", "manette", "controller", "controle" },
    };
    int glossaryMisses = 0;
    for (size_t i = 0; i < n; ++i) {
        if (!r[i].es) continue;
        for (const Term& g : glossary) {
            if (!startsWord(r[i].en, g.en)) continue;
            const char* want[] = { g.es, g.fr, g.de, g.pt };
            const char* got[] = { r[i].es, r[i].fr, r[i].de, r[i].pt };
            for (int k = 0; k < 4; ++k)
                if (!has(got[k], want[k])) { ++glossaryMisses; std::printf("GLOSSARY \"%s\" (%s): \"%s\" lacks \"%s\"\n", r[i].en, g.en, got[k], want[k]); }
        }
        // the Downloads app keeps its name (capital D, as a word)
        if (std::strstr(r[i].en, "Downloads") && !std::strstr(r[i].en, "Media downloads"))
            for (const char* c : { r[i].es, r[i].fr, r[i].de, r[i].pt })
                if (!std::strstr(c, "Downloads")) { ++glossaryMisses; std::printf("GLOSSARY \"%s\": \"%s\" lacks Downloads\n", r[i].en, c); }
    }
    CHECK(glossaryMisses == 0);

    // built-in lookups
    Table t;
    CHECK(t.empty() && t.tr("Back") == "Back");
    CHECK(t.loadBuiltin("en") == 0 && t.loadBuiltin("it") == 0 && t.empty());
    CHECK(t.loadBuiltin("es") == translated);
    CHECK(t.tr("Back") == "Atr\xc3\xa1s" && t.tr("Browser settings") == "Ajustes del navegador" && t.tr("On") == "S\xc3\xad");
    CHECK(t.tr("Search settings\xe2\x80\xa6") == "Buscar ajustes\xe2\x80\xa6");
    CHECK(t.tr("D-pad \xe2\x97\x80 \xe2\x96\xb6 change") == "Cruceta \xe2\x97\x80 \xe2\x96\xb6 cambiar");
    CHECK(t.tr("www.example.com") == "www.example.com" && t.tr("") == "" && t.tr("back") == "back");   // exact, case-sensitive
    CHECK(t.tr("Sent to Downloads: clip.mp4") == "Enviado a Downloads: clip.mp4");
    CHECK(t.tr("Sent to Downloads") == "Enviado a Downloads");            // the exact entry wins
    CHECK(t.tr("Sent to Downloads: ") == "Sent to Downloads: ");          // exact miss and nothing after the prefix: English
    CHECK(t.tr("Removed from shortcuts: Example") == "Quitado de accesos directos: Example");   // longest prefix, not "Removed: "
    CHECK(t.tr("Removed: Example") == "Eliminado: Example");
    CHECK(t.tr("Home page set to example.com") == "P\xc3\xa1gina principal: example.com");
    std::string out;
    CHECK(!t.prefixed("Removed: ", out));   // nothing after the prefix: not a prefix match
    CHECK(t.exact("Back") && !t.exact("Removed: "));
    // R2: English-only names are not loaded; stage-2 screens; tokens survive; the format key formats
    CHECK(t.tr("uBlock") == "uBlock" && t.tr("Downloads") == "Downloads" && t.tr("YouTube") == "YouTube" && !t.exact("Touchpad"));
    CHECK(t.tr("History") == "Historial" && t.tr("Clear history\xe2\x80\xa6") == "Borrar historial\xe2\x80\xa6" && t.tr("Video") == "V\xc3\xad" "deo");
    CHECK(t.tr("{Cross} is Enter, {Circle} is Back") == "{Cross} es Intro, {Circle} es Atr\xc3\xa1s");
    CHECK(t.tr("Options > Browse > Tabs") == "Opciones > Navegar > Pesta\xc3\xb1" "as");
    {
        const std::string& f = t.tr("Page %d of %d   D-pad \xe2\x96\xb2 \xe2\x96\xbc more");
        char buf[128];
        std::snprintf(buf, sizeof(buf), f.c_str(), 2, 3);
        CHECK(std::string(buf) == "P\xc3\xa1gina 2 de 3   Cruceta \xe2\x96\xb2 \xe2\x96\xbc m\xc3\xa1s");
    }
    CHECK(t.tr("Group named \"Work\"") == "Grupo llamado \"Work\"" && t.tr("Copied hello") == "Copiado: hello");
    Table d; d.loadBuiltin("de");
    CHECK(d.tr("Close tab") == "Tab schlie\xc3\x9f" "en" && d.tr("Download failed: a.zip") == "Download fehlgeschlagen: a.zip");
    CHECK(d.tr("Couldn't open the link sent from phone") == "Link konnte nicht ge\xc3\xb6" "ffnet werden, gesendet von phone");
    Table f; f.loadBuiltin("fr");
    CHECK(f.tr("About Omni") == "\xc3\x80 propos d'Omni" && f.tr("Bookmarked: x") == "Ajout\xc3\xa9 aux favoris : x");
    Table p; p.loadBuiltin("pt");
    CHECK(p.tr("New tab") == "Nova aba" && p.tr("Off") == "N\xc3\xa3o" && p.tr("Reading list") == "Lista de leitura");
    CHECK(d.loadBuiltin("de") == translated && f.size() == size_t(translated) && p.size() == size_t(translated));

    // file entries: override, add, prefix, comments, BOM, CRLF, bad lines, caps
    Table u; u.loadBuiltin("es");
    const int added = u.loadText("\xef\xbb\xbf# my fixes\r\nBack\tVolver\r\nBrand new\tNuevo\nno tab here\n\tempty key\nempty value\t\n"
                                 "Saving to *\tGuardando en *\nHalf*\tmedio\nx\ty\tz\n");
    CHECK(added == 3);
    CHECK(u.tr("Back") == "Volver" && u.tr("Brand new") == "Nuevo" && u.tr("Saving to /x/") == "Guardando en /x/");
    CHECK(u.tr("Half") == "Half" && u.tr("x") == "x" && u.tr("no tab here") == "no tab here");
    CHECK(u.tr("Browser settings") == "Ajustes del navegador");   // built-in kept
    // R2: a file entry that would break a format key or drop a {token} is refused (the built-in one stays)
    CHECK(u.loadText("Page %d of %d   D-pad \xe2\x96\xb2 \xe2\x96\xbc more\tP\xc3\xa1gina %s\n{Cross} is Enter, {Circle} is Back\tIntro\nBack\t100 %\n") == 0);
    CHECK(u.tr("Page %d of %d   D-pad \xe2\x96\xb2 \xe2\x96\xbc more") == "P\xc3\xa1gina %d de %d   Cruceta \xe2\x96\xb2 \xe2\x96\xbc m\xc3\xa1s");
    CHECK(u.tr("Back") == "Volver");
    CHECK(u.loadText("Page %d of %d   D-pad \xe2\x96\xb2 \xe2\x96\xbc more\tP. %d/%d\n") == 1 && u.tr("Page %d of %d   D-pad \xe2\x96\xb2 \xe2\x96\xbc more") == "P. %d/%d");
    Table it; CHECK(it.loadText("Back\tIndietro\n") == 1 && it.tr("Back") == "Indietro");   // a language from the file alone
    std::string big;
    for (int i = 0; i < 5000; ++i) big += "k" + std::to_string(i) + "\tv\n";
    Table cap; CHECK(cap.loadText(big) == int(kEntryMax) && cap.size() == kEntryMax);
    Table lng; CHECK(lng.loadText(std::string(kTextMax + 1, 'a') + "\tb\nok\tfine\n") == 1);
    Table ed; CHECK(!ed.add("", "x") && !ed.add("x", "") && !ed.add("*", "*") && !ed.add("a*", "b") && !ed.add("a", "b*"));
    CHECK(ed.add("Pre *", "Vor *") && ed.add("Pre *", "Davor *") && ed.size() == 1 && ed.tr("Pre x") == "Davor x");
    CHECK(ed.add("Pre longer *", "Lang *") && ed.tr("Pre longer x") == "Lang x" && ed.tr("Pre x") == "Davor x");
    ed.clear(); CHECK(ed.empty() && ed.tr("Pre x") == "Pre x");

    // R2: folding for search
    CHECK(fold("Configuraci\xc3\xb3n") == "configuracion" && fold("\xc3\x9c" "BER") == "uber" && fold("Stra\xc3\x9f" "e") == "strasse");
    CHECK(fold("\xc3\x87" "a va") == "ca va" && fold("\xc5\x92" "uvre") == "oeuvre" && fold("Configura\xc3\xa7\xc3\xb5" "es") == "configuracoes");
    CHECK(fold("\xc3\x97\xc3\xbe") == "\xc3\x97\xc3\xbe" && fold("abc 123") == "abc 123" && fold("\xe2\x80\xa6") == "\xe2\x80\xa6" && fold("") == "");
    CHECK(fold("Pesta\xc3\xb1" "as") == "pestanas" && fold("\xc3\x80 propos") == "a propos");

    // R2: hint bar cap
    CHECK(fitCap({ 100, 100, 100 }, 300) == 0 && fitCap({ 100, 100, 100 }, 240) == 80 && fitCap({ 20, 100, 100 }, 160) == 70);
    CHECK(fitCap({ 100, 100 }, 10) == 24 && fitCap({ 100, 100 }, 10, 8) == 8 && fitCap({}, 0) == 0 && fitCap({ 50 }, 40) == 40);
    {
        const std::vector<int> w = { 30, 140, 90, 200 };
        const int c = fitCap(w, 300);
        int sum = 0;
        for (int x : w) sum += std::min(x, c);
        CHECK(c > 0 && sum <= 300 && sum > 300 - int(w.size()));
    }

    // R2: two-language order and the steadiness rule
    CHECK(bestOf({ 0, 7, 3, 7 }, { 7, 1, 7, 7 }, 7) == std::vector<size_t>({ 0, 1, 2 }));
    CHECK(bestOf({ 2, 2, 2 }, { 7, 0, 7 }, 7) == std::vector<size_t>({ 1, 0, 2 }) && bestOf({}, {}, 7).empty());
    {
        std::vector<int> shown = { 11 };
        CHECK(keepShown({ 2, 0 }, { 10, 11, 12 }, shown) == std::vector<size_t>({ 1, 2, 0 }) && shown == std::vector<int>({ 11, 12, 10 }));
        std::vector<int> gone = { 99 };
        CHECK(keepShown({ 0 }, { 10 }, gone) == std::vector<size_t>({ 0 }) && gone == std::vector<int>({ 99, 10 }));
    }

    // R2: settings search with the real matcher - English still works, the translated label works, accents optional
    {
        using E = OmniSettingsSearch::Entry;
        std::vector<E> list;
        auto entry = [&](int id, const char* label, const char* value) { E e; e.id = id; e.label = label; e.value = value; e.section = OmniSettingsSearch::sectionOf(label); list.push_back(e); };
        entry(1, "Dark mode", "Off");
        entry(2, "Pointer speed", "Normal");
        entry(3, "Search engine", "Google");
        entry(4, "Text size", "Large");
        entry(5, "Captions", "On");
        Table es; es.loadBuiltin("es");
        Table de2; de2.loadBuiltin("de");
        Table none;
        std::vector<int> s1, s2, s3, s4, s5, s6, s7;
        CHECK(ssrView(es, list, "dark", s1) == std::vector<size_t>({ 0 }));            // English as before
        CHECK(ssrView(es, list, "oscuro", s2) == std::vector<size_t>({ 0 }));          // "Modo oscuro"
        CHECK(ssrView(es, list, "busqueda", s3) == std::vector<size_t>({ 2 }));        // "Motor de búsqueda", no accent typed
        CHECK(ssrView(es, list, "subt\xc3\xadtulos", s4) == std::vector<size_t>({ 4 }));   // accent typed
        CHECK(ssrView(de2, list, "zeiger", s5) == std::vector<size_t>({ 1 }));         // "Zeigergeschwindigkeit"
        CHECK(ssrView(de2, list, "TEXTGR\xc3\x96SSE", s6).size() >= 1 && s6[0] == 4);   // "Textgröße": case + accent + ß
        CHECK(ssrView(none, list, "oscuro", s7).empty());                                // English UI: no translated matching
        std::vector<int> e1, e2;
        CHECK(ssrView(es, list, "", e1) == OmniSettingsSearch::view(list, "", e2));       // empty query: everything, as before
    }

    std::printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
