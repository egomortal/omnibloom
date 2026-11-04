// OMNI_UBO_SITE_V1: per-site uBlock content (scriptlets, site CSS, procedural filters) chosen natively.
// SPDX-License-Identifier: GPL-3.0-or-later
//
// The uBlock content bundle (~5.4 MB of JavaScript) carries every scriptlet and cosmetic rule for
// every site and is compiled again in each frame (the console's JavaScriptCore has no JIT). This
// reader loads the same rules, re-indexed by outputs/ubo-site/make-ubo-site.py into
// /data/omni/ubo-site/site-index.txt, and builds for one frame host the two small scripts that host
// needs: page world (scriptlets) and isolated world (isolated scriptlets, site CSS, procedural
// filters only when used, generic-cosmetic exceptions). Hosts without rules get no script.
//
// Matching mirrors uBO Lite's content scripts: the frame host and each parent domain, then the
// "name.*" entities, then the hostname regular expressions; scriptlets also look at ancestor
// frames ("host>>" keys), which are kept behind a run-time check of location.ancestorOrigins.
// Exceptions (#@#) cancel within the same ruleset for scriptlets and across rulesets for CSS, as
// upstream. Plain C++ (no WebKit, no exceptions): also built by outputs/ubo-site/site-harness.cpp.
#pragma once
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <string_view>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace OmniUBlockSite {

using RegexTest = bool (*)(void* context, size_t rule, const std::string& text);

struct Scripts {
    std::string main;      // page world, document start ("" = nothing for this host)
    std::string isolated;  // isolated world, document start ("" = nothing)
    size_t scriptletCalls = 0, cssSelectors = 0, proceduralSelectors = 0, genericExceptions = 0;
    bool procedural = false, genericOff = false;
};

class Index {
public:
    bool load(const char* path, std::string& error)
    {
        *this = Index();
        FILE* file = fopen(path, "rb");
        if (!file) { error = "missing"; return false; }
        char chunk[65536]; size_t count;
        while ((count = fread(chunk, 1, sizeof(chunk), file)) && m_data.size() <= 32u * 1024 * 1024) m_data.append(chunk, count);
        const bool readError = ferror(file);
        fclose(file);
        if (readError || m_data.size() > 32u * 1024 * 1024) { error = "unreadable or too large"; m_data.clear(); return false; }
        m_pos = 0;
        if (line() != "OMNI-UBO-SITE 1") return fail(error, "bad header");
        for (;;) {
            std::string_view header = line();
            if (header == "@end") break;
            if (header.empty() && m_pos >= m_data.size()) return fail(error, "truncated");
            std::string_view name; size_t n = 0; char world = 0;
            if (!section(header, name, world, n)) return fail(error, "bad section header");
            if (name == "@rulesets") { for (size_t i = 0; i < n; ++i) m_rulesets.push_back(line()); }
            else if (name == "@calls") {
                for (size_t i = 0; i < n; ++i) {
                    std::string_view f[4]; if (!fields(line(), f, 4)) return fail(error, "bad call");
                    Call call; call.world = f[0].empty() ? 0 : f[0][0]; call.ruleset = number(f[1]);
                    call.all = f[2] == "-"; call.fn = f[2]; call.args = f[3];
                    m_calls.push_back(call);
                }
            } else if (name == "@decls") {
                auto& w = worldOf(world);
                for (size_t i = 0; i < n; ++i) {
                    std::string_view f[2]; if (!fields(line(), f, 2)) return fail(error, "bad decl");
                    std::string_view body = blob(number(f[1])); if (body.data() == nullptr) return fail(error, "bad decl body");
                    w.byName.emplace(std::string(f[0]), w.decls.size());
                    w.decls.push_back(body);
                }
            } else if (name == "@closure") {
                auto& w = worldOf(world);
                w.closure.assign(w.decls.size(), { });
                for (size_t i = 0; i < n; ++i) {
                    std::string_view f[2]; if (!fields(line(), f, 2)) return fail(error, "bad closure");
                    auto it = w.byName.find(std::string(f[0])); if (it == w.byName.end()) return fail(error, "closure of unknown decl");
                    forEachToken(f[1], [&](std::string_view t) { w.closure[it->second].push_back(static_cast<unsigned>(number(t))); });
                }
            } else if (name == "@selectors") { for (size_t i = 0; i < n; ++i) m_selectors.push_back(line()); }
            else if (name == "@regex") {
                for (size_t i = 0; i < n; ++i) {
                    std::string_view f[4]; if (!fields(line(), f, 4)) return fail(error, "bad regex");
                    m_regex.push_back({ f[0].empty() ? char(0) : f[0][0], f[1], std::string(f[2]), f[3] });
                }
            } else if (name == "@templates") {
                for (size_t i = 0; i < n; ++i) {
                    std::string_view f[2]; if (!fields(line(), f, 2)) return fail(error, "bad template");
                    std::string_view body = blob(number(f[1])); if (body.data() == nullptr) return fail(error, "bad template body");
                    m_templates.emplace(std::string(f[0]), body);
                }
            } else if (name == "@keys") {
                m_keys.reserve(n);
                for (size_t i = 0; i < n; ++i) m_keys.push_back(line());
            } else return fail(error, "unknown section");
        }
        for (const char* t : { "main-head", "iso-head", "anc", "procedural", "css-apply", "tail" })
            if (!m_templates.count(t)) return fail(error, "template missing");
        if (m_keys.empty() || m_calls.empty() || m_worlds[0].decls.empty() || m_worlds[1].decls.empty()) return fail(error, "empty tables");
        for (size_t i = 1; i < m_keys.size(); ++i)
            if (!(keyOf(m_keys[i - 1]) < keyOf(m_keys[i]))) return fail(error, "keys not sorted");
        for (auto& call : m_calls) {
            if (call.world != 'm' && call.world != 'i') return fail(error, "call world");
            if (!call.all && !worldOf(call.world).byName.count(std::string(call.fn))) return fail(error, "call of unknown function");
        }
        m_loaded = true;
        return true;
    }
    bool loaded() const { return m_loaded; }
    size_t keyCount() const { return m_keys.size(); }
    size_t bytes() const { return m_data.size(); }
    size_t regexCount() const { return m_regex.size(); }
    const std::string& regexSource(size_t i) const { return m_regex[i].source; }

    // host: the frame's host name (lower case). tops: host names of pages the frame was seen in
    // (for ancestor rules; checked again in the page). allowJSON: trusted-site list as a JSON array.
    Scripts build(const std::string& host, const std::vector<std::string>& tops, const std::string& allowJSON, RegexTest regexTest, void* regexContext) const
    {
        Scripts out;
        if (!m_loaded || host.empty()) return out;
        Collect c(m_calls.size());
        const std::vector<std::string> hns = hostsOf(host);
        std::vector<std::string> keys = hns;
        for (auto& e : entitiesOf(hns)) keys.push_back(e);
        for (auto& key : keys) lookup(key, nullptr, c);
        for (auto& top : tops) {
            if (top.empty()) continue;
            std::vector<std::string> ancestor = hostsOf(top);
            for (auto& e : entitiesOf(hostsOf(top))) ancestor.push_back(e);
            for (auto& a : ancestor) lookup(a + ">>", &a, c);
        }
        for (size_t i = 0; i < m_regex.size(); ++i) {
            auto& rule = m_regex[i];
            bool hit = false;
            if (rule.kind == 's') {
                for (auto& hn : hns) if (hn.find(rule.needle) != std::string::npos && regexTest && regexTest(regexContext, i, hn)) { hit = true; break; }
            } else if (host.find(rule.needle) != std::string::npos && regexTest && regexTest(regexContext, i, host)) hit = true;
            if (hit) apply(rule.tokens, nullptr, c);
        }
        const std::string allow = allowJSON.empty() ? std::string("[]") : allowJSON;
        out.main = scriptletScript('m', c, allow, out.scriptletCalls, nullptr);
        std::string isolatedBody;
        size_t isolatedCalls = 0;
        scriptletScript('i', c, allow, isolatedCalls, &isolatedBody);
        out.scriptletCalls += isolatedCalls;
        // Site CSS: positive selectors minus exceptions (exceptions apply across rulesets).
        std::string plain, procedural;
        for (unsigned s : c.css) {
            if (c.cssExceptions.count(s)) continue;
            std::string_view sel = m_selectors[s];
            if (!sel.empty() && sel[0] == '{') { if (!procedural.empty()) procedural += ','; procedural.append(sel); ++out.proceduralSelectors; }
            else { if (!plain.empty()) plain += ','; jsString(plain, sel); ++out.cssSelectors; }
        }
        std::string generic;
        if (!c.genericExceptions.empty()) {
            generic = "self.omniGenericExc = [";
            bool first = true;
            for (unsigned s : c.genericExceptions) { if (!first) generic += ','; first = false; jsString(generic, m_selectors[s]); ++out.genericExceptions; }
            generic += "];\n";
        }
        out.genericOff = c.unhide && !c.hideOverride;
        if (out.genericOff) generic += "self.omniGenericOff = true;\n";
        if (!isolatedBody.empty() || out.cssSelectors || out.proceduralSelectors || !generic.empty()) {
            std::string& s = out.isolated;
            s.append(templ("iso-head"));
            replaceAllow(s, allow);
            s += generic;
            s += isolatedBody;
            if (out.cssSelectors || out.proceduralSelectors) {
                out.procedural = out.proceduralSelectors != 0;
                if (out.procedural) s.append(templ("procedural"));
                s.append(templ("css-apply"));
                s += "omniSpecific([" + plain + "], [" + procedural + "]);\n";
            }
            s.append(templ("tail"));
        }
        return out;
    }

private:
    struct Call { char world = 0; size_t ruleset = 0; bool all = false; std::string_view fn, args; };
    struct World { std::vector<std::string_view> decls; std::vector<std::vector<unsigned>> closure; std::unordered_map<std::string, size_t> byName; };
    struct Regex { char kind; std::string_view needle; std::string source; std::string_view tokens; };
    struct Slot { unsigned gid; bool own; std::vector<std::string> ancestors; };
    struct Collect {
        explicit Collect(size_t calls) : slotOf(calls, -1) { }
        std::vector<Slot> slots; std::vector<int> slotOf;
        std::unordered_set<unsigned> excepted;
        std::vector<unsigned> css; std::unordered_set<unsigned> cssSeen, cssExceptions;
        std::vector<unsigned> genericExceptions; std::unordered_set<unsigned> genericSeen;
        bool unhide = false, hideOverride = false;
    };

    static std::string_view keyOf(std::string_view line) { auto tab = line.find('\t'); return tab == std::string_view::npos ? line : line.substr(0, tab); }
    static size_t number(std::string_view s) { size_t v = 0; for (char ch : s) { if (ch < '0' || ch > '9') break; v = v * 10 + static_cast<size_t>(ch - '0'); } return v; }
    template<typename F> static void forEachToken(std::string_view s, F&& f)
    {
        size_t start = 0;
        while (start < s.size()) {
            size_t end = s.find(' ', start);
            if (end == std::string_view::npos) end = s.size();
            if (end > start) f(s.substr(start, end - start));
            start = end + 1;
        }
    }
    bool fail(std::string& error, const char* what) { error = what; m_loaded = false; return false; }
    std::string_view line()
    {
        if (m_pos >= m_data.size()) return { };
        size_t end = m_data.find('\n', m_pos);
        if (end == std::string::npos) end = m_data.size();
        std::string_view result(m_data.data() + m_pos, end - m_pos);
        m_pos = end + 1;
        return result;
    }
    std::string_view blob(size_t length)
    {
        if (m_pos + length + 1 > m_data.size() || m_data[m_pos + length] != '\n') return { };
        std::string_view result(m_data.data() + m_pos, length);
        m_pos += length + 1;
        return result;
    }
    static bool fields(std::string_view s, std::string_view* out, int count)
    {
        for (int i = 0; i < count; ++i) {
            const bool last = i + 1 == count;
            size_t tab = last ? std::string_view::npos : s.find('\t');
            if (!last && tab == std::string_view::npos) return false;
            out[i] = s.substr(0, tab);
            s = last ? std::string_view() : s.substr(tab + 1);
        }
        return true;
    }
    static bool section(std::string_view header, std::string_view& name, char& world, size_t& count)
    {
        if (header.empty() || header[0] != '@') return false;
        size_t space = header.find(' ');
        if (space == std::string_view::npos) return false;
        name = header.substr(0, space);
        std::string_view rest = header.substr(space + 1);
        world = 0;
        if (rest.size() > 2 && rest[1] == ' ') { world = rest[0]; rest = rest.substr(2); }
        if (rest.empty()) return false;
        count = number(rest);
        return true;
    }
    World& worldOf(char w) { return m_worlds[w == 'i' ? 1 : 0]; }
    const World& worldOf(char w) const { return m_worlds[w == 'i' ? 1 : 0]; }
    std::string_view templ(const char* name) const { auto it = m_templates.find(name); return it == m_templates.end() ? std::string_view() : it->second; }

    static std::vector<std::string> hostsOf(const std::string& host)
    {
        std::vector<std::string> out { host };
        for (size_t p = host.find('.'); p != std::string::npos; p = host.find('.', p + 1)) out.push_back(host.substr(p + 1));
        return out;
    }
    // uBO "name.*" entities: every left part of every parent domain, sorted like uBOL (longest
    // first, then reverse alphabetical); the order only decides the order scriptlets run in.
    static std::vector<std::string> entitiesOf(const std::vector<std::string>& hns)
    {
        std::vector<std::string> out;
        for (auto hn : hns) {
            for (;;) {
                size_t p = hn.rfind('.');
                if (p == std::string::npos) break;
                hn.resize(p);
                out.push_back(hn + ".*");
            }
        }
        std::sort(out.begin(), out.end(), [](const std::string& a, const std::string& b) { return a.size() != b.size() ? a.size() > b.size() : a > b; });
        return out;
    }
    void lookup(const std::string& key, const std::string* ancestor, Collect& c) const
    {
        auto it = std::lower_bound(m_keys.begin(), m_keys.end(), std::string_view(key), [](std::string_view line, std::string_view k) { return keyOf(line) < k; });
        if (it == m_keys.end() || keyOf(*it) != key) return;
        std::string_view tokens = it->size() > key.size() ? it->substr(key.size() + 1) : std::string_view();
        apply(tokens, ancestor, c);
    }
    void apply(std::string_view tokens, const std::string* ancestor, Collect& c) const
    {
        forEachToken(tokens, [&](std::string_view t) {
            const char kind = t[0];
            const unsigned id = static_cast<unsigned>(number(t.substr(1)));
            switch (kind) {
            case 's':
                if (id >= m_calls.size()) return;
                if (c.slotOf[id] < 0) { c.slotOf[id] = static_cast<int>(c.slots.size()); c.slots.push_back({ id, false, { } }); }
                if (ancestor) { auto& a = c.slots[c.slotOf[id]].ancestors; if (std::find(a.begin(), a.end(), *ancestor) == a.end()) a.push_back(*ancestor); }
                else c.slots[c.slotOf[id]].own = true;
                return;
            case 'x': if (!ancestor) c.excepted.insert(id); return; // upstream lists have no ancestor exceptions
            case 'c': if (id < m_selectors.size() && c.cssSeen.insert(id).second) c.css.push_back(id); return;
            case 'd': c.cssExceptions.insert(id); return;
            case 'e': if (id < m_selectors.size() && c.genericSeen.insert(id).second) c.genericExceptions.push_back(id); return;
            case 'U': if (!ancestor) c.unhide = true; return;
            case 'V': if (!ancestor) c.hideOverride = true; return;
            default: return;
            }
        });
    }
    static void jsString(std::string& out, std::string_view s)
    {
        out += '"';
        for (unsigned char ch : s) {
            switch (ch) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if (ch < 0x20) { char b[8]; snprintf(b, sizeof(b), "\\u%04x", ch); out += b; }
                else out += static_cast<char>(ch);
            }
        }
        out += '"';
    }
    static void replaceAllow(std::string& s, const std::string& allow)
    {
        static const std::string marker = "/*OMNI_ALLOWLIST*/[]";
        auto p = s.find(marker);
        if (p != std::string::npos) s.replace(p, marker.size(), allow);
    }
    // Scriptlets of one world, grouped by ruleset in bundle order. Page world: a whole script;
    // isolated world: the body only (the isolated script also carries CSS).
    std::string scriptletScript(char world, const Collect& c, const std::string& allow, size_t& callCount, std::string* bodyOnly) const
    {
        callCount = 0;
        const World& w = worldOf(world);
        std::vector<bool> allOff(m_rulesets.size() + 1, false);
        for (auto& slot : c.slots) {
            auto& call = m_calls[slot.gid];
            if (call.world == world && call.all && slot.own && call.ruleset < allOff.size()) allOff[call.ruleset] = true;
        }
        std::vector<const Slot*> chosen;
        for (size_t rs = 0; rs < m_rulesets.size(); ++rs) {
            if (allOff[rs]) continue;
            for (auto& slot : c.slots) {
                auto& call = m_calls[slot.gid];
                if (call.world != world || call.ruleset != rs || call.all || c.excepted.count(slot.gid)) continue;
                chosen.push_back(&slot);
            }
        }
        if (chosen.empty()) return { };
        std::vector<bool> need(w.decls.size(), false);
        bool guarded = false;
        for (auto* slot : chosen) {
            auto it = w.byName.find(std::string(m_calls[slot->gid].fn));
            if (it == w.byName.end()) continue;
            for (unsigned d : w.closure[it->second]) if (d < need.size()) need[d] = true;
            if (!slot->own) guarded = true;
        }
        std::string s;
        if (!bodyOnly) { s.append(templ("main-head")); replaceAllow(s, allow); }
        else s += "const scriptletGlobals = {};\n";
        if (guarded) s.append(templ("anc"));
        for (size_t d = 0; d < need.size(); ++d) if (need[d]) s.append(w.decls[d]);
        for (auto* slot : chosen) {
            auto& call = m_calls[slot->gid];
            if (!slot->own) {
                s += "if (omniAnc([";
                for (size_t i = 0; i < slot->ancestors.size(); ++i) { if (i) s += ','; jsString(s, slot->ancestors[i]); }
                s += "])) ";
            }
            s += "try { "; s.append(call.fn); s += '('; s.append(call.args); s += "); } catch { }\n";
            ++callCount;
        }
        if (bodyOnly) { *bodyOnly = std::move(s); return { }; }
        s.append(templ("tail"));
        return s;
    }

    std::string m_data;
    size_t m_pos = 0;
    bool m_loaded = false;
    std::vector<std::string_view> m_rulesets;
    std::vector<Call> m_calls;
    World m_worlds[2];
    std::vector<std::string_view> m_selectors;
    std::vector<Regex> m_regex;
    std::unordered_map<std::string, std::string_view> m_templates;
    std::vector<std::string_view> m_keys;
};

} // namespace OmniUBlockSite
