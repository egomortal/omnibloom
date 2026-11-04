// OMNI_FEATURES_V2: saved logins and fill-on-demand.
// Logins are added BY HAND on the Passwords page (site, username, password typed on Omni's keyboard)
// and edited or deleted there. Omni never watches login forms and never reads what is typed into a
// page; there is no "save password?" prompt. Filling is always a user action (the keyboard's fill
// row, Site settings > Fill saved login, or Triangle on the Passwords page); the fill script runs
// only in the main frame and checks the page's origin first, so a login is only ever written into
// the site it belongs to.
// Storage: /data/omni/passwords.txt; each username and password is XORed with a keystream made from
// /data/omni/passwords.key and a per-value nonce, then hex encoded. This is OBFUSCATION, NOT
// encryption: the key is stored next to the data, so anyone who can read the console's files can read
// the passwords. The console has no keychain or secure storage Omni can use.
#pragma once
enum { omniPwKindList = 7102, omniPwKindChoose = 7104, omniPwKindEdit = 7105 };

struct OmniPwEntry { std::string origin, user, pass; long long created = 0, used = 0; };
struct OmniPwStore {
    std::vector<OmniPwEntry> list;
    std::vector<std::string> keepRaw;   // login lines that could not be decoded (key missing/changed): kept untouched
    bool loaded = false, haveKey = false;
    uint8_t key[32] {};
};
static OmniPwStore omniPw;
static uint64_t omniPwMix(uint64_t& s)   // splitmix64
{
    uint64_t z = (s += 0x9E3779B97F4A7C15ull);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
    return z ^ (z >> 31);
}
static void omniPwRandom(uint8_t* out, size_t n)
{
    memset(out, 0, n);
    if (FILE* f = fopen("/dev/urandom", "rb")) { if (fread(out, 1, n, f) != n) { } fclose(f); }
    static uint64_t counter = 0;
    uint64_t s = SDL_GetPerformanceCounter() ^ (uint64_t(time(nullptr)) << 21) ^ uint64_t(uintptr_t(out)) ^ (uint64_t(getpid()) << 42) ^ (++counter * 0xD1B54A32D192ED03ull);
    for (size_t i = 0; i < n; i += 8) { const uint64_t r = omniPwMix(s); for (size_t k = 0; k < 8 && i + k < n; ++k) out[i + k] ^= uint8_t(r >> (8 * k)); }
}
static std::string omniPwHex(const std::string& b)
{
    static const char* h = "0123456789abcdef";
    std::string o;
    for (unsigned char c : b) { o += h[c >> 4]; o += h[c & 15]; }
    return o;
}
static bool omniPwUnhex(const std::string& h, std::string& out)
{
    out.clear();
    if (h.size() % 2) return false;
    auto v = [](char c) { return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1; };
    for (size_t i = 0; i < h.size(); i += 2) { const int a = v(h[i]), b = v(h[i + 1]); if (a < 0 || b < 0) return false; out += char(a * 16 + b); }
    return true;
}
static void omniPwStream(std::string& data, size_t from, const uint8_t* nonce)
{
    uint64_t s = 0xcbf29ce484222325ull;
    for (int i = 0; i < 32; ++i) s = (s ^ omniPw.key[i]) * 0x100000001b3ull;
    for (int i = 0; i < 8; ++i) s = (s ^ nonce[i]) * 0x100000001b3ull;
    for (size_t i = from; i < data.size(); i += 8) {
        const uint64_t r = omniPwMix(s);
        for (size_t k = 0; k < 8 && i + k < data.size(); ++k) data[i + k] = char(uint8_t(data[i + k]) ^ uint8_t(r >> (8 * k)));
    }
}
static std::string omniPwSeal(const std::string& plain)
{
    uint8_t nonce[8];
    omniPwRandom(nonce, 8);
    std::string out(reinterpret_cast<const char*>(nonce), 8);
    out += plain;
    omniPwStream(out, 8, nonce);
    return omniPwHex(out);
}
static bool omniPwUnseal(const std::string& hex, std::string& plain)
{
    std::string raw;
    if (!omniPwUnhex(hex, raw) || raw.size() < 8) return false;
    uint8_t nonce[8];
    memcpy(nonce, raw.data(), 8);
    omniPwStream(raw, 8, nonce);
    plain = raw.substr(8);
    return true;
}
static void omniPwLoad()
{
    if (omniPw.loaded) return;
    omniPw.loaded = true;
    if (FILE* f = fopen(omniData("passwords.key").c_str(), "r")) {
        char line[160] = {};
        if (fgets(line, sizeof(line), f)) {
            std::string s(line), raw;
            while (!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
            if (omniPwUnhex(s, raw) && raw.size() == 32) { memcpy(omniPw.key, raw.data(), 32); omniPw.haveKey = true; }
        }
        fclose(f);
    }
    if (FILE* f = fopen(omniData("passwords.txt").c_str(), "r")) {
        char line[4096];
        while (fgets(line, sizeof(line), f)) {
            std::string s(line);
            while (!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
            std::vector<std::string> part;
            size_t from = 0;
            for (;;) { const size_t t = s.find('\t', from); part.push_back(s.substr(from, t == std::string::npos ? std::string::npos : t - from)); if (t == std::string::npos) break; from = t + 1; }
            if (part[0] == "login" && part.size() >= 6) {
                OmniPwEntry e;
                e.origin = part[1]; e.created = atoll(part[4].c_str()); e.used = atoll(part[5].c_str());
                if (omniPw.haveKey && omniPwUnseal(part[2], e.user) && omniPwUnseal(part[3], e.pass)) omniPw.list.push_back(std::move(e));
                else omniPw.keepRaw.push_back(s);
            }
        }
        fclose(f);
    }
}
static void omniPwSave()
{
    if (!omniPw.haveKey) {
        omniPwRandom(omniPw.key, 32);
        omniPw.haveKey = true;
        omniIoQueue(omniData("passwords.key"), omniPwHex(std::string(reinterpret_cast<const char*>(omniPw.key), 32)) + "\n", false);
    }
    std::string out = "omni-passwords\t1\n";
    for (auto& e : omniPw.list)
        out += "login\t" + omniOneLine(e.origin, 300) + "\t" + omniPwSeal(e.user) + "\t" + omniPwSeal(e.pass) + "\t" + std::to_string(e.created) + "\t" + std::to_string(e.used) + "\n";
    for (auto& r : omniPw.keepRaw) out += r + "\n";
    omniIoQueue(omniData("passwords.txt"), std::move(out), false);
}
static std::vector<int> omniPwFor(const std::string& origin)
{
    omniPwLoad();
    std::vector<int> out;
    if (origin.empty()) return out;
    for (size_t i = 0; i < omniPw.list.size(); ++i) if (omniPw.list[i].origin == origin) out.push_back(int(i));
    std::sort(out.begin(), out.end(), [](int a, int b) { return omniPw.list[a].used > omniPw.list[b].used; });
    return out;
}
static std::string omniPwShownOrigin(const std::string& origin)
{
    const size_t s = origin.find("://");
    const std::string rest = s == std::string::npos ? origin : origin.substr(s + 3);
    return origin.rfind("http://", 0) == 0 ? rest + " (http)" : rest;
}
static std::string omniPwDots(const std::string& p) { std::string d; for (size_t i = 0; i < std::min<size_t>(10, std::max<size_t>(6, omniCpCount(p))); ++i) d += "\xe2\x80\xa2"; return d; }

// --- filling (shell -> page), only when the user asks ----------------------------------------------
// Returns 'origin' (wrong site), 'none' (no field), 'error', or what was filled ('u' / 'p' / 'up').
static const char* const omniPwFillScript = R"JS((function(H,U,P){try{var L=location,h=String(L.hostname).toLowerCase();
if(h.indexOf('www.')===0&&h.indexOf('.',4)>=0)h=h.slice(4);
if(L.protocol+'//'+h+(L.port?':'+L.port:'')!==H)return 'origin';
var d=document,a=d.activeElement;
function vis(e){if(!e||e.disabled||e.readOnly)return false;var r=e.getBoundingClientRect();return r.width>0&&r.height>0;}
function ty(e){return String(e.getAttribute('type')||'text').toLowerCase();}
function set(e,v){try{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,v);}catch(x){e.value=v;}
e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));}
var pw=null,user=null,root=(a&&a.form)||d;
if(a&&a.tagName==='INPUT'&&ty(a)==='password')pw=a;
if(!pw){var ps=[].slice.call(root.querySelectorAll('input[type=password]')).filter(vis);pw=ps[0]||null;}
if(a&&a.tagName==='INPUT'&&a!==pw&&/^(text|email|tel)$/.test(ty(a)))user=a;
if(!user){var ins=[].slice.call(((pw&&pw.form)||root).querySelectorAll('input')).filter(vis),i=pw?ins.indexOf(pw):ins.length;
for(var k=i-1;k>=0;k--){if(/^(text|email|tel)$/.test(ty(ins[k]))){user=ins[k];break;}}
if(!user){var q=root.querySelector('input[autocomplete~=username],input[type=email]');if(vis(q))user=q;}}
var r='';if(user&&U){set(user,U);r+='u';}if(pw&&P){set(pw,P);r+='p';}
try{if(a&&a.focus&&a!==d.body)a.focus();}catch(x){}
return r||'none';}catch(x){return 'error';}}))JS";
static void omniPwFill(int index)
{
    omniPwLoad();
    Tab* t = active();
    if (!t || index < 0 || index >= int(omniPw.list.size())) return;
    const OmniPwEntry& e = omniPw.list[index];
    if (omniF2OriginOf(t->url) != e.origin) { notice("That login is for " + omniPwShownOrigin(e.origin)); return; }
    const std::string js = std::string(omniPwFillScript) + "(" + omniF2Json(e.origin) + "," + omniF2Json(e.user) + "," + omniF2Json(e.pass) + ")";
    auto src = adoptWK(WKStringCreateWithUTF8CString(js.c_str()));
    omniPw.list[index].used = time(nullptr);
    omniPwSave();
    WKPageEvaluateJavaScriptInMainFrame(t->page, src.get(), const_cast<void*>(static_cast<const void*>(t)), [](WKTypeRef result, WKErrorRef error, void* context) {
        if (!omniTabAlive(context)) return;
        const std::string r = omniFxResultString(result, error);
        if (r == "origin") notice("The page changed site: nothing was filled");
        else if (r == "none" || r.empty() || r == "error") notice("No sign-in field found on this page");
        else notice(r == "u" ? "Username filled (the password goes on the next page)" : "Login filled: now press Go or the page's sign-in button");
        if (editing && omniKb.kind == 1 && context == active()) omniKbProbe();
    });
}
static bool omniPwChooseInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    omniFxCloseAll();
    omniPwFill(r.id - 1000);
    return true;
}
static void omniPwFillCurrent()
{
    Tab* t = active();
    const auto idx = omniPwFor(t ? omniF2OriginOf(t->url) : std::string());
    if (idx.empty()) { notice("No saved login for this site"); return; }
    if (idx.size() == 1) { omniFxCloseAll(); omniPwFill(idx[0]); return; }
    OmniFxPanel p;
    p.kind = omniPwKindChoose; p.w = 700; p.title = "Fill which login?"; p.subtitle = omniPwShownOrigin(omniPw.list[idx[0]].origin);
    for (int i : idx) { OmniFxRow r; r.id = 1000 + i; r.label = omniPw.list[i].user.empty() ? std::string("(no username)") : omniPw.list[i].user; r.value = omniAgo(omniPw.list[i].used); p.rows.push_back(r); }
    p.input = omniPwChooseInput;
    p.faces = { { 0, "Fill" }, { 1, "Back" } };
    omniFxPush(std::move(p));
}

