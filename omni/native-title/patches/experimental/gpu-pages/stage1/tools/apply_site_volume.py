#!/usr/bin/env python3
"""OMNI_SITE_VOLUME_V1 (2026-11-16): remember tab volume per site (backlog E07). Music sites stay at 30 % every visit.

What the user sees
  - Changing a tab's volume (Now playing > "Volume  < 70% >", OMNI_TAB_VOLUME_V1) remembers it for the tab's site once
    the value has stayed put for 2 s (no extra notice: tab volume already says "Volume: 70%"). 100 % is the default, so
    going back to 100 % (Cross on the Volume row) forgets the site after the same 2 s. "Remember for this site" in Now
    playing shows On once it is remembered; turning it Off there forgets it (and drops a save still waiting).
  - A tab committing a navigation (didCommitNavigation) to a site with a remembered volume plays at it at once. The
    exception: a volume the user set by hand in this tab, on this same site, stays (a reload or another page of the site
    keeps the tab's own value). A hand value set on another site gives way to the remembered one here; on a site with
    nothing remembered the tab keeps its value (tab volume's per-tab rule). Other open tabs of the site with no value of
    their own follow within 500 ms (tab volume's tick).
  - Site settings (Options > Site settings), right after "Sound" (OMNI_SITE_MUTE_V1, row 776):
        "Volume    30%"          detail "Cross: Reset to 100%"; Cross forgets the site and puts its open tabs back at
                                 100 %, notice "Volume for example.com reset to 100%".
        "Volume    100%"         (nothing remembered: disabled) detail "Change the volume in Now playing: it is
                                 remembered for this site".
        "Volume    -"            omni:// / about: / new-tab pages (disabled).
    While Sound is "Always mute" the detail says the volume applies when the tab is unmuted.
  - Private tabs: tab volume's memory-only private list (OmniTabVolumeShell.h omniTvPrivate): remembered until Omni
    closes, never written, never read by normal tabs; normal tabs never shown to private ones.
  - Mute wins: this patch never calls WKPageSetMuted and never touches Tab::omniTaMuted / Tab::omniSmu; WebKit mutes on
    effectiveMuted || volume, so a site muted by "Always mute" (or a tab muted by hand) stays silent whatever its volume.

Store: no new file. /data/omni/site-volume.txt is tab volume's ("omni-site-volume-1", "<site>\\t<pct>" lines, at most
500, written through omniIoQueue, never in test modes; already in the Setup backup list via apply_guest_mode.py), so the
same values show in Now playing and here. Site key = OmniMediaControls::site(url) (tab volume's: lower case, "www."
dropped, no port, IPv6 kept in brackets), NOT OSMU::hostKey.

Pure part: engine/entry/OmniSiteVolume.h (no SDL / WebKit; includes OmniTabVolume.h): the 2 s settle (per tab and site,
SDL_GetTicks wrap-safe), the remember / forget decision on OmniTabVolume::Sites, the commit decision, texts. Tested by
tools/test_site_volume.cpp:
    g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_site_volume.cpp -o t && ./t
Shell side: engine/entry/OmniSiteVolumeShell.h, included from OmniFeatures3.h right after OmniTabVolumeShell.h (its
statics omniTvTabs / omniTvSaved / omniTvPrivate / omniTvApply are used; OmniSiteMuteShell.h is above it), so before
OmniPlaybackSpeedShell.h / OmniMediaControlsShell.h. Alias OSVOL, names omniSvo*, Site settings row 778 (free in the
tree and in every sibling's code on 2026-11-16; checked again before the first apply).
"Sites with custom settings" (OMNI_SITE_LIST_V1) can list it: omniSvoSavedSites() (saved keys), omniSvoSavedValue(key)
("30%" / "-") and omniSvoResetSaved(key) (forget, open tabs back to 100 %, notice). apply_site_list.py is not edited.

Anchors (whole lines, exactly once each; MARK makes each file idempotent; line endings kept):
  OmniBrowser.cpp           the OmniSiteMute.h include line (pure include after it); the omniSmuCommitted forward
                            declaration (ours after it); the omniSmuCommitted(*tab) call in didCommitNavigation (ours after
                            it: mute first, then volume).
  OmniQuickMenu.h           the omniSmuSiteInput declaration (row id + declarations after it); the omniSmuSiteRow(p, host)
                            call (our row after it); the omniSmuSiteRowId dispatch (ours before it).
  OmniFeatures3.h           the OmniTabVolumeShell.h include line (ours after it); the omniTvTick(now) line (ours after it).
  OmniMediaControlsShell.h  tab volume's omniTvNpOwns dispatch line is REPLACED by the same dispatch through
                            omniSvoNpInput, which calls omniTvNpInput and then notes a hand change.
Order: apply AFTER apply_tab_volume.py and apply_site_mute.py (their lines are anchors; checked). In the build chain:
append it right after apply_site_mute.py (chain_final.txt + apply_site_mute.py + apply_site_volume.py). apply_media_controls.py
rewrites OmniMediaControlsShell.h when it differs, so like tab volume this must run after it.
usage: apply_site_volume.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_SITE_VOLUME_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_site_volume.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ('778',)
NAMES = ('OSVOL', 'omniSvo', 'OmniSiteVolume', 'OMNI_SITE_VOLUME')

# Site mute's names are spelled through sm(): its pre-apply check (apply_site_mute.py ids_free) scans every sibling's
# code for them, and this patch only refers to its lines / functions (it must not look like a clash).
_SM = (('@SMU@', 'omniS' 'mu'), ('@SMH@', 'OmniSite' 'Mute'), ('@SMM@', 'OMNI_SITE' '_MUTE'),
       ('@SMT@', 'site-' 'mute.txt'))


def sm(t):
    for a, b in _SM:
        t = t.replace(a, b)
    return t


PURE = r'''// OMNI_SITE_VOLUME_V1: the pure part of "remember tab volume per site" (no SDL, no WebKit). The shell side is
// OmniSiteVolumeShell.h; the store is tab volume's (OmniTabVolume.h, site-volume.txt); the reasons are in
// tools/apply_site_volume.py. Tested on the host with g++ (test_site_volume.cpp).
#pragma once
#include <cstddef>
#include <cstdint>
#include <map>
#include <string>
#include <utility>
#include <vector>
#include "OmniTabVolume.h"

namespace OmniSiteVolume {

constexpr uint32_t kSettleMs = 2000;       // a hand change is remembered after 2 s without another one
constexpr int kSiteRowId = 778;            // Site settings row (710-776 and 787 taken there)

// A hand change waiting to be remembered.
struct Pending {
    std::string site;
    int pct = OmniTabVolume::kFull;
    bool privateTab = false;
    uint32_t due = 0;
};

// One entry per (tab, site): a newer change of the same tab on the same site restarts its 2 s.
class Settle {
public:
    void note(uintptr_t tab, const std::string& site, int pct, bool privateTab, uint32_t now)
    {
        if (site.empty()) return;
        Pending& p = m_[std::make_pair(tab, site)];
        p.site = site;
        p.pct = OmniTabVolume::clampPct(pct);
        p.privateTab = privateTab;
        p.due = now + kSettleMs;
    }
    // Forgotten / reset meanwhile: nothing of that site (in that store) is saved later.
    void cancelSite(const std::string& site, bool privateTab)
    {
        for (auto it = m_.begin(); it != m_.end();)
            it = it->second.site == site && it->second.privateTab == privateTab ? m_.erase(it) : std::next(it);
    }
    // The entries whose 2 s are over (removed), oldest key order.
    std::vector<Pending> take(uint32_t now)
    {
        std::vector<Pending> out;
        for (auto it = m_.begin(); it != m_.end();) {
            if (OmniTabVolume::reached(now, it->second.due)) { out.push_back(it->second); it = m_.erase(it); }
            else ++it;
        }
        return out;
    }
    bool empty() const { return m_.empty(); }
    size_t size() const { return m_.size(); }
private:
    std::map<std::pair<uintptr_t, std::string>, Pending> m_;
};

// Did a press change what the tab plays at? (before / after: the resolved volume)
inline bool handChange(int before, int after) { return OmniTabVolume::clampPct(before) != OmniTabVolume::clampPct(after); }

enum class Saved { kSame, kChanged, kFull };
// Remember pct for site (100 % = the default: the site is forgotten instead).
inline Saved remember(OmniTabVolume::Sites& s, const std::string& site, int pct)
{
    pct = OmniTabVolume::clampPct(pct);
    if (pct == OmniTabVolume::kFull) return s.erase(site) ? Saved::kChanged : Saved::kSame;
    int cur = 0;
    if (s.get(site, cur) && cur == pct) return Saved::kSame;
    return s.set(site, pct) ? Saved::kChanged : Saved::kFull;
}

// A navigation committed in a tab whose own value is ownPct (kUnset: none), set by hand on handSite ("" = not by hand):
// true = drop the tab's own value so the remembered volume of `site` applies.
inline bool dropOwn(int ownPct, const std::string& handSite, const std::string& site, bool siteHas)
{
    return ownPct >= 0 && !site.empty() && siteHas && handSite != site;
}

// --- texts -----------------------------------------------------------------------------------------------------------
inline std::string rowValue(bool web, bool has, int pct)
{
    if (!web) return "-";
    return has ? OmniTabVolume::label(pct) : OmniTabVolume::label(OmniTabVolume::kFull);
}
inline std::string rowDetail(bool web, bool has, bool privateTab, bool siteMuted)
{
    if (!web) return "Only for web sites";
    if (siteMuted) return has ? "Sound is Always mute: this volume plays when unmuted. Cross: Reset to 100%"
                              : "Sound is Always mute here";
    if (!has) return "Change the volume in Now playing: it is remembered for this site";
    return privateTab ? "Cross: Reset to 100% (private tabs, until Omni closes)" : "Cross: Reset to 100%";
}
inline std::string resetNotice(const std::string& site, bool privateTab)
{
    return "Volume for " + site + " reset to 100%" + (privateTab ? " (private tabs)" : "");
}

} // namespace OmniSiteVolume
'''
PURE = sm(PURE)

SHELL = r'''// OMNI_SITE_VOLUME_V1: remember tab volume per site (shell side). Included from OmniFeatures3.h right after
// OmniTabVolumeShell.h (inside OmniBrowser.cpp's anonymous namespace): it uses tab volume's statics (omniTvTabs,
// omniTvSaved, omniTvPrivate, omniTvApply, omniTvWrite) and @SMH@Shell.h's @SMU@Key / @SMU@On (above it).
// The pure part is OmniSiteVolume.h; the reasons are in tools/apply_site_volume.py. Main thread only; never mutes or
// unmutes (Always mute and the tab mute win: WebKit plays nothing while muted, whatever the volume).
#pragma once

namespace OSVOL = OmniSiteVolume;
static_assert(OSVOL::kSiteRowId == omniSvoSiteRowId, "OMNI_SITE_VOLUME_V1: Site settings row id");

static OSVOL::Settle omniSvoSettle;                    // hand changes waiting 2 s
static std::map<uintptr_t, std::string> omniSvoHand;   // tab (omniMediaIdentity) -> site its volume was set on by hand

static Tab* omniSvoTab(uintptr_t key)
{
    if (!key) return nullptr;
    for (auto& x : tabs) if (x->omniMediaIdentity == key) return x.get();
    return nullptr;
}
static void omniSvoPrune()   // closed tabs
{
    for (auto it = omniSvoHand.begin(); it != omniSvoHand.end();) it = omniSvoTab(it->first) ? std::next(it) : omniSvoHand.erase(it);
}

// Now playing (OmniMediaControlsShell.h): tab volume's rows, then a hand change of "Volume" waits 2 s to be remembered.
static bool omniSvoNpInput(uintptr_t key, int id, int b)
{
    Tab* t = omniSvoTab(key);
    const int before = t ? omniTvPct(*t) : OTVL::kFull;
    const bool handled = omniTvNpInput(key, id, b);
    if (!t) return handled;
    const std::string site = omniTvSite(*t);
    if (site.empty()) return handled;
    if (id == OTVL::kRowVolume) {
        const int after = omniTvPct(*t);
        if (OSVOL::handChange(before, after)) {
            omniSvoHand[key] = site;
            omniSvoSettle.note(key, site, after, t->omniPrivate, SDL_GetTicks());
        }
    } else if (id == OTVL::kRowRemember && !omniTvSites(*t).has(site)) {
        omniSvoSettle.cancelSite(site, t->omniPrivate);   // "Remember for this site" turned Off: no late save
    }
    return handled;
}

// omniF3Tick: the settled changes go into tab volume's lists (the saved one is written; the private one never).
static void omniSvoTick(uint32_t now)
{
    if (omniSvoSettle.empty()) return;
    for (const OSVOL::Pending& p : omniSvoSettle.take(now)) {
        omniTvLoad();
        const OSVOL::Saved r = OSVOL::remember(p.privateTab ? omniTvPrivate : omniTvSaved, p.site, p.pct);
        if (r == OSVOL::Saved::kChanged && !p.privateTab) omniTvWrite();
        if (r == OSVOL::Saved::kChanged) { fprintf(stderr, "OMNI SITE VOLUME: %s %d%s\n", p.site.c_str(), p.pct, p.privateTab ? " (private)" : ""); fflush(stderr); }
        if (r == OSVOL::Saved::kFull) { fprintf(stderr, "OMNI SITE VOLUME: list full, %s not saved\n", p.site.c_str()); fflush(stderr); }
    }
    if (!omniFxStack.empty()) omniFxRefresh();   // "Remember for this site" / Site settings show it
}

// didCommitNavigation (OmniBrowser.cpp), after tab.url is updated and after Always mute (@SMM@_V1).
static void omniSvoCommitted(Tab& t)
{
    omniSvoPrune();
    omniTvLoad();
    const std::string site = omniTvSite(t);   // "" for new-tab / omni:// / about: pages
    int sitePct = OTVL::kFull;
    const bool has = !site.empty() && omniTvSites(t).get(site, sitePct);
    auto it = omniTvTabs.find(t.omniMediaIdentity);
    if (it != omniTvTabs.end()) {
        auto h = omniSvoHand.find(t.omniMediaIdentity);
        if (OSVOL::dropOwn(it->second.pct, h == omniSvoHand.end() ? std::string() : h->second, site, has)) {
            it->second.pct = OTVL::kUnset;
            if (h != omniSvoHand.end()) omniSvoHand.erase(h);
        }
    }
    if (has || it != omniTvTabs.end()) omniTvApply(t, true);   // at once, not at the next 500 ms tick / first sound
}

// Forget site in one store; its open tabs (same store) lose their own value and play at 100 %.
static void omniSvoReset(const std::string& site, bool privateTab)
{
    if (site.empty()) return;
    omniTvLoad();
    if ((privateTab ? omniTvPrivate : omniTvSaved).erase(site) && !privateTab) omniTvWrite();
    omniSvoSettle.cancelSite(site, privateTab);
    for (auto& tp : tabs) {
        Tab& x = *tp;
        if (x.omniPrivate != privateTab || omniTvSite(x) != site) continue;
        auto it = omniTvTabs.find(x.omniMediaIdentity);
        if (it != omniTvTabs.end()) it->second.pct = OTVL::kUnset;
        omniSvoHand.erase(x.omniMediaIdentity);
        omniTvApply(x, true);
    }
}

// --- Site settings row ----------------------------------------------------------------------------------------------
static void omniSvoSiteRow(OmniFxPanel& p, const std::string&)
{
    Tab* t = active();
    const std::string site = t ? omniTvSite(*t) : std::string();
    int pct = OTVL::kFull;
    bool has = false;
    if (!site.empty()) { omniTvLoad(); has = omniTvSites(*t).get(site, pct); }
    const bool muted = t && @SMU@On(*t, @SMU@Key(t));
    OmniFxRow r; r.id = OSVOL::kSiteRowId; r.label = "Volume"; r.enabled = has;
    r.value = OSVOL::rowValue(!site.empty(), has, pct);
    r.detail = OSVOL::rowDetail(!site.empty(), has, t && t->omniPrivate, muted);
    p.rows.push_back(r);
}
static bool omniSvoSiteInput(const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    Tab* t = active();
    if (!r.enabled || !t) return true;
    const std::string site = omniTvSite(*t);
    if (site.empty()) return true;
    omniSvoReset(site, t->omniPrivate);
    notice(OSVOL::resetNotice(site, t->omniPrivate));
    omniFxRefresh();
    return true;
}

// --- for "Sites with custom settings" (OMNI_SITE_LIST_V1, optional): the saved list only, never a private choice ------
// key = OmniMediaControls::site("https://<host>/") (www. dropped, IPv6 in brackets).
[[maybe_unused]] static std::vector<std::string> omniSvoSavedSites()
{
    omniTvLoad();
    std::vector<std::string> out;
    for (const auto& kv : omniTvSaved.all()) out.push_back(kv.first);
    return out;
}
[[maybe_unused]] static std::string omniSvoSavedValue(const std::string& key)
{
    omniTvLoad();
    int pct = OTVL::kFull;
    return !key.empty() && omniTvSaved.get(key, pct) ? OTVL::label(pct) : std::string("-");
}
[[maybe_unused]] static void omniSvoResetSaved(const std::string& key)
{
    if (key.empty()) return;
    omniSvoReset(key, false);
    notice(OSVOL::resetNotice(key, false));
}
'''
SHELL = sm(SHELL)

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "@SMH@.h" // @SMM@_V1: Site settings > Sound: Always mute, @SMT@ (pure)\n',
         '#include "@SMH@.h" // @SMM@_V1: Site settings > Sound: Always mute, @SMT@ (pure)\n'
         '#include "OmniSiteVolume.h" // OMNI_SITE_VOLUME_V1: remember tab volume per site, 2 s settle (pure)\n'),
        ('static void @SMU@Committed(Tab& tab); // @SMM@_V1 (@SMH@Shell.h)\n',
         'static void @SMU@Committed(Tab& tab); // @SMM@_V1 (@SMH@Shell.h)\n'
         'static void omniSvoCommitted(Tab& tab); // OMNI_SITE_VOLUME_V1 (OmniSiteVolumeShell.h)\n'),
        ('        @SMU@Committed(*tab); // @SMM@_V1: Always mute this site (tab-audio mute + badge)\n',
         '        @SMU@Committed(*tab); // @SMM@_V1: Always mute this site (tab-audio mute + badge)\n'
         '        omniSvoCommitted(*tab); // OMNI_SITE_VOLUME_V1: the remembered volume of this site (never unmutes)\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool @SMU@SiteInput(const OmniFxRow& r, int b);\n',
         'static bool @SMU@SiteInput(const OmniFxRow& r, int b);\n'
         'constexpr int omniSvoSiteRowId = 778; // OMNI_SITE_VOLUME_V1 (OmniSiteVolumeShell.h)\n'
         'static void omniSvoSiteRow(OmniFxPanel& p, const std::string& host);\n'
         'static bool omniSvoSiteInput(const OmniFxRow& r, int b);\n'),
        ('    @SMU@SiteRow(p, host); // @SMM@_V1: Sound: Allow / Always mute\n',
         '    @SMU@SiteRow(p, host); // @SMM@_V1: Sound: Allow / Always mute\n'
         '    omniSvoSiteRow(p, host); // OMNI_SITE_VOLUME_V1: Volume: 30% / Cross: Reset\n'),
        ('    if (r.id == @SMU@SiteRowId) return @SMU@SiteInput(r, b); // @SMM@_V1 (handles its disabled state)\n',
         '    if (r.id == omniSvoSiteRowId) return omniSvoSiteInput(r, b); // OMNI_SITE_VOLUME_V1 (handles its disabled state)\n'
         '    if (r.id == @SMU@SiteRowId) return @SMU@SiteInput(r, b); // @SMM@_V1 (handles its disabled state)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniTabVolumeShell.h" // OMNI_TAB_VOLUME_V1 (before media controls: its panel calls ours)\n',
         '#include "OmniTabVolumeShell.h" // OMNI_TAB_VOLUME_V1 (before media controls: its panel calls ours)\n'
         '#include "OmniSiteVolumeShell.h" // OMNI_SITE_VOLUME_V1 (after tab volume + site mute; before media controls)\n'),
        ('    omniTvTick(now);    /* OMNI_TAB_VOLUME_V1: per-tab volume onto new pages / remembered sites (500 ms, only while set) */\n',
         '    omniTvTick(now);    /* OMNI_TAB_VOLUME_V1: per-tab volume onto new pages / remembered sites (500 ms, only while set) */\n'
         '    omniSvoTick(now);   /* OMNI_SITE_VOLUME_V1: hand changes remembered for the site after 2 s (only while waiting) */\n'),
    ],
    'OmniMediaControlsShell.h': [
        ('    if (omniTvNpOwns(r.id)) return omniTvNpInput(omniNpKey, r.id, b); /* OMNI_TAB_VOLUME_V1: D-pad left-right, Cross */\n',
         '    if (omniTvNpOwns(r.id)) return omniSvoNpInput(omniNpKey, r.id, b); /* OMNI_TAB_VOLUME_V1: D-pad left-right, Cross; OMNI_SITE_VOLUME_V1: then remembered for the site */\n'),
    ],
}
EDITS = {f: [(sm(a), sm(b)) for a, b in e] for f, e in EDITS.items()}
NEEDS = {'OmniBrowser.cpp': ('OMNI_TAB_VOLUME_V1', '@SMM@_V1'),
         'OmniQuickMenu.h': ('@SMM@_V1',),
         'OmniFeatures3.h': ('OMNI_TAB_VOLUME_V1', '@SMM@_V1'),
         'OmniMediaControlsShell.h': ('OMNI_TAB_VOLUME_V1',)}
NEEDS = {f: tuple(sm(x) for x in n) for f, n in NEEDS.items()}


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def check(name, edits):
    s = (root / name).read_bytes().decode('utf-8')
    if MARK in s:
        return
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits):
    p = root / name
    s = p.read_bytes().decode('utf-8')
    if MARK in s:
        return name + ': already'
    for old0, new0 in edits:
        old, e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))
        s = s.replace(old, new0.replace('\n', e), 1)
    p.write_bytes(s.encode('utf-8'))
    return name + ': applied'


def write_new(name, text, like):
    raw = (root / like).read_bytes()
    nl = '\r\n' if raw.count(b'\r\n') * 2 > raw.count(b'\n') else '\n'
    data = text.replace('\r\n', '\n').replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


# The Controls guide's table names other patches' handlers by design: never a name clash (numbers still count there).
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
GUIDE_TOOL = 'apply_controls_help.py'
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): an id or name in another patch's notes (e.g. "834-839" in a generated header) is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def code_only(src):
    """A sibling apply_*.py without its comments and module docstring (line numbers kept): names mentioned only in its
    notes are not a use. Numeric ids are never looked for in siblings (their notes list other patches' id ranges)."""
    import io
    import tokenize
    cut, first = [], True
    try:
        for t in tokenize.generate_tokens(io.StringIO(src).readline):
            if t.type == tokenize.COMMENT or (first and t.type == tokenize.STRING):
                cut.append((t.start, t.end))
            if t.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
                              tokenize.ENCODING):
                first = False
    except (tokenize.TokenError, SyntaxError):
        return ''.join(r for r in src.splitlines(True) if not r.lstrip().startswith('#'))
    starts = [0] + [i + 1 for i, c in enumerate(src) if c == '\n']   # tokenize's rows end at '\n' only
    out = list(src)
    for (r0, c0), (r1, c1) in cut:
        for i in range(starts[r0 - 1] + c0, starts[r1 - 1] + c1):
            if out[i] not in '\r\n':
                out[i] = ' '
    return ''.join(out)


