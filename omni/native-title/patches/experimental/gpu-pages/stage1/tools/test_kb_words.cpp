// OMNI_KB_WORDS_V1 host test: g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_kb_words.cpp -o t && ./t [kb_words_en.txt]
// Checks the pure header and the generated table: the fragment at the caret, finished words, address search text,
// case of the typed prefix, the completion text, the front-coded built-in list (decode, order, encode round trip, the
// same bytes apply_kb_words.py generated from kb_words_en.txt), prefix search and ranking with learned words, and
// kb-words.txt parse / serialize / 2000-word cap / eviction / bad lines.
#include "OmniKbWords.h"
#include "OmniKbWordsData.h"
#include <chrono>
#include <cstdio>
#include <fstream>
#include <string>
#include <vector>

namespace W = OmniKbWords;
static int failures = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); } } while (0)

static std::vector<std::string> S(std::initializer_list<const char*> l) { std::vector<std::string> v; for (auto p : l) v.push_back(p); return v; }

int main(int argc, char** argv)
{
    // fragment ---------------------------------------------------------------------------------------------------
    CHECK(W::fragment("hello wor", "") == "wor");
    CHECK(W::fragment("Hel", "") == "Hel");
    CHECK(W::fragment("hello wor", "ld") == "");          // caret inside a word
    CHECK(W::fragment("hello wor", " next") == "wor");
    CHECK(W::fragment("hello wor", ",") == "wor");
    CHECK(W::fragment("hello ", "") == "");
    CHECK(W::fragment("", "") == "");
    CHECK(W::fragment("abc123", "") == "");
    CHECK(W::fragment("x2abc", "") == "");                // touches a digit
    CHECK(W::fragment("me@exam", "") == "");              // e-mail
    CHECK(W::fragment("www.goo", "") == "");              // address
    CHECK(W::fragment("caf\xc3\xa9" "abc", "") == "");    // touches non-ASCII
    CHECK(W::fragment("I don'", "") == "don'");
    CHECK(W::fragment("say 'hel", "") == "hel");           // a leading quote is punctuation
    CHECK(W::fragment("say '", "") == "");
    CHECK(W::fragment("(hel", "") == "hel");
    CHECK(W::fragment("hel", "2") == "");
    CHECK(W::fragment(std::string(25, 'a'), "") == "");   // too long
    CHECK(W::fragment(std::string(24, 'a'), "") == std::string(24, 'a'));
    // finishedWord -----------------------------------------------------------------------------------------------
    CHECK(W::finishedWord("hello world ") == "world");
    CHECK(W::finishedWord("hello world, ") == "world");
    CHECK(W::finishedWord("Done.") == "Done");
    CHECK(W::finishedWord("hello world") == "");          // not finished yet
    CHECK(W::finishedWord("hello    ") == "");            // too many separators: not just typed
    CHECK(W::finishedWord("x2y ") == "");
    CHECK(W::finishedWord(" ") == "");
    // isSearchText -----------------------------------------------------------------------------------------------
    CHECK(W::isSearchText("best pizza"));
    CHECK(W::isSearchText("weather"));
    CHECK(!W::isSearchText("example.com"));
    CHECK(!W::isSearchText("https://example.com/a b"));
    CHECK(!W::isSearchText("localhost:8080"));
    CHECK(!W::isSearchText("   "));
    CHECK(W::isSearchText("what is example.com"));        // a space: Omni searches it
    // caseLike / completion --------------------------------------------------------------------------------------
    CHECK(W::caseLike("hello", "Hel") == "Hello");
    CHECK(W::caseLike("hello", "hel") == "hello");
    CHECK(W::caseLike("hello", "HEL") == "HELLO");
    CHECK(W::caseLike("hello", "H") == "Hello");          // one capital: a sentence start, not caps
    CHECK(W::caseLike("don't", "DON") == "DON'T");
    CHECK(W::completion("Hello", "Hel", "") == "lo ");
    CHECK(W::completion("Hello", "Hel", " there") == "lo");
    CHECK(W::completion("Hello", "Hel", ".") == "lo");
    CHECK(W::completion("Hello", "Hel", "x") == "lo ");
    CHECK(W::completion("He", "He", "") == "");
    // login fields (never learned from) ----------------------------------------------------------------------------
    CHECK(!W::isLoginField("", "q", "search", "search", false));
    CHECK(!W::isLoginField("off", "comment", "", "text", false));
    CHECK(W::isLoginField("", "q", "", "text", true));                 // a password field in the same form
    CHECK(W::isLoginField("username", "", "", "text", false));
    CHECK(W::isLoginField("section-a shipping Email", "", "", "text", false));
    CHECK(W::isLoginField("one-time-code", "", "", "text", false));
    CHECK(W::isLoginField("cc-number", "", "", "text", false) && W::isLoginField("cc-name", "", "", "text", false));
    CHECK(W::isLoginField("tel-national", "", "", "text", false) && W::isLoginField("billing address-line1", "", "", "text", false));
    CHECK(W::isLoginField("street-address", "", "", "text", false) && W::isLoginField("postal-code", "", "", "text", false));
    CHECK(!W::isLoginField("name", "fullname", "", "text", false) && !W::isLoginField("on", "", "", "text", false));
    CHECK(W::isLoginField("", "UserName", "", "text", false) && W::isLoginField("", "", "loginBox", "text", false));
    CHECK(W::isLoginField("", "", "account-id", "text", false) && W::isLoginField("", "otp", "", "text", false));
    CHECK(W::isLoginField("", "verify_code", "", "text", false) && W::isLoginField("", "", "cardholder", "text", false));
    CHECK(W::isLoginField("", "e", "", "EMAIL", false) && W::isLoginField("", "", "", "tel", false));
    {
        const char U = '\x1f';
        auto probe = [U](const char* ac, const char* name, const char* id, const char* type, const char* pw, const char* tag) {
            return std::string("ok") + U + ac + U + name + U + id + U + type + U + pw + U + tag; };
        CHECK(!W::fieldProbeSaysLogin(probe("", "q", "", "search", "0", "INPUT")));
        CHECK(!W::fieldProbeSaysLogin(probe("", "", "editor", "", "0", "DIV")));          // contenteditable
        CHECK(W::fieldProbeSaysLogin(probe("", "q", "", "text", "1", "INPUT")));
        CHECK(W::fieldProbeSaysLogin(probe("username", "q", "", "text", "0", "INPUT")));
        CHECK(W::fieldProbeSaysLogin(probe("", "", "", "", "0", "IFRAME")));            // a cross-origin frame
        CHECK(W::fieldProbeSaysLogin(probe("", "q", "", "text", "0", "")));
        CHECK(W::fieldProbeSaysLogin("") && W::fieldProbeSaysLogin("none") && W::fieldProbeSaysLogin("ok"));
        CHECK(W::fieldProbeSaysLogin(probe("", "q", "", "text", "0", "INPUT") + U));   // a stray separator
        CHECK(W::fieldProbeSaysLogin("no" + probe("", "q", "", "text", "0", "INPUT").substr(2)));
    }
    // clean ------------------------------------------------------------------------------------------------------
    std::string c;
    CHECK(W::clean("Hello", c) && c == "hello");
    CHECK(W::clean("don't", c) && c == "don't");
    CHECK(!W::clean("a", c) && !W::clean("'a'", c) && !W::clean("ab1", c) && !W::clean("it''s", c) && !W::clean("x'", c));
    CHECK(!W::clean(std::string(25, 'a'), c) && W::clean(std::string(24, 'a'), c));
    CHECK(!W::clean("caf\xc3\xa9", c));
    // encode / decode --------------------------------------------------------------------------------------------
    {
        const auto words = S({ "the", "then", "there", "thereafter", "theatre", "a'b", "zoo", "apple", "app" });
        const std::string data = W::encode(words);
        W::Dict d;
        CHECK(d.decode(data.c_str()));
        CHECK(d.size() == words.size());
        for (size_t i = 1; i < d.size(); ++i) CHECK(d.word(i - 1) < d.word(i));
        for (size_t r = 0; r < words.size(); ++r) {
            const size_t i = d.lowerBound(words[r]);
            CHECK(i < d.size() && d.word(i) == words[r] && d.rank[i] == r);
        }
        CHECK(d.contains("thereafter") && !d.contains("ther") && !d.contains("zzz"));
        W::Dict bad;
        CHECK(!bad.decode("0abcAA") && !bad.decode("5abcAAA") && !bad.decode("x") && !bad.decode(""));
        CHECK(!bad.decode("0bAAA0aAAB"));                  // out of order
        // the shared-prefix digit stops at 9
        const std::string longData = W::encode(S({ "internationalisation", "internationalization" }));
        CHECK(longData.find("9") != std::string::npos && d.decode(longData.c_str()) && d.word(1) == "internationalization");
    }
    // the generated table ----------------------------------------------------------------------------------------
    W::Dict dict;
    CHECK(dict.decode(W::builtinData));
    CHECK(dict.size() >= 5000 && dict.size() <= 10000);
    for (size_t i = 1; i < dict.size(); ++i) if (!(dict.word(i - 1) < dict.word(i))) { CHECK(false); break; }
    {
        const size_t the = dict.lowerBound("the");
        CHECK(the < dict.size() && dict.word(the) == "the" && dict.rank[the] == 0);
        CHECK(dict.contains("hello") && dict.contains("thanks") && dict.contains("weather") && dict.contains("don't"));
        CHECK(!dict.contains("astra") && !dict.contains("claude"));   // removed from the list (2026-11-16)
        if (argc > 1) {   // apply_kb_words.py's bytes == this encoder over the same list
            std::ifstream f(argv[1]);
            std::vector<std::string> words;
            for (std::string w; std::getline(f, w);) { if (!w.empty() && w.back() == '\r') w.pop_back(); if (!w.empty()) words.push_back(w); }
            CHECK(!words.empty() && W::encode(words) == W::builtinData);
            for (size_t r = 0; r < words.size() && r < 50; ++r) { const size_t i = dict.lowerBound(words[r]); CHECK(i < dict.size() && dict.rank[i] == r); }
        }
    }
    // suggest ----------------------------------------------------------------------------------------------------
    {
        W::Dict d;
        d.decode(W::encode(S({ "the", "they", "there", "then", "them", "their", "thank", "thanks", "thing", "think" })).c_str());
        auto s = W::suggest(&d, nullptr, "th");
        CHECK(s == S({ "the", "they", "there" }));
        s = W::suggest(&d, nullptr, "The");
        CHECK(s == S({ "They", "There", "Then" }));       // the typed word itself is not offered
        s = W::suggest(&d, nullptr, "THA");
        CHECK(s == S({ "THANK", "THANKS" }));
        CHECK(W::suggest(&d, nullptr, "xyz").empty() && W::suggest(&d, nullptr, "").empty() && W::suggest(nullptr, nullptr, "th").empty());
        W::Learned l;
        l.add("thermostat");
        s = W::suggest(&d, &l, "th");
        CHECK(s.size() == 3 && s[0] == "the" && s[1] == "they");   // typed once: below the most common words...
        s = W::suggest(&d, &l, "the");
        CHECK(s.size() == 3 && s[0] == "they");
        l.add("thermostat");
        s = W::suggest(&d, &l, "th");
        CHECK(s.size() == 3 && s[0] == "thermostat");             // ...typed twice: first
        l.add("think"); l.add("think"); l.add("think");
        s = W::suggest(&d, &l, "th");
        CHECK(s[0] == "think" && s[1] == "thermostat");           // learned and built-in: both scores count
        s = W::suggest(&d, &l, "thi", 2);
        CHECK(s == S({ "think", "thing" }));
        // a word typed once beats a rare built-in word
        W::Dict big;
        std::vector<std::string> many;
        for (int i = 0; i < 300; ++i) { std::string w = "w"; w += char('a' + i / 26 % 26); w += char('a' + i % 26); many.push_back(w); }
        many.push_back("zebra");
        big.decode(W::encode(many).c_str());
        W::Learned once;
        once.add("zeppelin");
        CHECK(W::suggest(&big, &once, "ze") == S({ "zeppelin", "zebra" }));
        // cost: a one-letter prefix over the full table stays cheap (no per-frame use; this is per text change)
        W::Learned full;
        for (int i = 0; i < 2000; ++i) { std::string w = "s"; for (int k = i; k; k /= 26) w += char('a' + k % 26); w += "x"; full.add(w); }
        const auto t0 = std::chrono::steady_clock::now();
        for (int i = 0; i < 100; ++i) (void)W::suggest(&dict, &full, "s");
        const double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count() / 100;
        printf("suggest(\"s\") over %zu built-in + 2000 learned words: %.3f ms\n", dict.size(), ms);
        CHECK(ms < 5);
        const auto r = W::suggest(&dict, nullptr, "hel");
        CHECK(!r.empty());
        printf("hel -> %s %s %s | wea -> %s | tha -> %s\n", r.size() > 0 ? r[0].c_str() : "-", r.size() > 1 ? r[1].c_str() : "-",
            r.size() > 2 ? r[2].c_str() : "-", W::suggest(&dict, nullptr, "wea")[0].c_str(), W::suggest(&dict, nullptr, "tha")[0].c_str());
    }
    // learned: add / cap / eviction / parse / serialize --------------------------------------------------------------
    {
        W::Learned l;
        CHECK(l.add("Hello") && l.add("hello") && !l.add("a") && !l.add("x1") && !l.add("p@ss"));
        CHECK(l.words.size() == 1 && l.words[0].word == "hello" && l.words[0].count == 2 && l.clock == 2);
        const std::string text = l.serialize();
        CHECK(text == "omni-kb-words\t1\nhello\t2\t2\n");
        W::Learned back;
        back.parse(text);
        CHECK(back.words.size() == 1 && back.words[0].word == "hello" && back.words[0].count == 2 && back.clock == 2);
        back.parse("omni-kb-words\t1\r\nGood\t3\t9\r\nbad line\nx1\t4\t1\nneg\t-2\t1\nzero\t0\t1\ngood\t1\t4\nnostamp\t5\n\tempty\t1\n");
        CHECK(back.words.size() == 2 && back.words[0].word == "good" && back.words[0].count == 4 && back.words[0].stamp == 9);
        CHECK(back.words[1].word == "nostamp" && back.words[1].count == 5 && back.clock == 9);
        back.parse("");
        CHECK(back.words.empty() && back.clock == 0);
        // the cap: the least used, then the oldest, goes; the new word stays
        W::Learned cap;
        auto name = [](int i) { std::string w = "w"; for (int k = i; ; k /= 26) { w += char('a' + k % 26); if (k < 26) break; } return w; };
        for (int i = 0; i < 2000; ++i) cap.add(name(i));
        for (int i = 0; i < 2000; ++i) if (i != 5) cap.add(name(i));   // every word twice except w5's
        CHECK(cap.words.size() == 2000);
        cap.add("newword");
        CHECK(cap.words.size() == 2000 && cap.find("newword") && !cap.find(name(5)));
        cap.add("another");                                // now "newword" (1 use, older) goes
        CHECK(cap.words.size() == 2000 && cap.find("another") && !cap.find("newword"));
        // parse caps too, keeping the most used
        std::string big = "omni-kb-words\t1\n";
        for (int i = 0; i < 2100; ++i) big += name(i) + "\t" + std::to_string(i < 100 ? 1 : 3) + "\t" + std::to_string(i) + "\n";
        W::Learned p;
        p.parse(big);
        CHECK(p.words.size() == 2000 && !p.find(name(0)) && !p.find(name(99)) && p.find(name(100)) && p.find(name(2099)));
        W::Learned rt;
        rt.parse(p.serialize());
        CHECK(rt.serialize() == p.serialize());
    }
    printf("%s: %d checks, %d failed\n", failures ? "FAIL" : "PASS", checks, failures);
    return failures ? 1 : 0;
}