// --- Passwords page (add by hand, edit, delete, reveal on press) -----------------------------------
static int omniPwEditIndex = -1;           // -1 = adding a new login
static std::string omniPwEditSite, omniPwEditUser, omniPwEditPass;
static int omniPwRevealRow = -1;           // list row whose password is shown while Cross is held
static void omniPwEditBuild(OmniFxPanel& p)
{
    auto add = [&](int id, const char* label, std::string value) { OmniFxRow r; r.id = id; r.label = label; r.value = std::move(value); r.stepper = false; p.rows.push_back(r); };
    add(1, "Website", omniPwEditSite.empty() ? std::string("Press Cross to type") : omniPwEditSite);
    add(2, "Username", omniPwEditUser.empty() ? std::string("(optional)") : omniPwEditUser);
    add(3, "Password", omniPwEditPass.empty() ? std::string("Press Cross to type") : omniPwDots(omniPwEditPass));
    add(4, omniPwEditIndex < 0 ? "Save login" : "Save changes", "");
    if (omniPwEditIndex >= 0) { add(5, "Delete this login", ""); p.rows.back().danger = true; }
}
static bool omniPwEditInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    switch (r.id) {
    case 1: omniKbEdit(&omniPwEditSite, "Website (e.g. example.com)", [](bool ok) { if (ok) omniFxRefresh(); }); return true;
    case 2: omniKbEdit(&omniPwEditUser, "Username or email", [](bool ok) { if (ok) omniFxRefresh(); }); return true;
    case 3: omniKbEdit(&omniPwEditPass, "Password", [](bool ok) { if (ok) omniFxRefresh(); }); return true;
    case 4: {
        std::string site = omniPwEditSite;
        while (!site.empty() && (site.front() == ' ')) site.erase(site.begin());
        while (!site.empty() && site.back() == ' ') site.pop_back();
        if (site.empty() || omniPwEditPass.empty()) { notice("A website and a password are needed"); return true; }
        std::string origin = omniF2OriginOf(omniWebURL(site) ? site : "https://" + site);
        if (origin.empty()) { notice("That doesn't look like a website address"); return true; }
        omniPwLoad();
        if (omniPwEditIndex >= 0 && omniPwEditIndex < int(omniPw.list.size())) {
            OmniPwEntry& e = omniPw.list[omniPwEditIndex];
            e.origin = origin; e.user = omniPwEditUser; e.pass = omniPwEditPass; e.used = time(nullptr);
        } else {
            omniPw.list.push_back({ origin, omniPwEditUser, omniPwEditPass, (long long)time(nullptr), (long long)time(nullptr) });
        }
        omniPwSave();
        notice("Login saved for " + omniPwShownOrigin(origin));
        omniFxPop();
        return true;
    }
    case 5:
        if (omniPwEditIndex < 0) return true;
        omniAsk("Delete this login?", omniPwShownOrigin(omniPwEditSite.empty() ? std::string() : omniPwEditSite) + " will be removed from this console.", "Delete", [](bool ok) {
            if (!ok) return;
            omniPwLoad();
            if (omniPwEditIndex >= 0 && omniPwEditIndex < int(omniPw.list.size())) { omniPw.list.erase(omniPw.list.begin() + omniPwEditIndex); omniPwSave(); notice("Login deleted"); }
            omniFxPop();
        });
        return true;
    }
    return false;
}
static void omniPwEditShow(int index)
{
    omniPwEditIndex = index;
    if (index >= 0 && index < int(omniPw.list.size())) {
        // show the saved origin for editing (keep http:// so it round-trips; https host shown bare)
        const std::string o = omniPw.list[index].origin;
        omniPwEditSite = o.rfind("http://", 0) == 0 ? o : o.substr(o.find("://") == std::string::npos ? 0 : o.find("://") + 3);
        omniPwEditUser = omniPw.list[index].user;
        omniPwEditPass = omniPw.list[index].pass;
    } else { omniPwEditSite.clear(); omniPwEditUser.clear(); omniPwEditPass.clear(); }
    OmniFxPanel p;
    p.kind = omniPwKindEdit; p.w = 760;
    p.title = index < 0 ? "Add a login" : "Edit login";
    p.subtitle = "Typed on this console. Not encrypted (see About).";
    p.build = omniPwEditBuild; p.input = omniPwEditInput;
    p.faces = { { 0, "Edit / save" }, { 1, "Back" } };
    omniFxPush(std::move(p));
}
static void omniPwListBuild(OmniFxPanel& p)
{
    omniPwLoad();
    OmniFxRow addRow; addRow.id = 1; addRow.label = "Add a login"; addRow.icon = omniIconPlus; p.rows.push_back(addRow);
    std::vector<int> order;
    for (size_t i = 0; i < omniPw.list.size(); ++i) order.push_back(int(i));
    std::sort(order.begin(), order.end(), [](int a, int b) {
        if (omniPw.list[a].origin != omniPw.list[b].origin) return omniPw.list[a].origin < omniPw.list[b].origin;
        return omniPw.list[a].user < omniPw.list[b].user;
    });
    for (int i : order) {
        OmniFxRow r; r.id = 1000 + i;
        r.label = omniPwShownOrigin(omniPw.list[i].origin);
        r.detail = omniPw.list[i].user;
        r.value = (omniPwRevealRow == 1000 + i) ? omniPw.list[i].pass : omniPwDots(omniPw.list[i].pass);
        p.rows.push_back(r);
    }
    if (omniPw.list.empty()) { OmniFxRow r; r.id = 2; r.label = "No saved logins yet"; r.enabled = false; p.rows.push_back(r); }
    if (!omniPw.keepRaw.empty()) { OmniFxRow r; r.id = 3; r.label = std::to_string(omniPw.keepRaw.size()) + " login(s) can't be read (key changed)"; r.enabled = false; p.rows.push_back(r); }
}
static bool omniPwListInput(OmniFxPanel& p, const OmniFxRow& r, int b)
{
    if (r.id == 1 && b == SDL_CONTROLLER_BUTTON_A) { omniPwEditShow(-1); return true; }
    if (r.id < 1000) return b == SDL_CONTROLLER_BUTTON_A;
    const int index = r.id - 1000;
    if (b == SDL_CONTROLLER_BUTTON_A) { omniPwRevealRow = omniPwRevealRow == r.id ? -1 : r.id; (void)p; return true; }   // reveal toggles on press
    if (b == SDL_CONTROLLER_BUTTON_Y) { omniPwEditShow(index); return true; }
    if (b == SDL_CONTROLLER_BUTTON_X) {
        omniPwLoad();
        if (index >= 0 && index < int(omniPw.list.size())) {
            const std::string site = omniPwShownOrigin(omniPw.list[index].origin);
            omniAsk("Delete the login for " + site + "?", "It will be removed from this console.", "Delete", [index](bool ok) {
                if (!ok) return; omniPwLoad();
                if (index >= 0 && index < int(omniPw.list.size())) { omniPw.list.erase(omniPw.list.begin() + index); omniPwSave(); notice("Login deleted"); omniFxRefresh(); }
            });
        }
        return true;
    }
    if (b == SDL_CONTROLLER_BUTTON_RIGHTSHOULDER || b == SDL_CONTROLLER_BUTTON_LEFTSHOULDER) {   // R1: fill into the current page
        if (b == SDL_CONTROLLER_BUTTON_RIGHTSHOULDER) { omniFxCloseAll(); omniPwFill(index); }
        return true;
    }
    return false;
}
static void omniPwListShow()
{
    omniPwRevealRow = -1;
    OmniFxPanel p;
    p.kind = omniPwKindList; p.w = 900; p.maxVisible = 10;
    p.title = "Passwords"; p.subtitle = "Saved logins on this console";
    p.build = omniPwListBuild; p.input = omniPwListInput;
    p.faces = { { 0, "Reveal" }, { 3, "Edit" }, { 2, "Delete" }, { 1, "Back" } };
    p.extra = "R1 fills the selected login into the current page";
    omniFxPush(std::move(p));
}
