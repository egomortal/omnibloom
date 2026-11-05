// OMNI_FEATURES_V2 + OMNI_VAULT_V2: saved logins and fill-on-demand.
// Logins are added BY HAND on the Passwords page (site, username, password typed on Omni's keyboard)
// and edited or deleted there. Omni never watches login forms and never reads what is typed into a
// page; there is no "save password?" prompt. Filling is always a user action (the keyboard's fill
// row, Site settings > Fill saved login, or R1 on the Passwords page); the fill script runs
// only in the main frame and checks the page's origin first, so a login is only ever written into
// the site it belongs to.
// Storage (OMNI_VAULT_V2, OmniVault.h): /data/omni/vault.v2, AES-256-GCM per entry with a fresh nonce on
// every save and authenticated data binding each login to its site. Without a PIN the data key is in
// /data/omni/vault.key: that stops casual reading and any tampering, but anyone who can read the console's
// files (FTP on the home network) can still read the key. With a PIN (Passwords > Set a PIN) the key is
// derived from the PIN (PBKDF2-HMAC-SHA256, 600,000 rounds) and nothing on the console can open the vault.
// The old OMNI_FEATURES_V2 files (XOR obfuscation) are migrated once and renamed *.xor-migrated; the
// Passwords page offers to remove that old copy.
#pragma once
enum { omniPwKindList = 7102, omniPwKindChoose = 7104, omniPwKindEdit = 7105 };

