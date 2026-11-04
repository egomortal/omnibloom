// Isolated upstream uBlock network engine. No DOM, filesystem or network APIs
// are exposed to its JavaScript context. SPDX-License-Identifier: GPL-3.0-or-later
#include "config.h"
#include <JavaScriptCore/JavaScript.h>
#include <JavaScriptCore/JSTypedArray.h>
#include <wtf/text/WTFString.h>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <string>
#include <unordered_set>
#include <vector>
#include <sys/stat.h>
#include <unistd.h>

namespace {
// One isolated JavaScriptCore context per rule set. The network process uses
// the full set; the browser shell loads only `$popup` filters for its popup check.
struct Engine {
    const char* compiledName;
    const char* testCompiledName;
    bool reportsStatus;
    JSGlobalContextRef context = nullptr;
    JSObjectRef matcher = nullptr;
    JSObjectRef rewriter = nullptr;
    bool attempted = false;
    bool failed = false;
};
Engine network { "ublock-compiled.txt", "ublock-test-compiled.txt", true };
bool filterFailure() {
    network.failed = true;
    unlink("/data/omni/ublock-ready.flag");
    if (FILE* file = fopen("/data/omni/ublock-error.flag", "w")) { fputs("1\n", file); fclose(file); }
    return true; // Do not silently allow requests while filtering is enabled.
}
bool filteringOff() {
    return access("/data/omni/ublock-native.flag", F_OK) || !access("/data/omni/ublock-disabled.flag", F_OK);
}
std::string readAsset(const char* name) {
    std::string result;
    std::string path = std::string("/data/omni/") + name;
    FILE* file = fopen(path.c_str(), "rb");
    if (!file) return result;
    char chunk[4096]; size_t count;
    while ((count = fread(chunk, 1, sizeof(chunk), file)) && result.size() <= 8 * 1024 * 1024) result.append(chunk, count);
    if (ferror(file) || result.size() > 8 * 1024 * 1024) result.clear();
    fclose(file); return result;
}
JSValueRef stringValue(JSContextRef ctx, const char* value) {
    auto string = JSStringCreateWithUTF8CString(value);
    auto result = JSValueMakeString(ctx, string);
    JSStringRelease(string); return result;
}
void report(JSContextRef ctx, JSValueRef exception) {
    auto text = JSValueToStringCopy(ctx, exception, nullptr);
    if (!text) return;
    char message[512]; JSStringGetUTF8CString(text, message, sizeof(message)); JSStringRelease(text);
    fprintf(stderr, "ublock engine error: %s\n", message);
}
JSValueRef evaluate(JSGlobalContextRef ctx, const char* source) {
    auto script = JSStringCreateWithUTF8CString(source);
    JSValueRef exception = nullptr;
    auto result = JSEvaluateScript(ctx, script, nullptr, nullptr, 1, &exception);
    JSStringRelease(script);
    if (exception) { report(ctx, exception); return nullptr; }
    return result;
}
JSValueRef decode(JSContextRef ctx, JSObjectRef, JSObjectRef, size_t count, const JSValueRef args[], JSValueRef* exception) {
    if (!count || !JSValueIsObject(ctx, args[0])) return stringValue(ctx, "");
    auto object = JSValueToObject(ctx, args[0], exception);
    auto length = JSObjectGetTypedArrayByteLength(ctx, object, exception);
    if (*exception) return JSValueMakeUndefined(ctx);
    auto offset = JSObjectGetTypedArrayByteOffset(ctx, object, exception);
    if (*exception) return JSValueMakeUndefined(ctx);
    auto* bytes = static_cast<const uint8_t*>(JSObjectGetTypedArrayBytesPtr(ctx, object, exception));
    if (*exception || !bytes) return JSValueMakeUndefined(ctx);
    auto value = WTF::String::fromUTF8ReplacingInvalidSequences(std::span<const uint8_t>(bytes + offset, length));
    std::u16string characters; characters.reserve(value.length());
    for (unsigned i = 0; i < value.length(); ++i) characters.push_back(value[i]);
    auto text = JSStringCreateWithCharacters(reinterpret_cast<const JSChar*>(characters.data()), characters.size());
    auto result = JSValueMakeString(ctx, text); JSStringRelease(text); return result;
}
bool initialize(Engine& engine) {
    if (engine.attempted) return engine.matcher;
    engine.attempted = true;
    auto bundle = readAsset("ublock-engine.js");
    bool testRules = engine.testCompiledName && !access("/data/omni/ublock-test.flag", F_OK);
    auto compiled = readAsset(testRules ? engine.testCompiledName : engine.compiledName);
    auto suffixes = readAsset("public-suffix-list.dat");
    if (bundle.empty() || compiled.empty() || suffixes.empty()) { fprintf(stderr,"ublock engine: missing assets (%s)\n", engine.compiledName); return false; }
    auto ctx = JSGlobalContextCreate(nullptr);
    engine.context = ctx;
    auto name = JSStringCreateWithUTF8CString("omniDecodeUTF8");
    auto function = JSObjectMakeFunctionWithCallback(ctx, name, decode);
    JSObjectSetProperty(ctx, JSContextGetGlobalObject(ctx), name, function, kJSPropertyAttributeReadOnly, nullptr);
    JSStringRelease(name);
    // Optimization jobs are queued by upstream freeze(), then explicitly run
    // synchronously by initialize(). No page-controlled timer callbacks exist.
    if (!evaluate(ctx, "class TextDecoder { decode(bytes) { return omniDecodeUTF8(bytes); } } let omniTimerId=0; function setTimeout(){return ++omniTimerId;} function clearTimeout(){}")) return false;
    if (!evaluate(ctx, bundle.c_str())) return false;
    auto initializer = evaluate(ctx, "OmniUBlock.initialize");
    if (!initializer || !JSValueIsObject(ctx, initializer)) return false;
    JSValueRef arguments[] = { stringValue(ctx, compiled.c_str()), stringValue(ctx, suffixes.c_str()) };
    JSValueRef exception = nullptr;
    JSObjectCallAsFunction(ctx, JSValueToObject(ctx, initializer, nullptr), nullptr, 2, arguments, &exception);
    if (exception) { report(ctx, exception); return false; }
    auto match = evaluate(ctx, "OmniUBlock.match");
    if (!match || !JSValueIsObject(ctx, match)) return false;
    // Older bundles have no rewrite(); link skipping/cleaning is then simply off.
    auto rewrite = evaluate(ctx, "typeof OmniUBlock.rewrite === 'function' ? OmniUBlock.rewrite : null");
    if (rewrite && JSValueIsObject(ctx, rewrite)) { engine.rewriter = JSValueToObject(ctx, rewrite, nullptr); JSValueProtect(ctx, engine.rewriter); }
    engine.matcher = JSValueToObject(ctx, match, nullptr); JSValueProtect(ctx, engine.matcher);
    fprintf(stderr,"ublock engine: upstream static network engine ready (%s%s)\n", engine.compiledName, engine.rewriter ? ", link rewriting" : "");
    if (engine.reportsStatus)
        if (FILE* ready = fopen("/data/omni/ublock-ready.flag", "w")) { fputs("1\n", ready); fclose(ready); }
    return true;
}
}

