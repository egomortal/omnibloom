// OMNI_ZAPPER_V1: the pure part of the element zapper (no SDL, no WebKit): the user rules file
// (/data/omni/ublock-user-filters.txt, uBlock syntax), which lines become cosmetic rules, the per-host style sheet, the
// selector checks, the page script (picker, outline box, selector generator, page-only hide / unhide) and the texts.
// The shell side is OmniZapperShell.h; the reasons are in tools/apply_zapper.py. Tested on the host with g++
// (tools/test_zapper.cpp) and node (tools/test_zapper_js.cjs: the page script on a fake DOM).
#pragma once
#include <cstddef>
#include <cstdio>
#include <map>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace OmniZapper {

constexpr const char* kFileName = "ublock-user-filters.txt";   // under OMNI_DATA_DIR (/data/omni/)
constexpr size_t kMaxFileBytes = 256 * 1024;   // read cap; a longer file is cut at the last whole line
constexpr size_t kMaxLines = 3000;             // lines kept (all kinds); the zapper adds no line past it
constexpr size_t kMaxPerHost = 100;            // zapper rules for one host
constexpr size_t kMaxSelector = 280;           // characters in one selector
constexpr size_t kHostMax = 253;
constexpr int kConfirmOver = 10;               // a selector matching more elements than this asks first
constexpr int kSiteRowId = 7925;               // Site settings > "Hidden elements"
constexpr int kContextId = 9925;               // hold-Cross page menu: "Hide this element..."
constexpr int kUndoId = 9926;                  // hold-Cross page menu: "Undo hide element"
constexpr unsigned kFollowMs = 100;            // the pointer moved: re-pick at most this often
constexpr unsigned kSyncMs = 400;              // the pointer is still: re-place the box (page scrolled) this often
constexpr unsigned kBusyMs = 2000;             // a page that never answers frees the query slot after this
constexpr const char* kHeader = "! Omni: my filters (uBlock Origin syntax). The element zapper adds host##selector lines.";

inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c + ('a' - 'A')) : c; }
inline std::string trim(const std::string& s)
{
    size_t a = 0, b = s.size();
    while (a < b && (s[a] == ' ' || s[a] == '\t' || s[a] == '\r')) ++a;
    while (b > a && (s[b - 1] == ' ' || s[b - 1] == '\t' || s[b - 1] == '\r')) --b;
    return s.substr(a, b - a);
}

// --- hosts --------------------------------------------------------------------------------------------------------
// A rule host: lower case letters, digits, '.', '-' (IDN as punycode); no empty label.
inline bool validHost(const std::string& h)
{
    if (h.empty() || h.size() > kHostMax || h.front() == '.' || h.back() == '.' || h.find("..") != std::string::npos) return false;
    for (char c : h) if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '-')) return false;
    return true;
}
inline bool isIPv4(const std::string& h)
{
    int parts = 0, digits = 0, value = 0;
    for (size_t i = 0; i <= h.size(); ++i) {
        if (i == h.size() || h[i] == '.') {
            if (!digits || value > 255) return false;
            ++parts; digits = 0; value = 0;
            continue;
        }
        if (h[i] < '0' || h[i] > '9' || ++digits > 3) return false;
        value = value * 10 + (h[i] - '0');
    }
    return parts == 4;
}
// uBlock's hostname rule: "example.com##x" applies on example.com and every subdomain of it.
inline bool hostCovers(const std::string& ruleHost, const std::string& pageHost)
{
    if (ruleHost.empty() || pageHost.empty()) return false;
    if (pageHost == ruleHost) return true;
    return pageHost.size() > ruleHost.size() && pageHost.compare(pageHost.size() - ruleHost.size(), ruleHost.size(), ruleHost) == 0
        && pageHost[pageHost.size() - ruleHost.size() - 1] == '.';
}
// WebKit user-content URL patterns for a rule host's sheet: "*." also matches the host itself (UserContentURLPattern).
inline std::vector<std::string> allowPatterns(const std::string& host)
{
    std::vector<std::string> out;
    if (!validHost(host)) return out;
    out.push_back(isIPv4(host) ? "*://" + host + "/*" : "*://*." + host + "/*");
    return out;
}

