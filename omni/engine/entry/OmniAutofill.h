// OMNI_FEATURES_V2: form autofill. One profile (name, email, phone, street, city, postcode, country)
// kept in /data/omni/autofill.txt as plain text and edited in Browser settings > Autofill. Omni never
// reads what is typed into pages; it only writes the profile into matching empty fields of the
// focused form when the user picks "Fill form" (the row above the keyboard, or Site settings).
#pragma once
enum { omniAfKindPanel = 7103 };

// --- form autofill profile -------------------------------------------------------------------------
struct OmniAfField { const char* key; const char* label; };
static const OmniAfField omniAfFields[] = {
    { "name", "Full name" }, { "email", "Email" }, { "tel", "Phone" }, { "street", "Street address" },
    { "city", "Town / city" }, { "zip", "Postcode / ZIP" }, { "country", "Country" },
};
constexpr int omniAfCount = int(sizeof(omniAfFields) / sizeof(omniAfFields[0]));
struct OmniAf { bool loaded = false, offer = true; std::map<std::string, std::string> v; };
static OmniAf omniAf;
static void omniAfLoad()
{
    if (omniAf.loaded) return;
    omniAf.loaded = true;
    if (FILE* f = fopen(omniData("autofill.txt").c_str(), "r")) {
        char line[1200];
        while (fgets(line, sizeof(line), f)) {
            std::string s(line);
            while (!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
            const size_t t = s.find('\t');
            if (t == std::string::npos) continue;
            if (s.substr(0, t) == "offer") omniAf.offer = s.substr(t + 1) != "0";
            else if (t) omniAf.v[s.substr(0, t)] = s.substr(t + 1);
        }
        fclose(f);
    }
}
static void omniAfSave()
{
    std::string out = "offer\t" + std::string(omniAf.offer ? "1" : "0") + "\n";
    for (auto& [k, v] : omniAf.v) if (!v.empty()) out += omniOneLine(k, 40) + "\t" + omniOneLine(v, 300) + "\n";
    omniIoQueue(omniData("autofill.txt"), std::move(out), false);
}
static bool omniAfEmpty() { omniAfLoad(); for (auto& [k, v] : omniAf.v) if (!v.empty()) return false; return true; }
static std::string omniAfValue(const std::string& kind)
{
    omniAfLoad();
    auto get = [](const char* k) { auto it = omniAf.v.find(k); return it == omniAf.v.end() ? std::string() : it->second; };
    if (kind == "first" || kind == "last") {
        const std::string n = get("name");
        const size_t sp = n.rfind(' ');
        if (sp == std::string::npos) return kind == "first" ? n : std::string();
        return kind == "first" ? n.substr(0, sp) : n.substr(sp + 1);
    }
    return get(kind.c_str());
}
// Field kind from autocomplete, type, name, id, placeholder and label: name first last email tel street city zip country.
static const char* const omniAfKindJS = R"JS(function(e){var t=String(e.getAttribute('type')||'').toLowerCase();
if(/^(password|hidden|checkbox|radio|submit|button|file|image|reset|search|number|date|range|color)$/.test(t))return '';
var ac=String(e.getAttribute('autocomplete')||'').toLowerCase(),n=(String(e.name||'')+' '+String(e.id||'')+' '+String(e.getAttribute('placeholder')||'')+' '+String(e.getAttribute('aria-label')||'')).toLowerCase();
if(/\bemail\b/.test(ac)||t==='email')return 'email';if(/\btel\b/.test(ac)||t==='tel')return 'tel';
if(/given-name/.test(ac))return 'first';if(/family-name/.test(ac))return 'last';if(/(^|\s)name$/.test(ac))return 'name';
if(/street-address|address-line1/.test(ac))return 'street';if(/address-level2/.test(ac))return 'city';
if(/postal-code/.test(ac))return 'zip';if(/country/.test(ac))return 'country';
if(/(user|nick|organi|cc-|one-time|password)/.test(ac))return '';
if(/e-?mail/.test(n))return 'email';if(/phone|mobile|\btel/.test(n))return 'tel';
if(/user|login|search|captcha|code|company|organi|coupon|promo/.test(n))return '';
if(/first.?name|given|fname/.test(n))return 'first';if(/last.?name|surname|family|lname/.test(n))return 'last';
if(/full.?name|your.?name|\bname\b/.test(n))return 'name';if(/city|town/.test(n))return 'city';
if(/zip|postal|postcode/.test(n))return 'zip';if(/country/.test(n))return 'country';
if(/street|address|addr/.test(n)&&!/mail|\bip\b/.test(n))return 'street';return '';})JS";
static void omniAfFill()
{
    Tab* t = active();
    if (!t) return;
    omniAfLoad();
    std::string values = "{";
    for (const char* k : { "name", "first", "last", "email", "tel", "street", "city", "zip", "country" }) {
        const std::string v = omniAfValue(k);
        if (v.empty()) continue;
        if (values.size() > 1) values += ",";
        values += omniF2Json(k) + ":" + omniF2Json(v);
    }
    values += "}";
    const std::string js = std::string("(function(V){try{var KIND=") + omniAfKindJS + R"JS(;var d=document,a=d.activeElement,root=(a&&a.form)||d,n=0;
function set(e,v){try{var pr=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(pr,'value').set.call(e,v);}catch(x){e.value=v;}
e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));}
var els=root.querySelectorAll('input,textarea,select');
for(var i=0;i<els.length&&i<400;i++){var e=els[i];if(e.disabled||e.readOnly)continue;var r=e.getBoundingClientRect();if(!(r.width>0&&r.height>0))continue;
var k=KIND(e),v=k&&V[k];if(!v)continue;
if(e.tagName==='SELECT'){var lv=String(v).toLowerCase();for(var j=0;j<e.options.length;j++){var o=e.options[j];
if(String(o.text).trim().toLowerCase()===lv||String(o.value).toLowerCase()===lv){if(e.selectedIndex!==j){e.selectedIndex=j;e.dispatchEvent(new Event('change',{bubbles:true}));n++;}break;}}continue;}
if(e!==a&&String(e.value||'')!=='')continue;set(e,v);n++;}
try{if(a&&a.focus&&a!==d.body)a.focus();}catch(x){}
return String(n);}catch(x){return '-1';}})()JS" + values + ")";
    auto src = adoptWK(WKStringCreateWithUTF8CString(js.c_str()));
    WKPageEvaluateJavaScriptInMainFrame(t->page, src.get(), const_cast<void*>(static_cast<const void*>(t)), [](WKTypeRef result, WKErrorRef error, void* context) {
        if (!omniTabAlive(context)) return;
        const int n = atoi(omniFxResultString(result, error).c_str());
        notice(n > 0 ? "Filled " + std::to_string(n) + (n == 1 ? " field" : " fields") : std::string("No matching empty fields to fill"));
        if (editing && omniKb.kind == 1 && context == active()) omniKbProbe();
    });
}