extern "C" bool omniUBlockShouldBlock(const char* url, const char* origin, const char* type) {
    if (filteringOff()) return false;
    if (network.failed) return true;
    if (!initialize(network)) return filterFailure();
    auto ctx = network.context;
    JSValueRef arguments[] = { stringValue(ctx, url), stringValue(ctx, origin), stringValue(ctx, type) };
    JSValueRef exception = nullptr;
    auto result = JSObjectCallAsFunction(ctx, network.matcher, nullptr, 3, arguments, &exception);
    if (exception) { report(ctx, exception); return filterFailure(); }
    if (!result || !JSValueIsNumber(ctx, result)) return filterFailure();
    double decision = JSValueToNumber(ctx, result, nullptr);
    if (decision != 0 && decision != 1 && decision != 2) return filterFailure();
    return decision == 1;
}

// uBlock's request rewriting (urlskip / removeparam / uritransform) for a
// top-level navigation. Writes the new URL to `out`; false when unchanged.
// Optional: any failure here leaves the request as it was.
extern "C" bool omniUBlockRewrite(const char* url, const char* origin, const char* type, bool blocked, char* out, size_t size) {
    if (!out || size < 16) return false;
    out[0] = 0;
    if (filteringOff() || network.failed || !initialize(network) || !network.rewriter) return false;
    auto ctx = network.context;
    JSValueRef arguments[] = { stringValue(ctx, url), stringValue(ctx, origin), stringValue(ctx, type), JSValueMakeBoolean(ctx, blocked) };
    JSValueRef exception = nullptr;
    auto result = JSObjectCallAsFunction(ctx, network.rewriter, nullptr, 4, arguments, &exception);
    if (exception) { report(ctx, exception); return false; }
    if (!result || !JSValueIsString(ctx, result)) return false;
    auto text = JSValueToStringCopy(ctx, result, nullptr);
    if (!text) return false;
    bool fits = JSStringGetMaximumUTF8CStringSize(text) <= size;
    if (fits) JSStringGetUTF8CString(text, out, size);
    JSStringRelease(text);
    if (!fits) { out[0] = 0; return false; }
    return out[0] && strcmp(out, url);
}