// --- selectors ------------------------------------------------------------------------------------------------------
// uBlock procedural / action operators: not plain CSS, never put in a style sheet (the line is kept in the file).
inline bool procedural(const std::string& s)
{
    static const char* const ops[] = { ":has-text(", ":style(", ":remove(", ":matches-css", ":upward(", ":xpath(", ":-abp-",
        ":min-text-length(", ":watch-attr(", ":others(", ":matches-path(", ":matches-attr(", ":matches-media(",
        ":remove-attr(", ":remove-class(", ":matches-prop(", ":if(", ":if-not(", ":nth-ancestor(", ":spath(", ":contains(" };
    for (const char* op : ops) if (s.find(op) != std::string::npos) return true;
    return false;
}
// A selector that is safe inside "<selector>{display:none!important}": it cannot close the rule or open another one,
// start a comment or an at-rule; brackets, parentheses and quotes are balanced.
inline bool cssSafe(const std::string& s)
{
    if (s.empty() || s.size() > kMaxSelector) return false;
    if (s.find("/*") != std::string::npos || s.find("*/") != std::string::npos) return false;
    const char f = s[0];
    if (f == '@' || f == '>' || f == '+' || f == '~' || f == ',' || f == ' ') return false;
    int paren = 0, bracket = 0;
    char quote = 0;
    for (size_t i = 0; i < s.size(); ++i) {
        const unsigned char c = static_cast<unsigned char>(s[i]);
        if (c < 0x20 || c == 0x7f || c == '{' || c == '}' || c == ';' || c == '<' || c == '\\') return false;
        if (quote) { if (c == quote) quote = 0; continue; }
        if (c == '"' || c == '\'') quote = char(c);
        else if (c == '(') ++paren;
        else if (c == ')') { if (--paren < 0) return false; }
        else if (c == '[') ++bracket;
        else if (c == ']') { if (--bracket < 0) return false; }
    }
    return !quote && !paren && !bracket && !procedural(s);
}
// What the page script's generator makes: "#id", ".a.b", "tag", "tag.a:nth-of-type(3)" joined by " > ". Anything else
// coming back from the page (a page that replaced our script's helpers) is refused before it is saved.
inline bool generatedShape(const std::string& s)
{
    if (!cssSafe(s)) return false;
    for (char c : s) {
        const bool ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_'
            || c == '#' || c == '.' || c == ':' || c == '(' || c == ')' || c == '>' || c == ' ';
        if (!ok) return false;
    }
    return s.find("  ") == std::string::npos && s.back() != ' ' && s.back() != '>';
}

