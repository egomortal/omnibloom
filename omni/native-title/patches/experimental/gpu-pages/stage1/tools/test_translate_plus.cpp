// OMNI_TRANSLATE_PLUS_V1: host tests for engine/entry/OmniTranslatePlus.h (written by apply_translate_plus.py).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_translate_plus.cpp -o t && ./t
#include "OmniTranslatePlus.h"
#include <cstdio>

static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

using namespace OmniTranslatePlus;

static bool has(const std::string& s, const char* part) { return s.find(part) != std::string::npos; }

int main()
{
    // addresses
    CHECK(parseUrl("https://WWW.Example.JP./a?b#c").host == "www.example.jp");
    CHECK(parseUrl("https://www.example.jp/a?b#c").rest == "/a?b#c");
    CHECK(parseUrl("http://user:pw@example.com/").userinfo);
    CHECK(parseUrl("http://[2001:db8::1]:8080/").host == "2001:db8::1");
    CHECK(!parseUrl("omni://start").ok && !parseUrl("about:blank").ok && !parseUrl("file:///x").ok);

    // eligibility: what is never sent
    CHECK(eligibility("https://www.example.jp/news?id=1") == kOk);
    CHECK(eligibility("omni://bookmarks") == kNotWeb);
    CHECK(eligibility("https://user:secret@example.com/") == kCredentials);
    CHECK(eligibility("http://192.168.0.1/") == kLocal);
    CHECK(eligibility("http://[::1]/") == kLocal);
    CHECK(eligibility("http://router/") == kLocal);
    CHECK(eligibility("http://localhost:8080/") == kLocal);
    CHECK(eligibility("http://nas.local/") == kLocal);
    CHECK(eligibility("http://printer.home.arpa/") == kLocal);
    CHECK(eligibility("http://abc.onion/") == kLocal);
    CHECK(eligibility("https://www-example-jp.translate.goog/") == kAlreadyTranslated);
    CHECK(eligibility("https://translate.google.com/translate?u=x") == kAlreadyTranslated);
    CHECK(eligibility("https://example.localhost.com/") == kOk);   // only real suffixes count

    // translate.goog -> original
    CHECK(originalOf("https://www-example-jp.translate.goog/a/b?x=1&_x_tr_sl=auto&_x_tr_tl=en&_x_tr_hl=en&_x_tr_pto=wapp#top")
          == "https://www.example.jp/a/b?x=1#top");
    CHECK(originalOf("https://my--site-example-com.translate.goog/?_x_tr_sl=auto&_x_tr_tl=es") == "https://my-site.example.com/");
    CHECK(originalOf("https://old-example-org.translate.goog/p?_x_tr_sch=http&_x_tr_sl=auto") == "http://old.example.org/p");
    CHECK(originalOf("https://example-com.translate.goog") == "https://example.com/");
    CHECK(originalOf("https://www.example.com/") == "");
    CHECK(originalOf("https://-x.translate.goog/") == "");   // does not decode to a host
    CHECK(isTranslated("https://www-example-jp.translate.goog/") && !isTranslated("https://translate.goog/"));

    // site keys: www dropped, translated pages use the original's
    CHECK(siteKey("https://www.example.jp/x") == "example.jp");
    CHECK(siteKey("https://news.example.jp/x") == "news.example.jp");
    CHECK(siteKey("https://www-example-jp.translate.goog/x?_x_tr_tl=en") == "example.jp");
    CHECK(siteKey("http://192.168.0.1/") == "" && siteKey("omni://start") == "");
    CHECK(sameDocument("https://example.com", "https://example.com/#a"));
    CHECK(!sameDocument("https://example.com/a", "https://example.com/b"));
    CHECK(!sameDocument("", ""));

    // rules: subdomains covered, exact wins, Offer is not stored, list capped
    std::map<std::string, Rule> sites;
    CHECK(setSite(sites, "example.jp", kAlways));
    CHECK(setSite(sites, "news.example.jp", kNever));
    CHECK(siteRule(sites, "example.jp") == kAlways);
    CHECK(siteRule(sites, "shop.example.jp") == kAlways);
    CHECK(siteRule(sites, "news.example.jp") == kNever);
    CHECK(siteRule(sites, "a.news.example.jp") == kNever);
    CHECK(siteRule(sites, "example.com") == kOffer);
    CHECK(siteRule(sites, "jp") == kOffer);
    CHECK(setSite(sites, "news.example.jp", kOffer) && !sites.count("news.example.jp"));
    CHECK(!setSite(sites, "192.168.0.1", kAlways) && !setSite(sites, "bad host", kAlways) && !setSite(sites, "", kAlways));
    {
        std::map<std::string, Rule> full;
        for (size_t i = 0; i < kMaxSites; ++i) CHECK(setSite(full, "s" + std::to_string(i) + ".example.com", kNever));
        CHECK(!setSite(full, "one-more.example.com", kNever));
        CHECK(setSite(full, "s1.example.com", kAlways));   // changing an existing row still works
    }
    CHECK(cycle(kOffer, 1) == kAlways && cycle(kAlways, 1) == kNever && cycle(kNever, 1) == kOffer);
    CHECK(cycle(kOffer, -1) == kNever);

    // storage round trip; an older consent id is dropped (asked again)
    Store st;
    st.consent = kConsentId;
    setSite(st.sites, "example.jp", kAlways);
    setSite(st.sites, "example.de", kNever);
    const std::string text = serialize(st);
    CHECK(text == std::string("omni-translate\t1\nconsent\t") + kConsentId + "\nsite\texample.de\tnever\nsite\texample.jp\talways\n");
    const Store back = parse(text);
    CHECK(back.consent == kConsentId && back.sites.size() == 2 && back.sites.at("example.jp") == kAlways);
    CHECK(parse("consent\tgoogle-old\n").consent.empty());
    CHECK(parse("site\t192.168.0.1\talways\r\nsite\tok.example\tbogus\nsite\tfine.org\tnever\r\n").sites.size() == 1);
    CHECK(parse("").consent.empty() && parse("garbage\n\t\t\n").sites.empty());

    // languages
    CHECK(targetLang("en") == "en" && targetLang("es") == "es" && targetLang("pt") == "pt");
    CHECK(targetLang("zh") == "zh-CN" && targetLang("nb") == "no" && targetLang("") == "en" && targetLang("x1") == "en");
    CHECK(primary("pt_BR") == "pt" && primary("ZH-Hant") == "zh" && primary("") == "" && primary("english") == "");
    CHECK(foreign("ja", "en") && !foreign("en-GB", "en") && !foreign("es-MX", "es") && !foreign("", "en"));
    CHECK(!foreign("zh-TW", "zh-CN") && !foreign("nn", "no") && foreign("de", "es"));
    CHECK(targetName("zh-CN") == "Chinese" && targetName("es") == "Spanish" && targetName("xx") == "xx");

    // the translate address: target language for page and Google's toolbar, URL fully encoded
    CHECK(translateUrl("https://example.jp/a?b=1&c=2", "es")
          == "https://translate.google.com/translate?sl=auto&tl=es&hl=es&u=https%3A%2F%2Fexample.jp%2Fa%3Fb%3D1%26c%3D2");
    CHECK(encode("\xc3\xa9 ~") == "%C3%A9%20~");

    // the decision
    Input in;
    in.manual = true; in.eligible = true;
    CHECK(decide(in) == kAskConsent);                       // first use asks
    in.consent = true;
    CHECK(decide(in) == kTranslate);                        // then a press translates
    in.privateTab = true;
    CHECK(decide(in) == kAskConsent);                       // private: every time
    in = Input(); in.manual = true; in.translated = true;
    CHECK(decide(in) == kShowOriginal);
    in = Input(); in.manual = true; in.eligible = false;
    CHECK(decide(in) == kRefuse);
    in = Input(); in.manual = true; in.eligible = true; in.consent = true; in.rule = kNever;
    CHECK(decide(in) == kTranslate);                        // Never only stops offers, not a press
    // loads: nothing is sent without Always + the saved OK, never from a private tab
    in = Input(); in.eligible = true; in.foreign = true;
    CHECK(decide(in) == kOfferNotice);
    in.rule = kAlways;
    CHECK(decide(in) == kOfferNotice);                      // Always without consent: only offers
    in.consent = true;
    CHECK(decide(in) == kTranslate);
    in.privateTab = true;
    CHECK(decide(in) == kOfferNotice);
    in.privateTab = false; in.suppressed = true;
    CHECK(decide(in) == kNothing);                          // after Show original
    in.suppressed = false; in.rule = kNever;
    CHECK(decide(in) == kNothing);
    in.rule = kOffer; in.foreign = false;
    CHECK(decide(in) == kNothing);                          // already in the target language
    in.foreign = true; in.translated = true;
    CHECK(decide(in) == kNothing);
    in.translated = false; in.eligible = false;
    CHECK(decide(in) == kNothing);

    // texts name the service, what is sent, the target, and the private-tab rule
    const std::string body = askBody("www.example.jp", "es", false);
    CHECK(has(body, "Google Translate") && has(body, "full address of this page (www.example.jp)") && has(body, "into Spanish"));
    CHECK(has(body, "privacy policy") && has(body, "asks this once"));
    CHECK(has(askBody("x.jp", "en", true), "Private tab: Omni asks every time and remembers nothing."));
    CHECK(has(askTitle(), "Google Translate"));
    CHECK(refuseNotice(kNotWeb) == "This page can't be translated");
    CHECK(has(refuseNotice(kLocal), "own network") && has(refuseNotice(kCredentials), "sign-in"));
    CHECK(startNotice() == "Translating with Google Translate...");   // the string apply_ui_lang.py already translates
    CHECK(siteDetail("de") == "Google Translate, into German");
    CHECK(has(siteNotice("example.jp", kAlways, true, false), "offered only"));
    CHECK(has(siteNotice("example.jp", kNever, false, false), "no translate offers"));
    CHECK(has(siteNotice("example.jp", kAlways, false, true), "not saved"));

    std::printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "ok", checks, fails);
    return fails ? 1 : 0;
}