// `$popup` filters for a window a page is opening, used by the browser shell in
// the main app process. Native code over a small rule file
// (ublock-popup-rules.txt, generated by compile-lists.cjs); only the handful of
// regular-expression rules use JavaScriptCore, in a tiny context created the
// first time one of them has to be evaluated. Supported uBlock syntax: `||host^`,
// URL patterns with `*`, `^`, `|`, `||`, `/regex/`, `@@` exceptions and the
// options third-party/3p, first-party/1p, strict3p, important, match-case,
// domain=/from= (opener) and to= (popup), with `~` negation and `name.*`.
namespace {
struct DomainEntry { std::string name; bool negated; bool entity; };
struct PopupRule {
    char kind; // 'H' host, 'P' pattern, 'R' regular expression
    std::string pattern;
    bool exception = false, thirdParty = false, firstParty = false, strictThirdParty = false, important = false, matchCase = false;
    std::vector<DomainEntry> openers, targets;
    std::vector<std::string> required; // text every match of a regular expression contains
    int regex = -1;
};
std::vector<PopupRule> popupRules;
bool popupRulesLoaded = false;
size_t popupRegexRules = 0;
struct RegexEngine {
    bool attempted = false;
    JSGlobalContextRef context = nullptr;
    JSObjectRef tester = nullptr;
    std::vector<JSObjectRef> expressions;
} popupRegex;

std::vector<DomainEntry> parseDomains(const std::string& list) {
    std::vector<DomainEntry> result;
    if (list == "-") return result;
    size_t start = 0;
    while (start <= list.size()) {
        auto end = list.find('|', start);
        if (end == std::string::npos) end = list.size();
        std::string name = list.substr(start, end - start);
        bool negated = !name.empty() && name[0] == '~';
        if (negated) name.erase(0, 1);
        for (auto& c : name) if (c >= 'A' && c <= 'Z') c = c - 'A' + 'a';
        bool entity = name.size() > 2 && name.compare(name.size() - 2, 2, ".*") == 0;
        if (entity) name.resize(name.size() - 2);
        if (!name.empty()) result.push_back({ name, negated, entity });
        start = end + 1;
    }
    return result;
}
void addPopupRule(PopupRule&& rule) {
    if (rule.kind != 'R') for (auto& c : rule.pattern) if (!rule.matchCase && c >= 'A' && c <= 'Z') c = c - 'A' + 'a';
    if (rule.kind == 'R') ++popupRegexRules;
    popupRules.push_back(std::move(rule));
}
void loadPopupRules() {
    popupRulesLoaded = true;
    FILE* file = fopen("/data/omni/ublock-popup-rules.txt", "r");
    if (!file) { fprintf(stderr, "ublock popup rules: missing\n"); return; }
    char line[4096];
    while (fgets(line, sizeof(line), file)) {
        std::string text(line);
        if (text.empty() || (text.back() != '\n' && !feof(file))) { int ch; while ((ch = fgetc(file)) != EOF && ch != '\n') { } continue; }
        while (!text.empty() && (text.back() == '\n' || text.back() == '\r')) text.pop_back();
        if (text.empty() || text[0] == '#') continue;
        if (text.find('\t') != std::string::npos) {
            // v2: kind, flags, pattern, opener domains, popup domains[, required text].
            std::string field[6]; size_t start = 0; int count = 0;
            while (count < 6 && start <= text.size()) {
                auto end = text.find('\t', start);
                if (end == std::string::npos) end = text.size();
                field[count++] = text.substr(start, end - start); start = end + 1;
            }
            if (count < 5 || start <= text.size() || field[0].size() != 1 || field[2].empty()) continue;
            PopupRule rule;
            rule.kind = field[0][0];
            if (rule.kind != 'H' && rule.kind != 'P' && rule.kind != 'R') continue;
            for (char flag : field[1]) switch (flag) {
            case 'x': rule.exception = true; break;
            case 't': rule.thirdParty = true; break;
            case 'f': rule.firstParty = true; break;
            case 's': rule.strictThirdParty = true; break;
            case 'i': rule.important = true; break;
            case 'c': rule.matchCase = true; break;
            default: break;
            }
            rule.pattern = field[2];
            rule.openers = parseDomains(field[3]);
            rule.targets = parseDomains(field[4]);
            if (rule.kind == 'R' && count == 6 && field[5] != "-") {
                size_t from = 0;
                while (from < field[5].size()) {
                    auto space = field[5].find(' ', from);
                    if (space == std::string::npos) space = field[5].size();
                    if (space > from) rule.required.push_back(field[5].substr(from, space - from));
                    from = space + 1;
                }
            }
            addPopupRule(std::move(rule));
            continue;
        }
        // v1: "<kind> <pattern>" (H/HT/X/XT hosts, P/PT/XP/XPT patterns).
        auto space = text.find(' ');
        if (space == std::string::npos || space + 1 >= text.size()) continue;
        std::string kind = text.substr(0, space);
        if (kind != "H" && kind != "HT" && kind != "X" && kind != "XT" && kind != "P" && kind != "PT" && kind != "XP" && kind != "XPT") continue;
        PopupRule rule;
        rule.kind = (kind == "H" || kind == "HT" || kind == "X" || kind == "XT") ? 'H' : 'P';
        rule.exception = kind[0] == 'X';
        rule.thirdParty = kind.back() == 'T';
        rule.pattern = text.substr(space + 1);
        addPopupRule(std::move(rule));
    }
    fclose(file);
    fprintf(stderr, "ublock popup rules: %zu loaded (%zu regular expressions)\n", popupRules.size(), popupRegexRules);
}
void initializePopupRegex() {
    popupRegex.attempted = true;
    if (!popupRegexRules) return;
    auto context = JSGlobalContextCreate(nullptr);
    if (!context) return;
    auto compiler = evaluate(context, "(function (source, flags) { try { return new RegExp(source, flags); } catch (e) { return null; } })");
    auto tester = evaluate(context, "(function (expression, text) { return expression.test(text); })");
    if (!compiler || !tester || !JSValueIsObject(context, compiler) || !JSValueIsObject(context, tester)) { JSGlobalContextRelease(context); return; }
    auto compile = JSValueToObject(context, compiler, nullptr);
    popupRegex.context = context;
    popupRegex.tester = JSValueToObject(context, tester, nullptr);
    JSValueProtect(context, popupRegex.tester);
    size_t rejected = 0;
    for (auto& rule : popupRules) {
        if (rule.kind != 'R') continue;
        JSValueRef args[] = { stringValue(context, rule.pattern.c_str()), stringValue(context, rule.matchCase ? "" : "i") };
        JSValueRef exception = nullptr;
        auto value = JSObjectCallAsFunction(context, compile, nullptr, 2, args, &exception);
        if (exception || !value || !JSValueIsObject(context, value)) { ++rejected; continue; }
        JSValueProtect(context, value);
        rule.regex = static_cast<int>(popupRegex.expressions.size());
        popupRegex.expressions.push_back(JSValueToObject(context, value, nullptr));
    }
    fprintf(stderr, "ublock popup rules: %zu regular expressions ready, %zu rejected\n", popupRegex.expressions.size(), rejected);
}
bool regexMatches(int index, const std::string& url) {
    if (!popupRegex.context || index < 0 || index >= static_cast<int>(popupRegex.expressions.size())) return false;
    auto context = popupRegex.context;
    JSValueRef args[] = { popupRegex.expressions[index], stringValue(context, url.c_str()) };
    JSValueRef exception = nullptr;
    auto result = JSObjectCallAsFunction(context, popupRegex.tester, nullptr, 2, args, &exception);
    return !exception && result && JSValueToBoolean(context, result);
}
std::string lowerHost(const std::string& url) {
    auto scheme = url.find("://");
    if (scheme == std::string::npos) return { };
    auto begin = scheme + 3, end = url.find_first_of("/?#", begin);
    std::string host = url.substr(begin, end == std::string::npos ? std::string::npos : end - begin);
    if (auto at = host.rfind('@'); at != std::string::npos) host = host.substr(at + 1);
    if (auto colon = host.find(':'); colon != std::string::npos && host[0] != '[') host.resize(colon);
    for (auto& c : host) if (c >= 'A' && c <= 'Z') c = c - 'A' + 'a';
    while (!host.empty() && host.back() == '.') host.pop_back();
    return host;
}
bool hostCovers(const std::string& host, const std::string& entry) {
    return host == entry || (host.size() > entry.size() && host.compare(host.size() - entry.size(), entry.size(), entry) == 0 && host[host.size() - entry.size() - 1] == '.');
}
// Registrable domains from the public suffix list the network engine also
// uses (/data/omni/public-suffix-list.dat), as uBlock does for third-party and
// `name.*` checks. Without the file: last two labels, or three after a short
// second-level label (co.uk).
struct SuffixList { bool loaded = false; std::unordered_set<std::string> rules, wildcards, exceptions; } suffixList;
void loadSuffixList() {
    suffixList.loaded = true;
    FILE* file = fopen("/data/omni/public-suffix-list.dat", "r");
    if (!file) return;
    char line[512];
    while (fgets(line, sizeof(line), file)) {
        std::string rule(line);
        if (rule.back() != '\n' && !feof(file)) { int ch; while ((ch = fgetc(file)) != EOF && ch != '\n') { } continue; }
        auto end = rule.find_first_of(" \t\r\n");
        if (end != std::string::npos) rule.resize(end);
        if (rule.empty() || rule.rfind("//", 0) == 0) continue;
        bool ascii = true;
        for (auto& c : rule) { if (static_cast<unsigned char>(c) >= 0x80) ascii = false; else if (c >= 'A' && c <= 'Z') c = c - 'A' + 'a'; }
        if (!ascii) continue;
        if (rule[0] == '!') suffixList.exceptions.insert(rule.substr(1));
        else if (rule.rfind("*.", 0) == 0) suffixList.wildcards.insert(rule.substr(2));
        else suffixList.rules.insert(rule);
    }
    fclose(file);
}
bool isAddress(const std::string& host) {
    if (host.empty() || host[0] == '[') return !host.empty();
    for (char c : host) if (!((c >= '0' && c <= '9') || c == '.')) return false;
    return true;
}
std::string publicSuffixOf(const std::string& host) {
    if (!suffixList.loaded) loadSuffixList();
    if (suffixList.rules.empty()) {
        auto last = host.rfind('.');
        if (last == std::string::npos) return host;
        auto second = host.rfind('.', last - 1);
        if (last && second != std::string::npos && last - second - 1 <= 3 && host.size() - last - 1 == 2) return host.substr(second + 1);
        return host.substr(last + 1);
    }
    for (size_t start = 0; start < host.size();) {
        std::string candidate = host.substr(start);
        auto dot = candidate.find('.');
        if (suffixList.exceptions.count(candidate)) return dot == std::string::npos ? candidate : candidate.substr(dot + 1);
        if (suffixList.rules.count(candidate)) return candidate;
        if (dot != std::string::npos && suffixList.wildcards.count(candidate.substr(dot + 1))) return candidate;
        auto next = host.find('.', start);
        if (next == std::string::npos) break;
        start = next + 1;
    }
    auto last = host.rfind('.');
    return last == std::string::npos ? host : host.substr(last + 1); // default rule "*"
}
std::string siteOf(const std::string& host) {
    if (host.empty() || isAddress(host)) return host;
    auto suffix = publicSuffixOf(host);
    if (suffix.size() >= host.size()) return host;
    auto label = host.rfind('.', host.size() - suffix.size() - 2);
    return label == std::string::npos ? host : host.substr(label + 1);
}
bool domainMatches(const std::string& host, const DomainEntry& entry) {
    if (host.empty()) return false;
    if (!entry.entity) return hostCovers(host, entry.name);
    // `name.*`: name followed by the host's public suffix.
    if (isAddress(host)) return false;
    return hostCovers(host, entry.name + "." + publicSuffixOf(host));
}
// uBlock domain lists: a matching `~` entry excludes; otherwise, when there are
// positive entries, one of them must match.
bool domainsAllow(const std::vector<DomainEntry>& list, const std::string& host) {
    if (list.empty()) return true;
    bool positive = false, matched = false;
    for (auto& entry : list) {
        if (entry.negated) { if (domainMatches(host, entry)) return false; continue; }
        positive = true;
        if (!matched && domainMatches(host, entry)) matched = true;
    }
    return !positive || matched;
}
bool isSeparator(char c) {
    return !((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_' || c == '-' || c == '.' || c == '%');
}
char lower(char c) { return c >= 'A' && c <= 'Z' ? c - 'A' + 'a' : c; }
// Wildcard match of p[pi..] against s[si..]; `*` any run, `^` separator or end.
bool globAt(const std::string& p, size_t pi, const std::string& s, size_t si, bool endAnchor, bool matchCase, int depth) {
    if (depth > 64) return false;
    while (pi < p.size()) {
        char c = p[pi];
        if (c == '*') {
            while (pi < p.size() && p[pi] == '*') ++pi;
            if (pi == p.size()) return true;
            for (size_t k = si; k <= s.size(); ++k) if (globAt(p, pi, s, k, endAnchor, matchCase, depth + 1)) return true;
            return false;
        }
        if (c == '^') {
            if (si == s.size()) { ++pi; continue; }
            if (!isSeparator(s[si])) return false;
            ++si; ++pi; continue;
        }
        if (c == '|' && pi + 1 == p.size()) { endAnchor = true; ++pi; continue; }
        if (si >= s.size() || (matchCase ? s[si] : lower(s[si])) != c) return false;
        ++si; ++pi;
    }
    return !endAnchor || si == s.size();
}
bool patternMatches(const std::string& pattern, const std::string& url, const std::string& host, bool matchCase) {
    if (pattern == "*") return true;
    if (pattern.rfind("||", 0) == 0) {
        auto scheme = url.find("://");
        if (scheme == std::string::npos || host.empty()) return false;
        size_t hostStart = scheme + 3, hostEnd = hostStart + host.size();
        if (auto at = url.find('@', hostStart); at != std::string::npos && at < url.find_first_of("/?#", hostStart)) hostStart = at + 1, hostEnd = hostStart + host.size();
        for (size_t i = hostStart; i <= hostEnd && i < url.size(); ++i)
            if ((i == hostStart || url[i - 1] == '.') && globAt(pattern, 2, url, i, false, matchCase, 0)) return true;
        return false;
    }
    if (pattern[0] == '|') return globAt(pattern, 1, url, 0, false, matchCase, 0);
    for (size_t i = 0; i < url.size(); ++i) if (globAt(pattern, 0, url, i, false, matchCase, 0)) return true;
    return false;
}
struct PopupContext { const std::string& url; const std::string& lowerUrl; const std::string& host; const std::string& openerHost; bool thirdParty; bool strictThirdParty; };
// Everything except the regular expression itself.
bool rulePrefilter(const PopupRule& rule, const PopupContext& context) {
    if (rule.thirdParty && !context.thirdParty) return false;
    if (rule.firstParty && context.thirdParty) return false;
    if (rule.strictThirdParty && !context.strictThirdParty) return false;
    for (auto& text : rule.required) if ((rule.matchCase ? context.url : context.lowerUrl).find(text) == std::string::npos) return false;
    return domainsAllow(rule.openers, context.openerHost) && domainsAllow(rule.targets, context.host);
}
bool ruleMatches(const PopupRule& rule, const PopupContext& context) {
    if (!rulePrefilter(rule, context)) return false;
    switch (rule.kind) {
    case 'H': return !context.host.empty() && hostCovers(context.host, rule.pattern);
    case 'P': return patternMatches(rule.pattern, context.url, context.host, rule.matchCase);
    default:
        if (context.url.size() > 4096) return false;
        if (!popupRegex.attempted) initializePopupRegex();
        return regexMatches(rule.regex, context.url);
    }
}
}

extern "C" bool omniUBlockPopupBlocked(const char* url, const char* opener) {
    if (!url || filteringOff()) return false;
    if (!popupRulesLoaded) loadPopupRules();
    std::string target(url);
    if (target.empty() || target.size() > 8192) return false;
    std::string host = lowerHost(target);
    std::string openerHost = opener ? lowerHost(opener) : std::string { };
    // uBlock: first-party when the popup's host is the opener's registrable domain or under it.
    bool thirdParty = openerHost.empty() || host.empty() || !hostCovers(host, siteOf(openerHost));
    std::string lowerTarget(target);
    for (auto& c : lowerTarget) c = lower(c);
    PopupContext context { target, lowerTarget, host, openerHost, thirdParty, openerHost.empty() || host != openerHost };
    // uBlock: important blocks win, then exceptions, then ordinary blocks.
    bool blocked = false, excepted = false;
    for (auto& rule : popupRules) {
        if (rule.kind == 'R' || (rule.exception ? excepted : (blocked && !rule.important))) continue;
        if (!ruleMatches(rule, context)) continue;
        if (rule.important && !rule.exception) return true;
        (rule.exception ? excepted : blocked) = true;
    }
    // Regular expressions see at most 4,096 characters, the length compile-lists.cjs
    // times them at (it leaves out any that are slow there).
    if (!popupRegexRules || target.size() > 4096) return blocked && !excepted;
    // Regular expressions only when they can still change the answer.
    for (auto& rule : popupRules) {
        if (rule.kind != 'R') continue;
        bool useful = rule.exception ? (blocked && !excepted) : (rule.important || !blocked);
        if (!useful || !rulePrefilter(rule, context)) continue;
        if (!popupRegex.attempted) initializePopupRegex();
        if (!regexMatches(rule.regex, target)) continue;
        if (rule.important && !rule.exception) return true;
        (rule.exception ? excepted : blocked) = true;
    }
    return blocked && !excepted;
}

// Per-site "trusted" switch written by the browser shell (one hostname per line).
// Checked against the top-level site so a trusted page loads all of its resources.
namespace {
std::mutex trustedLock;
std::vector<std::string> trusted;
bool trustedLoaded = false;
ino_t trustedInode = 0;
time_t trustedModified = 0;
off_t trustedSize = -1;
void refreshTrusted()
{
    // The shell replaces the file atomically (rename), so a new inode marks a change.
    struct stat info { };
    if (stat("/data/omni/ublock-allowlist.txt", &info)) { trusted.clear(); trustedLoaded = true; trustedSize = -1; return; }
    if (trustedLoaded && info.st_ino == trustedInode && info.st_mtime == trustedModified && info.st_size == trustedSize) return;
    trustedLoaded = true; trustedInode = info.st_ino; trustedModified = info.st_mtime; trustedSize = info.st_size;
    trusted.clear();
    FILE* file = fopen("/data/omni/ublock-allowlist.txt", "r");
    if (!file) return;
    char line[300];
    while (fgets(line, sizeof(line), file)) {
        std::string host(line);
        if (host.empty() || (host.back() != '\n' && !feof(file))) {
            int ch; while ((ch = fgetc(file)) != EOF && ch != '\n') { }
            continue;
        }
        while (!host.empty() && (host.back() == '\n' || host.back() == '\r' || host.back() == ' ')) host.pop_back();
        bool valid = !host.empty() && host.size() <= 253;
        for (char c : host) valid = valid && ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '-');
        if (valid) trusted.push_back(host);
    }
    fclose(file);
}
}

extern "C" bool omniUBlockSiteAllowed(const char* site)
{
    if (!site || !*site) return false;
    std::string host(site);
    for (auto& c : host) if (c >= 'A' && c <= 'Z') c = c - 'A' + 'a';
    while (!host.empty() && host.back() == '.') host.pop_back();
    std::lock_guard<std::mutex> guard(trustedLock);
    refreshTrusted();
    for (auto& entry : trusted)
        if (host == entry || (host.size() > entry.size() && host.compare(host.size() - entry.size(), entry.size(), entry) == 0 && host[host.size() - entry.size() - 1] == '.'))
            return true;
    return false;
}

#include <arpa/inet.h>
#include <string>
namespace {
std::string pnaHost(const char* url)
{
    if (!url) return {};
    std::string u(url); auto s = u.find("://"); if (s == std::string::npos) return {};
    s += 3; auto e = u.find_first_of("/?#", s); std::string h = u.substr(s, e == std::string::npos ? std::string::npos : e - s);
    if (auto at = h.rfind('@'); at != std::string::npos) h = h.substr(at + 1);
    if (!h.empty() && h[0] == '[') { auto c = h.find(']'); return c == std::string::npos ? std::string() : h.substr(1, c - 1); }
    if (auto c = h.rfind(':'); c != std::string::npos) h = h.substr(0, c);
    for (auto& ch : h) if (ch >= 'A' && ch <= 'Z') ch = ch - 'A' + 'a';
    while (!h.empty() && h.back() == '.') h.pop_back();
    return h;
}
bool pnaPrivate(const std::string& h)
{
    if (h.empty()) return false;
    if (h == "localhost" || (h.size() > 10 && !h.compare(h.size() - 10, 10, ".localhost")) || (h.size() > 6 && !h.compare(h.size() - 6, 6, ".local"))) return true;
    in_addr a4; if (inet_pton(AF_INET, h.c_str(), &a4) == 1) {
        uint32_t x = ntohl(a4.s_addr);
        return (x >> 24) == 10 || (x >> 24) == 127 || (x >> 20) == 0xAC1 || (x >> 16) == 0xC0A8 || (x >> 16) == 0xA9FE || x == 0 || (x >> 22) == (100u << 2 | 1);
    }
    // IPv6 by text (no in6_addr needed): loopback, unique-local fc00::/7, link-local fe80::/10, IPv4-mapped ::ffff:a.b.c.d
    if (h.find(':') != std::string::npos) {
        if (h == "::1" || h == "0:0:0:0:0:0:0:1") return true;
        if (h.rfind("::ffff:", 0) == 0 && h.find('.') != std::string::npos) return pnaPrivate(h.substr(7));
        return h.size() > 2 && ((h[0] == 'f' && (h[1] == 'c' || h[1] == 'd')) || (h[0] == 'f' && h[1] == 'e' && h.size() > 3 && h[2] >= '8' && h[2] <= 'b'));
    }
    return false;
}
}
extern "C" bool omniPrivateNetworkBlocked(const char* url, const char* documentURL)
{
    if (!access("/data/omni/sec-local-block.off", F_OK)) return false;        // the same Browser settings switch
    const std::string target = pnaHost(url), from = pnaHost(documentURL);
    if (from.empty() || !pnaPrivate(target) || pnaPrivate(from)) return false;  // typed navigations, private->private: allowed
    fprintf(stderr, "sec: blocked a public page (%s) from reaching %s (OMNI_SEC_PNA_V1)\n", from.c_str(), target.c_str());
    return true;
}