// --- the rules file ---------------------------------------------------------------------------------------------------
// One uBlock filter per line. Lines the zapper does not understand (comments "!", network filters, generic "##x",
// exceptions "#@#", "~host" negations, scriptlets "##+js(", HTML filters "##^", procedural operators) are kept as they
// are and never applied here: the file stays a valid uBlock "My filters" list.
struct Line {
    std::vector<std::string> hosts;   // the plain hosts of a "h1,h2##selector" line (empty: not a cosmetic host rule)
    std::string selector;
};
inline Line parseLine(const std::string& raw)
{
    Line out;
    const std::string s = trim(raw);
    if (s.empty() || s[0] == '!' || s[0] == '[') return out;
    const size_t sep = s.find("##");
    if (sep == std::string::npos || sep == 0) return out;                 // network filter / generic rule
    if (s.find("#@#") != std::string::npos || s.find("#?#") != std::string::npos || s.find("#$#") != std::string::npos) return out;
    const std::string sel = s.substr(sep + 2);
    if (sel.empty() || sel[0] == '+' || sel[0] == '^') return out;       // scriptlet / HTML filter
    if (!cssSafe(sel)) return out;
    std::vector<std::string> hosts;
    const std::string list = s.substr(0, sep);
    size_t p = 0;
    while (p <= list.size()) {
        size_t c = list.find(',', p);
        if (c == std::string::npos) c = list.size();
        std::string h;
        for (char ch : trim(list.substr(p, c - p))) h += lower(ch);
        if (!validHost(h)) return out;                                     // "~h", "h.*" entities, "/re/": not ours
        hosts.push_back(h);
        p = c + 1;
    }
    out.hosts = std::move(hosts);
    out.selector = sel;
    return out;
}
struct Store {
    std::vector<std::string> lines;   // the file, line by line, as written (no line ends)
};
inline Store parse(const std::string& text0)
{
    Store st;
    std::string text = text0.size() > kMaxFileBytes ? text0.substr(0, kMaxFileBytes) : text0;
    if (text0.size() > kMaxFileBytes) { const size_t nl = text.rfind('\n'); text.resize(nl == std::string::npos ? 0 : nl); }
    size_t p = 0;
    while (p < text.size() && st.lines.size() < kMaxLines) {
        size_t e = text.find('\n', p);
        if (e == std::string::npos) e = text.size();
        std::string l = text.substr(p, e - p);
        if (!l.empty() && l.back() == '\r') l.pop_back();
        st.lines.push_back(l);
        p = e + 1;
    }
    while (!st.lines.empty() && trim(st.lines.back()).empty()) st.lines.pop_back();
    return st;
}
inline std::string serialize(const Store& st)
{
    std::string out;
    for (const auto& l : st.lines) out += l + "\n";
    return out;
}
struct Rule { std::string host, selector; };
// Every applicable (host, selector) pair, in file order, without repeats.
inline std::vector<Rule> rules(const Store& st)
{
    std::vector<Rule> out;
    std::set<std::string> seen;
    for (const auto& l : st.lines) {
        const Line pl = parseLine(l);
        for (const auto& h : pl.hosts)
            if (seen.insert(h + '\n' + pl.selector).second) out.push_back(Rule { h, pl.selector });
    }
    return out;
}
// Every rule host with its user style sheet (one rule per selector: one bad selector never drops the others), in
// file order; one pass over the file.
inline std::vector<std::pair<std::string, std::string>> sheets(const Store& st)
{
    std::vector<std::pair<std::string, std::string>> out;
    std::map<std::string, size_t> at;
    for (const auto& r : rules(st)) {
        auto it = at.find(r.host);
        if (it == at.end()) { it = at.emplace(r.host, out.size()).first; out.emplace_back(r.host, std::string()); }
        out[it->second].second += r.selector + "{display:none!important}\n";
    }
    return out;
}
// The rules that apply on a page of pageHost (its own and its parent domains'): Site settings > Hidden elements.
inline std::vector<Rule> rulesFor(const Store& st, const std::string& pageHost)
{
    std::vector<Rule> out;
    for (const auto& r : rules(st)) if (hostCovers(r.host, pageHost)) out.push_back(r);
    return out;
}
enum class Added { Ok, Exists, Invalid, HostFull, FileFull };
inline Added add(Store& st, const std::string& host, const std::string& selector)
{
    if (!validHost(host) || !cssSafe(selector)) return Added::Invalid;
    size_t forHost = 0;
    for (const auto& r : rules(st)) {
        if (r.host == host && r.selector == selector) return Added::Exists;
        if (r.host == host) ++forHost;
    }
    if (forHost >= kMaxPerHost) return Added::HostFull;
    if (st.lines.size() + 2 > kMaxLines) return Added::FileFull;
    if (st.lines.empty()) st.lines.push_back(kHeader);
    st.lines.push_back(host + "##" + selector);
    return Added::Ok;
}
// Removes host from every line "…host…##selector" (a line left without hosts goes). Returns how many lines changed.
inline int remove(Store& st, const std::string& host, const std::string& selector)
{
    int changed = 0;
    std::vector<std::string> keep;
    for (const auto& l : st.lines) {
        const Line pl = parseLine(l);
        bool has = pl.selector == selector;
        if (has) { has = false; for (const auto& h : pl.hosts) if (h == host) has = true; }
        if (!has) { keep.push_back(l); continue; }
        ++changed;
        std::string hosts;
        for (const auto& h : pl.hosts) if (h != host) hosts += (hosts.empty() ? "" : ",") + h;
        if (!hosts.empty()) keep.push_back(hosts + "##" + selector);
    }
    st.lines.swap(keep);
    if (st.lines.size() == 1 && st.lines[0] == kHeader) st.lines.clear();
    return changed;
}