// --- Autofill profile panel (Browser settings > Autofill) ------------------------------------------
static int omniAfEditField = -1;
static std::string omniAfEditValue;
static void omniAfPanelBuild(OmniFxPanel& p)
{
    omniAfLoad();
    { OmniFxRow r; r.id = 1; r.label = "Offer to fill forms"; r.value = omniAf.offer ? "On" : "Off"; r.stepper = true; p.rows.push_back(r); }
    for (int i = 0; i < omniAfCount; ++i) {
        OmniFxRow r; r.id = 100 + i; r.label = omniAfFields[i].label;
        auto it = omniAf.v.find(omniAfFields[i].key);
        r.value = it == omniAf.v.end() || it->second.empty() ? std::string("Not set") : it->second;
        p.rows.push_back(r);
    }
    if (!omniAfEmpty()) { OmniFxRow r; r.id = 2; r.label = "Clear the profile"; r.danger = true; p.rows.push_back(r); }
}
static bool omniAfPanelInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    const bool a = b == SDL_CONTROLLER_BUTTON_A, side = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT || b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT;
    if (r.id == 1) { if (!a && !side) return false; omniAf.offer = !omniAf.offer; omniAfSave(); return true; }
    if (r.id == 2 && a) { omniAf.v.clear(); omniAfSave(); notice("Autofill profile cleared"); return true; }
    if (r.id >= 100 && a) {
        const int i = r.id - 100;
        omniAfEditField = i;
        auto it = omniAf.v.find(omniAfFields[i].key);
        omniAfEditValue = it == omniAf.v.end() ? std::string() : it->second;
        omniKbEdit(&omniAfEditValue, omniAfFields[i].label, [](bool ok) {
            if (ok && omniAfEditField >= 0) { omniAf.v[omniAfFields[omniAfEditField].key] = omniAfEditValue; omniAfSave(); omniFxRefresh(); }
        });
        return true;
    }
    return false;
}
static void omniAfPanelShow()
{
    OmniFxPanel p;
    p.kind = omniAfKindPanel; p.w = 800; p.maxVisible = 10;
    p.title = "Autofill"; p.subtitle = "One profile, stored in plain text on this console";
    p.build = omniAfPanelBuild; p.input = omniAfPanelInput;
    p.faces = { { 0, "Edit" }, { 1, "Back" } };
    p.extra = "Fill a form from the page's quick menu or Site settings";
    omniFxPush(std::move(p));
}
