// OMNI_SETTINGS_SEARCH_V1: the search box at the top of Browser settings (shell side). Included from
// OmniBrowserSettings.h right before omniFxSettingsBuild (inside OmniBrowser.cpp's anonymous namespace); the pure
// part is OmniSettingsSearch.h (included from OmniBrowser.cpp). Main thread only.
//
// How it hooks in: omniFxSettingsBuild still adds every row exactly as before (its own add() lambda and the
// omniXxSettingsRows(p) helpers of the other patches push straight into p.rows: the rows are collected, not
// drawn, and the panel draws p.rows later). One call at the end of it, omniSsrFilter(p), puts the
// "Search settings..." row (id OSSR::kSearchRowId) first and, when a query is set, turns the built rows into
// (id, section, label, value) entries, lets OSSR::view() pick and order them, and rebuilds p.rows from the ORIGINAL
// OmniFxRow objects (same id, stepper, enabled, detail) with the section as a dim prefix (OmniFxRow::prefix).
// So any row any patch adds is searchable, and Cross / D-pad / Triangle on a found row reach the same handler
// (omniFxSettingsInput dispatches by id). p.input becomes omniSsrPanelInput, which answers the two search rows and
// passes everything else to omniFxSettingsInput; Square that no row used clears the query.
#pragma once

namespace OSSR = OmniSettingsSearch;

static void omniFxSettingsBuild(OmniFxPanel& p);
static bool omniFxSettingsInput(OmniFxPanel&, const OmniFxRow& r, int b);

static std::string omniSsrQuery;                  // the active query ("" = everything shown)
static std::string omniSsrEdit;                   // the keyboard's buffer
static std::vector<int> omniSsrShown;             // ids shown so far for this query, in order (OSSR::view)
static bool omniSsrBaseSet = false;               // the panel's own subtitle / hints, restored without a query
static std::string omniSsrBaseSubtitle, omniSsrBaseExtra;
static std::vector<std::pair<int, const char*>> omniSsrBaseFaces;

static bool omniSsrActive() { return !omniSsrQuery.empty(); }
static void omniSsrOpened() { omniSsrQuery.clear(); omniSsrShown.clear(); omniSsrBaseSet = false; }   // a fresh Browser settings
static OmniFxPanel* omniSsrPanel()
{
    if (omniFxStack.empty() || omniFxStack.back().build != omniFxSettingsBuild) return nullptr;
    return &omniFxStack.back();
}

static OmniFxRow omniSsrSearchRow()
{
    OmniFxRow r;
    r.id = OSSR::kSearchRowId;
    r.label = "Search settings\xe2\x80\xa6";
    r.value = omniSsrQuery.empty() ? std::string("Type a few letters") : "\"" + omniSsrQuery + "\"";
    return r;
}

// Called last in omniFxSettingsBuild, after every row (its own and every patch's) is in p.rows.
static void omniSsrFilter(OmniFxPanel& p)
{
    if (!omniSsrBaseSet) { omniSsrBaseSubtitle = p.subtitle; omniSsrBaseExtra = p.extra; omniSsrBaseFaces = p.faces; omniSsrBaseSet = true; }
    if (!omniSsrActive()) {   // without a query: every row as before, under the search row
        p.subtitle = omniSsrBaseSubtitle; p.extra = omniSsrBaseExtra; p.faces = omniSsrBaseFaces;
        p.rows.insert(p.rows.begin(), omniSsrSearchRow());
        return;
    }
    std::vector<OmniFxRow> rows = std::move(p.rows);
    std::vector<OSSR::Entry> list;
    list.reserve(rows.size());
    for (const auto& r : rows) list.push_back({ r.id, OSSR::sectionOf(r.label), r.label, r.value });
    const std::vector<size_t> pick = OSSR::view(list, omniSsrQuery, omniSsrShown);
    p.rows.clear();
    OmniFxRow search = omniSsrSearchRow();
    search.detail = pick.empty() ? std::string("Square clears") : std::to_string(pick.size()) + (pick.size() == 1 ? " match" : " matches") + ". Square clears";
    p.rows.push_back(std::move(search));
    for (size_t i : pick) {
        OmniFxRow r = rows[i];   // the row as built: same id (same handler), stepper, enabled, detail
        r.prefix = list[i].section;
        p.rows.push_back(std::move(r));
    }
    if (pick.empty()) {
        OmniFxRow none;
        none.id = OSSR::kNoMatchRowId; none.label = "No settings match"; none.enabled = false;
        none.detail = "Try another word, or Square to show all";
        p.rows.push_back(std::move(none));
    }
    p.subtitle = OSSR::countText(pick.size(), list.size(), omniSsrQuery);
    p.extra = "D-pad \xe2\x97\x80 \xe2\x96\xb6 change   Y reset";
    p.faces = { { 0, "Change" }, { 2, "Clear search" }, { 1, "Back" } };
}

// Clears the query; the row that had the highlight keeps it in the full list (Square on a found row = "show me
// this setting among the others").
static void omniSsrClear(OmniFxPanel& p, int keepId)
{
    omniSsrQuery.clear(); omniSsrShown.clear();
    omniFxRebuild(p);
    p.sel = 0;
    for (size_t i = 0; i < p.rows.size(); ++i) if (p.rows[i].id == keepId) { p.sel = int(i); break; }
    p.scroll = std::max(0, p.sel - p.maxVisible / 2);
    omniShellDirty = true;
}

static void omniSsrOpenKeyboard()
{
    omniSsrEdit = omniSsrQuery;
    omniKbEdit(&omniSsrEdit, "Search settings", [](bool ok) {
        OmniFxPanel* p = omniSsrPanel();
        if (!ok || !p) { omniFxRefresh(); return; }
        const std::string q = OSSR::cleanQuery(omniSsrEdit);
        if (q == omniSsrQuery) { omniFxRefresh(); return; }
        omniSsrQuery = q; omniSsrShown.clear();
        omniFxRebuild(*p);
        p->sel = q.empty() || p->rows.size() < 2 || !p->rows[1].enabled ? 0 : 1;   // the best match
        p->scroll = 0;
        omniShellDirty = true;
    });
}

static bool omniSsrPanelInput(OmniFxPanel& p, const OmniFxRow& r, int b)
{
    if (r.id == OSSR::kSearchRowId || r.id == OSSR::kNoMatchRowId) {
        if (b == SDL_CONTROLLER_BUTTON_A) { omniSsrOpenKeyboard(); return true; }
        if (b == SDL_CONTROLLER_BUTTON_X && omniSsrActive()) { omniSsrClear(p, OSSR::kSearchRowId); return true; }
        return false;
    }
    if (omniFxSettingsInput(p, r, b)) return true;   // the row's own handler, exactly as without a query
    if (b == SDL_CONTROLLER_BUTTON_X && omniSsrActive()) { omniSsrClear(p, r.id); return true; }
    return false;
}