// --- the page script ------------------------------------------------------------------------------------------------
// A JavaScript string literal (double quotes), also safe inside an HTML <script>.
inline std::string jsString(const std::string& s)
{
    static const char* const hex = "0123456789abcdef";
    std::string out = "\"";
    for (size_t i = 0; i < s.size(); ++i) {
        const unsigned char c = static_cast<unsigned char>(s[i]);
        if (c == '"') out += "\\\"";
        else if (c == '\\') out += "\\\\";
        else if (c == '\n') out += "\\n";
        else if (c == '\r') out += "\\r";
        else if (c == '<' || c == '>' || c == '&' || c < 0x20 || c == 0x7f) { out += "\\u00"; out += hex[c >> 4]; out += hex[c & 15]; }
        else if (c == 0xe2 && i + 2 < s.size() && static_cast<unsigned char>(s[i + 1]) == 0x80
                 && (static_cast<unsigned char>(s[i + 2]) == 0xa8 || static_cast<unsigned char>(s[i + 2]) == 0xa9)) {
            out += static_cast<unsigned char>(s[i + 2]) == 0xa8 ? "\\u2028" : "\\u2029";
            i += 2;
        } else out += char(c);
    }
    return out + "\"";
}
// One function expression, called with (op, x, y, selector); x / y are CSS pixels of the main frame's viewport.
// State lives on the page's window (__omniZapV1): the picked path (innermost element first), the depth, the outline
// box, and the page-only hides with each element's previous inline display (for Undo). The answer is JSON:
//   start / move / up / down: {"ok":1,"sel":"…","n":3,"label":"div.banner","w":640,"h":120,"i":0,"top":5[,"edge":1]}
//   sync {"ok":1}   hide / unhide {"ok":1,"n":2}   clear {"ok":1}   failure {"ok":0}
// The generator: "#id" when the id is stable and unique; else ".a.b" (at most 2 stable classes) or the tag; when that
// is not unique, "tag.a.b:nth-of-type(k)"; then the same for the parent, joined by " > ", at most 4 levels, stopping
// at the first unique selector (or a unique stable id). Ids / classes that look generated (4+ digits in a row,
// css- / sc- / jsx- / svelte- / emotion- / tw- prefixes, letter-digit mixes of 5+, 3+ inner capitals) are skipped.
constexpr const char* kCore = R"JS(function (OP, X, Y, SEL) {
  var W = window, D = document, K = "__omniZapV1", MAXN = 9999;
  var S = W[K];
  if (!S || S.doc !== D) {
    S = { doc: D, path: [], i: 0, box: null, hidden: [] };
    try { Object.defineProperty(W, K, { value: S, configurable: true, writable: true }); } catch (e) { W[K] = S; }
  }
  function tagOf(e) { return String((e && e.tagName) || "").toLowerCase(); }
  function okIdent(s) { return typeof s === "string" && s.length > 0 && s.length <= 48 && /^-?[A-Za-z_][A-Za-z0-9_-]*$/.test(s); }
  function generated(s) {
    if (/[0-9]{4,}/.test(s) || /^(css|sc|jsx|svelte|emotion|tw)-/i.test(s)) return true;
    var parts = s.split(/[-_]+/);
    for (var j = 0; j < parts.length; j++) {
      var q = parts[j];
      if (q.length >= 5 && /[0-9]/.test(q) && /[A-Za-z]/.test(q)) return true;
      if (q.length >= 6 && (q.slice(1).match(/[A-Z]/g) || []).length >= 3) return true;
    }
    return false;
  }
  function usable(e) {
    if (!e || e.nodeType !== 1 || e === S.box) return false;
    var t = tagOf(e);
    return t !== "" && t !== "html" && t !== "body" && t !== "head";
  }
  function count(sel) { try { return Math.min(D.querySelectorAll(sel).length, MAXN); } catch (e) { return -1; } }
  function classesOf(e) {
    var raw = typeof e.className === "string" ? e.className : (e.getAttribute && e.getAttribute("class")) || "";
    var list = String(raw).split(/\s+/), out = [];
    for (var j = 0; j < list.length && out.length < 2; j++) {
      var c = list[j];
      if (okIdent(c) && !generated(c) && out.indexOf(c) < 0) out.push(c);
    }
    return out;
  }
  function nthOf(e) {
    var p = e.parentElement;
    if (!p) return 0;
    var c = p.children, k = 0, n = 0;
    for (var j = 0; j < c.length; j++) if (c[j].tagName === e.tagName) { n++; if (c[j] === e) k = n; }
    return n > 1 ? k : 0;
  }
  function selectorFor(e) {
    var parts = [], cur = e, found = false;
    for (var lvl = 0; lvl < 4 && usable(cur); lvl++) {
      var tail = parts.length ? " > " + parts.join(" > ") : "";
      if (cur.id && okIdent(cur.id) && !generated(cur.id) && count("#" + cur.id) === 1) { parts.unshift("#" + cur.id); found = true; break; }
      var t = tagOf(cur), cls = classesOf(cur);
      if (!/^[a-z][a-z0-9-]*$/.test(t)) return null;
      var dots = cls.length ? "." + cls.join(".") : "";
      var plain = dots || t;
      if (count(plain + tail) === 1) { parts.unshift(plain); found = true; break; }
      var k = nthOf(cur);
      parts.unshift(t + dots + (k ? ":nth-of-type(" + k + ")" : ""));
      if (count(parts.join(" > ")) === 1) { found = true; break; }
      cur = cur.parentElement;
    }
    if (!parts.length) return null;
    var sel = parts.join(" > ");
    if (sel.length > 280) return null;
    try { if (e.matches && !e.matches(sel)) return null; } catch (x) { return null; }
    return { sel: sel, n: count(sel), unique: found };
  }
  function hit(x, y) {
    var es = D.elementsFromPoint ? D.elementsFromPoint(x, y) : [D.elementFromPoint(x, y)];
    for (var j = 0; es && j < es.length; j++) if (usable(es[j])) return es[j];
    return null;
  }
  function pathFrom(e) { var p = []; while (usable(e) && p.length < 32) { p.push(e); e = e.parentElement; } return p; }
  function removeBox() { if (S.box && S.box.parentNode) S.box.parentNode.removeChild(S.box); S.box = null; }
  function place() {
    var e = S.path[S.i];
    if (!e || e.isConnected === false) return false;
    if (!S.box || !S.box.parentNode) {
      var b = D.createElement("div");
      b.setAttribute("data-omni-zap", "1");
      b.style.cssText = "position:fixed!important;pointer-events:none!important;z-index:2147483647!important;box-sizing:border-box!important;margin:0!important;padding:0!important;border:3px solid #ff3b3b!important;background:rgba(255,59,59,.16)!important;outline:2px solid rgba(255,255,255,.85)!important;border-radius:2px!important;display:block!important;transition:none!important";
      (D.documentElement || D.body).appendChild(b);
      S.box = b;
    }
    var r = e.getBoundingClientRect(), st = S.box.style;
    st.setProperty("left", r.left + "px", "important");
    st.setProperty("top", r.top + "px", "important");
    st.setProperty("width", Math.max(r.width, 2) + "px", "important");
    st.setProperty("height", Math.max(r.height, 2) + "px", "important");
    return true;
  }
  function info(edge) {
    var e = S.path[S.i];
    if (!e || !place()) { removeBox(); S.path = []; return { ok: 0 }; }
    var g = selectorFor(e), r = e.getBoundingClientRect(), cls = classesOf(e);
    var label = tagOf(e) + (e.id && okIdent(e.id) && !generated(e.id) ? "#" + e.id : cls.length ? "." + cls[0] : "");
    var o = { ok: 1, sel: g ? g.sel : "", n: g ? g.n : 0, label: label.slice(0, 60), w: Math.round(r.width), h: Math.round(r.height), i: S.i, top: S.path.length - 1 };
    if (edge) o.edge = 1;
    return o;
  }
  var r = { ok: 0 };
  try {
    if (OP === "start" || OP === "move") {
      var e = hit(X, Y);
      if (OP === "start" || (e && S.path[0] !== e)) { S.path = pathFrom(e); S.i = 0; }
      r = info(false);
    } else if (OP === "up") {
      var top = S.i + 1 >= S.path.length;
      if (!top) S.i++;
      r = info(top);
    } else if (OP === "down") {
      var bottom = S.i <= 0;
      if (!bottom) S.i--;
      r = info(bottom);
    } else if (OP === "sync") {
      r = S.path.length && place() ? { ok: 1 } : { ok: 0 };
      if (!r.ok) { removeBox(); S.path = []; }
    } else if (OP === "hide") {
      removeBox(); S.path = [];
      var list = D.querySelectorAll(SEL), items = [];
      for (var j = 0; j < list.length && j < 500; j++) {
        var h = list[j];
        items.push([h, h.style.getPropertyValue("display"), h.style.getPropertyPriority("display")]);
        h.style.setProperty("display", "none", "important");
      }
      S.hidden.push({ sel: SEL, items: items });
      if (S.hidden.length > 50) S.hidden.shift();
      r = { ok: 1, n: items.length };
    } else if (OP === "unhide") {
      for (var u = S.hidden.length - 1; u >= 0; u--) {
        if (S.hidden[u].sel !== SEL) continue;
        var it = S.hidden[u].items;
        for (var v = 0; v < it.length; v++) {
          if (it[v][1]) it[v][0].style.setProperty("display", it[v][1], it[v][2]);
          else it[v][0].style.removeProperty("display");
        }
        S.hidden.splice(u, 1);
        r = { ok: 1, n: it.length };
        break;
      }
    } else if (OP === "clear") {
      removeBox(); S.path = []; S.i = 0;
      r = { ok: 1 };
    }
  } catch (err) { r = { ok: 0 }; }
  return JSON.stringify(r);
})JS";
enum class Op { Start, Move, Up, Down, Sync, Hide, Unhide, Clear };
inline const char* opName(Op op)
{
    switch (op) {
    case Op::Start: return "start";
    case Op::Move: return "move";
    case Op::Up: return "up";
    case Op::Down: return "down";
    case Op::Sync: return "sync";
    case Op::Hide: return "hide";
    case Op::Unhide: return "unhide";
    case Op::Clear: return "clear";
    }
    return "clear";
}
inline std::string number(double v)
{
    if (!(v == v) || v < -100000 || v > 100000) v = 0;   // NaN / absurd: the page's top-left corner
    char b[32];
    snprintf(b, sizeof b, "%.1f", v);
    return b;
}
// The whole script: the core is used as written (never cut), then called with its arguments.
inline std::string script(Op op, double x = 0, double y = 0, const std::string& selector = std::string())
{
    return std::string("(") + kCore + ")(" + jsString(opName(op)) + "," + number(x) + "," + number(y) + "," + jsString(selector) + ")";
}