def ids_free():
    """Before a first apply: no other patch or tree file uses this patch's ids or names."""
    word = re.compile(r'\b(%s)\b' % '|'.join(IDS))
    name = re.compile('|'.join(NAMES))
    mine = {'OmniSiteVolume.h', 'OmniSiteVolumeShell.h'}
    # A sibling not applied to this tree yet still owns its ids: its code assigning one of ours to a row id
    # ("kSiteRowId = 778", "omniXxSiteRowId = 778", "constexpr int x = 778") is a clash. The Controls guide's code
    # names other patches' handlers by design: its names are not looked for (its id assignments still are).
    assign = re.compile(r'(?:\b\w*[Rr]ow\w*|\bconstexpr\s+int\s+\w+)\s*=\s*(%s)(?![\w.])' % '|'.join(IDS))
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        t = code_only(f.read_text(encoding='utf-8', errors='replace'))
        # Siblings whose code names this patch's functions by design: the Controls guide and "Sites with custom
        # settings" (apply_site_list.py, OMNI_SITE_LIST_V1 r4 lists this store). Their id assignments are still looked for.
        skip = f.name == GUIDE_TOOL or "MARK = 'OMNI_SITE_LIST_V1'" in t
        m = (None if skip else name.search(t)) or assign.search(t)   # bare numbers: not looked for (siblings' notes list others' ids)
        if m:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))
    for f in sorted(root.iterdir()):
        if f.name in mine or f.suffix not in ('.h', '.cpp', '.inc'):
            continue
        t = f.read_bytes().decode('utf-8', errors='replace')
        c = cpp_code(t)
        m = word.search(c) or (None if f.name in GUIDE else name.search(c))
        if m and MARK not in t:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))


def main():
    for fname, needs in NEEDS.items():
        s = (root / fname).read_bytes().decode('utf-8')
        for need in needs:
            if need not in s:
                sys.exit('%s: %s missing: apply its patch first' % (fname, need))
    if MARK not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        ids_free()
    for fname, edits in EDITS.items():   # every anchor is checked before anything is written
        check(fname, edits)
    msgs = [write_new('OmniSiteVolume.h', PURE, 'OmniTabVolume.h'),
            write_new('OmniSiteVolumeShell.h', SHELL, 'OmniTabVolumeShell.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