struct OmniPwEntry { std::string origin, user, pass; long long created = 0, used = 0; std::string id; };
struct OmniPwStore {
    std::vector<OmniPwEntry> list;      // decrypted logins (empty while the vault is locked)
    bool loaded = false;
    OmniVault::Vault* vault = nullptr;  // never destroyed (the process ends with _exit)
    int migrated = -1, undecodable = 0; // this session's migration result (-1 = none needed)
    long long lastUse = 0;
    int failedUnlocks = 0; long long retryAfter = 0;
};
static OmniPwStore omniPw;
static const int omniPwLockMinutes = 15;   // PIN mode: lock again after this long without using the vault
static std::string omniPwPinA, omniPwPinB;
static void omniPwWipe(std::string& s) { OmniVault::wipe(s); }
static void omniPwClearList()
{
    for (auto& e : omniPw.list) { omniPwWipe(e.user); omniPwWipe(e.pass); }
    omniPw.list.clear();
}
// vault entries (kind "login") -> omniPw.list
static void omniPwFromVault()
{
    omniPwClearList();
    if (!omniPw.vault || !omniPw.vault->unlocked()) return;
    for (auto& v : omniPw.vault->entries) if (v.kind == "login") {
        OmniPwEntry e; e.id = v.id; e.origin = v.origin; e.user = v.a; e.pass = v.b; e.created = v.created; e.used = v.used;
        omniPw.list.push_back(std::move(e));
    }
}
static bool omniPwLocked() { return omniPw.vault && omniPw.vault->pinMode() && !omniPw.vault->unlocked(); }
static bool omniPwBroken() { return omniPw.vault && omniPw.vault->openFailed(); }
static void omniPwLoad()
{
    const long long now = (long long)time(nullptr);
    if (omniPw.loaded) {
        if (omniPw.vault && omniPw.vault->pinMode() && omniPw.vault->unlocked() && now - omniPw.lastUse > omniPwLockMinutes * 60) {
            omniPw.vault->lock(); omniPwClearList();   // auto-lock
        }
        omniPw.lastUse = now;
        return;
    }
    omniPw.loaded = true; omniPw.lastUse = now;
    if (!omniPw.vault) omniPw.vault = new OmniVault::Vault(OMNI_DATA_DIR);
    omniPw.vault->load();
    if (omniPw.vault->canSave()) {
        int bad = 0;
        const int n = omniPw.vault->migrateLegacy(&bad);
        if (n > 0 || bad > 0) { omniPw.migrated = n; omniPw.undecodable = bad; }
        if (n != 0 || bad > 0) fprintf(stderr, "vault: OMNI_VAULT_V2 migrated %d login(s) from passwords.txt (%d unreadable)\n", n, bad);
    }
    omniPwFromVault();
    fprintf(stderr, "vault: OMNI_VAULT_V2 %s, %s, %zu login(s)%s%s\n", omniPw.vault->exists() ? "opened" : "new",
            omniPw.vault->openFailed() ? "CAN'T OPEN" : omniPw.vault->pinMode() ? (omniPw.vault->unlocked() ? "PIN, unlocked" : "PIN, locked") : "key file",
            omniPw.list.size(), omniPw.vault->recoveredFromBackup() ? ", restored from backup" : "", omniPw.vault->unreadable() ? ", some entries failed their check" : "");
}
// omniPw.list -> vault entries, then an encrypted atomic write. Returns false (and says why) if nothing was saved.
static bool omniPwSave()
{
    omniPwLoad();
    OmniVault::Vault& v = *omniPw.vault;
    if (!v.canSave()) { notice(omniPwLocked() ? "Passwords are locked: unlock them first" : "Passwords can't be saved: " + v.error()); return false; }
    std::vector<OmniVault::Entry> before = v.entries, keep;   // kept to undo the change if the write fails
    for (auto& e : v.entries) if (e.kind != "login") keep.push_back(e);   // 2FA secrets etc. stay as they are
    for (auto& e : v.entries) { OmniVault::wipe(e.a); OmniVault::wipe(e.b); OmniVault::wipe(e.c); }
    v.entries.swap(keep);
    auto wipeAll = [](std::vector<OmniVault::Entry>& list) { for (auto& e : list) { OmniVault::wipe(e.a); OmniVault::wipe(e.b); OmniVault::wipe(e.c); } list.clear(); };
    for (auto& e : omniPw.list) {
        OmniVault::Entry x; x.id = e.id.size() == 16 ? e.id : OmniVault::Vault::newId(); e.id = x.id;
        x.kind = "login"; x.origin = e.origin; x.a = e.user; x.b = e.pass; x.created = e.created; x.used = e.used;
        v.entries.push_back(std::move(x));
    }
    if (!v.save()) {
        fprintf(stderr, "vault: save failed (%s)\n", v.error().c_str());
        v.entries.swap(before); wipeAll(before);
        omniPwFromVault();   // the list shows what is really stored
        notice("Passwords weren't saved: " + v.error());
        return false;
    }
    wipeAll(before);
    return true;
}
// PIN prompts (typed on Omni's keyboard; the label contains "assword" so the keyboard shows dots).
static void omniPwUnlockThen(std::function<void()> next)
{
    omniPwLoad();
    if (!omniPwLocked()) { if (next) next(); return; }
    const long long now = (long long)time(nullptr);
    if (now < omniPw.retryAfter) { notice("Too many wrong tries: wait " + std::to_string(omniPw.retryAfter - now) + " s"); return; }
    omniPwPinA.clear();
    omniKbEdit(&omniPwPinA, "Vault password or PIN", [next](bool ok) {
        if (!ok) { omniPwWipe(omniPwPinA); return; }
        notice("Unlocking...");
        const auto t0 = std::chrono::steady_clock::now();
        const bool good = omniPw.vault->unlock(omniPwPinA);
        omniPwWipe(omniPwPinA);
        fprintf(stderr, "vault: unlock %s in %lld ms (%d PBKDF2 rounds)\n", good ? "ok" : "refused",
                (long long)std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - t0).count(), omniPw.vault->iterations());
        if (!good) {
            if (++omniPw.failedUnlocks >= 5) { omniPw.retryAfter = (long long)time(nullptr) + 30; omniPw.failedUnlocks = 0; }
            notice(omniPw.vault->error() == "Wrong PIN" ? std::string("Wrong vault password or PIN") : "Couldn't unlock: " + omniPw.vault->error());
            return;
        }
        omniPw.failedUnlocks = 0; omniPw.lastUse = (long long)time(nullptr);
        int bad = 0; const int n = omniPw.vault->migrateLegacy(&bad);   // an older build may have written passwords.txt again
        if (n > 0 || bad > 0) { omniPw.migrated = n; omniPw.undecodable = bad; }
        omniPwFromVault();
        notice("Passwords unlocked");
        if (next) next();
    });
}
static void omniPwSetPinFlow()
{
    omniPwUnlockThen([] {
        omniPwPinA.clear(); omniPwPinB.clear();
        omniKbEdit(&omniPwPinA, "New vault password or PIN (6+ characters)", [](bool ok) {
            if (!ok) { omniPwWipe(omniPwPinA); return; }
            if (omniPwPinA.size() < 6) { omniPwWipe(omniPwPinA); notice("Use at least 6 characters"); return; }
            omniKbEdit(&omniPwPinB, "Type the vault password again", [](bool ok2) {
                const bool same = ok2 && omniPwPinA == omniPwPinB;
                omniPwWipe(omniPwPinB);
                if (!same) { omniPwWipe(omniPwPinA); if (ok2) notice("They didn't match: nothing changed"); return; }
                notice("Protecting the vault...");
                const auto t0 = std::chrono::steady_clock::now();
                const bool done = omniPw.vault->setPin(omniPwPinA);
                omniPwWipe(omniPwPinA);
                fprintf(stderr, "vault: set PIN %s in %lld ms\n", done ? "ok" : "failed", (long long)std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - t0).count());
                notice(done ? "Passwords are now protected by your PIN" : "PIN not set: " + omniPw.vault->error());
                omniFxRefresh();
            });
        });
    });
}
// vault.capabilities for the s3 omnibloomHost bridge (ENGINE-CONTRACT.md section 5 / R3-036).
[[maybe_unused]] static std::string omniVaultCapabilitiesJson()
{
    omniPwLoad();
    const bool pin = omniPw.vault && omniPw.vault->pinMode();
    return std::string("{\"version\":1,\"encrypted\":true,\"authenticated\":true,\"protectedKey\":") + (pin ? "true" : "false")
        + ",\"unlocked\":" + (omniPw.vault && omniPw.vault->unlocked() ? "true" : "false") + "}";
}
// Removes the renamed OMNI_FEATURES_V2 files (old XOR copy) after the user confirms.
static int omniPwRemoveLegacyCopies()
{
    int n = 0;
    if (DIR* d = opendir(OMNI_DATA_DIR)) {
        std::vector<std::string> names;
        while (dirent* e = readdir(d)) { const std::string s = e->d_name; if (s.rfind("passwords.txt.xor-migrated", 0) == 0 || s.rfind("passwords.key.xor-migrated", 0) == 0) names.push_back(s); }
        closedir(d);
        for (auto& s : names) if (unlink((std::string(OMNI_DATA_DIR) + s).c_str()) == 0) ++n;
    }
    return n;
}
static std::vector<int> omniPwFor(const std::string& origin)
{
    omniPwLoad();
    std::vector<int> out;
    if (origin.empty() || omniPwLocked()) return out;
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
    omniPwLoad();
    if (omniPwLocked()) { omniPwUnlockThen([] { omniPwFillCurrent(); }); return; }
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
            omniPw.list.push_back({ origin, omniPwEditUser, omniPwEditPass, (long long)time(nullptr), (long long)time(nullptr), std::string() });
        }
        if (!omniPwSave()) return true;
        notice("Login saved for " + omniPwShownOrigin(origin));
        omniFxPop();
        return true;
    }
    case 5:
        if (omniPwEditIndex < 0) return true;
        omniAsk("Delete this login?", omniPwShownOrigin(omniPwEditSite.empty() ? std::string() : omniPwEditSite) + " will be removed from this console.", "Delete", [](bool ok) {
            if (!ok) return;
            omniPwLoad();
            if (omniPwEditIndex >= 0 && omniPwEditIndex < int(omniPw.list.size())) { omniPw.list.erase(omniPw.list.begin() + omniPwEditIndex); if (omniPwSave()) notice("Login deleted"); }
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
    p.subtitle = "Typed on this console. Stored encrypted (AES-256-GCM).";
    p.build = omniPwEditBuild; p.input = omniPwEditInput;
    p.faces = { { 0, "Edit / save" }, { 1, "Back" } };
    omniFxPush(std::move(p));
}
static void omniPwListBuild(OmniFxPanel& p)
{
    omniPwLoad();
    OmniVault::Vault& v = *omniPw.vault;
    if (omniPwBroken()) {
        OmniFxRow r; r.id = 3; r.label = "The password vault can't be opened"; r.detail = v.error() + ". Nothing will be written over it."; r.enabled = false; p.rows.push_back(r);
        return;
    }
    { OmniFxRow r; r.id = 4; r.label = "Protection"; r.enabled = false;
      r.value = omniPwLocked() ? std::string("Locked (PIN)") : v.pinMode() ? std::string("Encrypted, PIN on") : std::string("Encrypted, no PIN");
      p.rows.push_back(r); }
    if (omniPwLocked()) { OmniFxRow r; r.id = 5; r.label = "Unlock with your vault password or PIN"; p.rows.push_back(r); }
    else {
        OmniFxRow s; s.id = 6; s.label = v.pinMode() ? "Change PIN" : "Set a PIN (recommended)";
        if (!v.pinMode()) s.detail = "Without one, anyone who can read this console's files can read your passwords";
        p.rows.push_back(s);
        if (v.pinMode()) { OmniFxRow r; r.id = 7; r.label = "Remove PIN"; p.rows.push_back(r); OmniFxRow l; l.id = 8; l.label = "Lock now"; p.rows.push_back(l); }
    }
    if (v.legacyLeftovers()) { OmniFxRow r; r.id = 9; r.label = "Remove the old unencrypted copy"; r.danger = true; p.rows.push_back(r); }
    if (v.recoveredFromBackup()) { OmniFxRow r; r.id = 3; r.label = "Restored from the backup copy (the vault file was damaged)"; r.enabled = false; p.rows.push_back(r); }
    if (omniPwLocked()) return;
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
    if (v.unreadable()) { OmniFxRow r; r.id = 3; r.label = std::to_string(v.unreadable()) + " saved item(s) failed their integrity check and are hidden"; r.enabled = false; p.rows.push_back(r); }
}
static bool omniPwListInput(OmniFxPanel& p, const OmniFxRow& r, int b)
{
    if (r.id == 1 && b == SDL_CONTROLLER_BUTTON_A) { omniPwUnlockThen([] { omniPwEditShow(-1); }); return true; }
    if (b == SDL_CONTROLLER_BUTTON_A && r.id == 5) { omniPwUnlockThen([] { omniFxRefresh(); }); return true; }
    if (b == SDL_CONTROLLER_BUTTON_A && r.id == 6) { omniPwSetPinFlow(); return true; }
    if (b == SDL_CONTROLLER_BUTTON_A && r.id == 7) {
        omniAsk("Remove the PIN?", "Passwords stay encrypted, but the key will be stored on this console again, so anyone who can read its files could read them.", "Remove PIN", [](bool ok) {
            if (!ok) return;
            notice(omniPw.vault->removePin() ? "PIN removed" : "PIN not removed: " + omniPw.vault->error());
            omniFxRefresh();
        });
        return true;
    }
    if (b == SDL_CONTROLLER_BUTTON_A && r.id == 8) { omniPw.vault->lock(); omniPwClearList(); notice("Passwords locked"); omniFxRefresh(); return true; }
    if (b == SDL_CONTROLLER_BUTTON_A && r.id == 9) {
        omniAsk("Remove the old unencrypted copy?", "Before this update, logins were stored with weak obfuscation. That old copy was kept as passwords.*.xor-migrated; your logins are now in the encrypted vault.", "Remove", [](bool ok) {
            if (!ok) return;
            const int n = omniPwRemoveLegacyCopies();
            notice(n > 0 ? std::string("Old copy removed") : std::string("Nothing was removed"));
            omniFxRefresh();
        });
        return true;
    }
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
                if (index >= 0 && index < int(omniPw.list.size())) { omniPw.list.erase(omniPw.list.begin() + index); if (omniPwSave()) notice("Login deleted"); omniFxRefresh(); }
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
    omniPwLoad();
    if (omniPw.migrated > 0 || omniPw.undecodable > 0) {
        notice(std::to_string(std::max(0, omniPw.migrated)) + " saved login(s) moved into the encrypted vault" + (omniPw.undecodable ? " (" + std::to_string(omniPw.undecodable) + " couldn't be read)" : std::string()));
        omniPw.migrated = -1; omniPw.undecodable = 0;
    }
    OmniFxPanel p;
    p.kind = omniPwKindList; p.w = 900; p.maxVisible = 10;
    p.title = "Passwords"; p.subtitle = "Saved logins on this console";
    p.build = omniPwListBuild; p.input = omniPwListInput;
    p.faces = { { 0, "Reveal" }, { 3, "Edit" }, { 2, "Delete" }, { 1, "Back" } };
    p.extra = "R1 fills the selected login into the current page";
    omniFxPush(std::move(p));
}