// --- texts --------------------------------------------------------------------------------------------------------
inline std::string plural(int n, const char* one, const char* many) { return std::to_string(n) + " " + (n == 1 ? one : many); }
inline std::string shortSel(const std::string& s, size_t max = 64)
{
    return s.size() <= max ? s : s.substr(0, max - 3) + "...";
}
inline std::string barTitle(const std::string& label, int w, int h)
{
    return "Hide this element: " + (label.empty() ? std::string("element") : label) + "  (" + std::to_string(w) + " x " + std::to_string(h) + ")";
}
inline std::string barDetail(int n, bool privateTab)
{
    std::string s = n > 1 ? "Matches " + plural(n, "element", "elements") + " on this page" : n == 1 ? std::string("Only this element") : std::string("No rule for this element: D-pad up picks a bigger one");
    if (privateTab) s += ". Private tab: hidden on this page only, not saved";
    return s;
}
inline std::string askManyTitle(int n) { return "Hide " + std::to_string(n) + " elements?"; }
inline std::string askManyBody(const std::string& sel, int n, const std::string& host, bool privateTab)
{
    std::string s = "The rule \"" + shortSel(sel, 90) + "\" matches " + std::to_string(n) + " elements on this page";
    s += privateTab ? ". They are hidden on this page only." : ". They stay hidden on " + host + " from now on (Site settings > Hidden elements to show them again).";
    return s;
}
inline std::string hiddenNotice(const std::string& host, bool privateTab, Added a)
{
    if (privateTab) return "Hidden on this page only (private tab). Undo: hold Cross > Undo hide element";
    switch (a) {
    case Added::Ok: return "Hidden on " + host + ". Undo: hold Cross > Undo hide element";
    case Added::Exists: return "Hidden (already in your rules for " + host + ")";
    case Added::HostFull: return "Hidden on this page only: " + host + " already has " + std::to_string(kMaxPerHost) + " hidden elements";
    case Added::FileFull: return "Hidden on this page only: the rules file is full";
    case Added::Invalid: break;
    }
    return "Hidden on this page only (no rule could be saved for it)";
}
inline std::string rowValue(size_t n) { return n ? std::to_string(n) : std::string("None"); }

} // namespace OmniZapper
