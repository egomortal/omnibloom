// OMNI_YT_ATTEST_LOG_V1 PC test: g++ -std=c++17 -I <tree>/engine/entry test_yt_attest_log.cpp && ./a.out
#include "OmniYtAttestLog.h"
#include <cassert>
#include <iostream>
#include <vector>

using namespace OmniYtAttestLog;
static int fails = 0;
#define CHECK(c) do { if (!(c)) { ++fails; std::cerr << "FAIL line " << __LINE__ << ": " #c "\n"; } } while (0)

int main()
{
    Url u = split("https://WWW.YouTube.com:443/watch?v=abcdEFGhijk&t=3#x");
    CHECK(u.ok && u.host == "www.youtube.com" && u.path == "/watch" && u.query == "v=abcdEFGhijk&t=3");
    CHECK(classify(u) == Kind::Page);
    CHECK(classify(split("https://www.youtube.com/watch?v=x&pbj=1")) == Kind::None);
    CHECK(classify(split("https://www.youtube.com/tv#/watch?v=x")) == Kind::Page);
    CHECK(classify(split("https://jnn-pa.googleapis.com/$rpc/google.internal.waa.v1.Waa/GenerateIT")) == Kind::GenerateIT);
    CHECK(classify(split("https://jnn-pa.googleapis.com/$rpc/google.internal.waa.v1.Waa/Create")) == Kind::Create);
    CHECK(classify(split("https://www.youtube.com/api/jnn/v1/GenerateIT")) == Kind::GenerateIT);
    CHECK(classify(split("https://www.youtube.com/youtubei/v1/att/get?prettyPrint=false")) == Kind::AttGet);
    CHECK(classify(split("https://www.youtube.com/youtubei/v1/player?key=z")) == Kind::Player);
    CHECK(classify(split("https://rr3---sn-abc.googlevideo.com/videoplayback?sabr=1")) == Kind::Videoplayback);
    CHECK(classify(split("https://i.ytimg.com/vi/x/hq.jpg")) == Kind::None);
    CHECK(classify(split("about:blank")) == Kind::None);
    bool f = false;
    CHECK(param("a=1&sps=3&pot=XYZ", "sps", f) == "3" && f);
    CHECK(param("a=1&spsx=3", "sps", f).empty() && !f);
    CHECK(param("sabr", "sabr", f).empty() && f);
    CHECK(smallInt("2") == "2" && smallInt("abcd") == "?" && smallInt("") == "?");

    std::vector<std::string> lines;
    Logger L([&](const char* s) { lines.emplace_back(s); });
    const std::string page = "https://www.youtube.com/watch?v=SECRETVID01";
    const std::string git = "https://jnn-pa.googleapis.com/$rpc/google.internal.waa.v1.Waa/GenerateIT";
    const std::string vp = "https://rr1---sn-q4fl6n6s.googlevideo.com/videoplayback?expire=1&id=o-SECRETID&sps=2&pot=MnTOKENTOKENTOKEN&sabr=1";
    L.onRequest(1000, "https://i.ytimg.com/x.jpg", "GET", 0);          // ignored
    L.onRequest(1000, page, "GET", 3);
    L.onRequest(4200, git, "POST", 3);
    L.onResponse(4500, git, 200, 1830, "application/json+protobuf");
    L.onComplete(4510, git, 0, 1830);
    L.onRequest(5000, vp, "POST", 3);
    L.onResponse(5100, vp, 200, -1, "application/vnd.yt-ump");
    L.onComplete(5200, vp, 0, -1);
    L.onRedirect(5300, vp, 302, "https://rr2---sn-zz.googlevideo.com/videoplayback?sps=3&id=SECRET2");
    L.onRequest(9000, "https://www.youtube.com/watch?v=OTHER", "GET", 4); // next page -> summary of page 1
    std::string all; for (auto& l : lines) all += l + "\n";
    std::cout << all;
    CHECK(lines.size() == 9 && lines[8] == "page n=2 run=4 host=www.youtube.com path=/watch");
    CHECK(lines[0] == "page n=1 run=3 host=www.youtube.com path=/watch");
    CHECK(lines[1].find("req kind=GenerateIT") == 0 && lines[1].find("t=3200") != std::string::npos && lines[1].find("first=1") != std::string::npos);
    CHECK(lines[2].find("resp kind=GenerateIT status=200 len=1830") == 0 && lines[2].find("dt=300") != std::string::npos);
    CHECK(lines[3].find("done kind=GenerateIT err=0") == 0);
    CHECK(lines[4].find("vp req i=1 method=POST sabr=1 sps=2 pot_len=17") == 0);
    CHECK(lines[5].find("vp resp i=1 status=200 len=-1") == 0);
    CHECK(lines[6].find("redir kind=videoplayback status=302 to=*.googlevideo.com/videoplayback sps=3") == 0);
    CHECK(lines[7].find("pagesum n=1 run=3 git_req=1 git_resp=1 git_err=0 git_first_ms=3200 git_resp_ms=3500 git_status=200 git_len=1830 vp_req=1 vp_resp=1") == 0);
    CHECK(lines[7].find("sps=3") != std::string::npos);
    // privacy: no video ids, no token text, no googlevideo node names
    CHECK(all.find("SECRET") == std::string::npos && all.find("TOKEN") == std::string::npos && all.find("sn-q4") == std::string::npos);
    // videoplayback line cap
    lines.clear();
    for (int i = 0; i < 200; ++i) { L.onRequest(10000 + i, vp + "&n=" + std::to_string(i), "POST", 4); L.onResponse(10001 + i, vp + "&n=" + std::to_string(i), 200, 100, "x"); }
    size_t vpLines = 0, sums = 0; for (auto& l : lines) { if (l.rfind("vp ", 0) == 0) ++vpLines; if (l.rfind("pagesum", 0) == 0) ++sums; }
    CHECK(vpLines == Logger::vpLineCap);
    CHECK(sums == 3); // every 64 responses
    std::cout << (fails ? "FAILED " : "OK ") << fails << "\n";
    return fails ? 1 : 0;
}
