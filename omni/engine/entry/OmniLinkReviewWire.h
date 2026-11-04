#pragma once
#include <wtf/JSONValues.h>
#include <wtf/URL.h>
#include "OmniLinkReviewGate.h"
#include <cstdint>
#include <set>
#include <string>

namespace OmniLinkReview {
using namespace WTF::StringLiterals;
inline std::string utf8(const WTF::String& value) { auto bytes = value.utf8(); return { reinterpret_cast<const char*>(bytes.data()), bytes.length() }; }
inline bool validHttp(const std::string& value) {
    if (value.empty() || value.size() > 8192) return false;
    const auto start = httpPrefixLength(value);
    if (!start) return false;
    auto end = value.find_first_of("/?#", start);
    if (value.substr(start, end == std::string::npos ? end : end - start).find('@') != std::string::npos) return false;
    for (unsigned char c : value) if (c <= 32 || c == 127 || c == '\\') return false;
    auto string = WTF::String::fromUTF8(value);
    if (string.isNull() || string.length() > 4096) return false;
    WTF::URL parsed { WTF::URL { }, string };
    return parsed.isValid() && parsed.protocolIsInHTTPFamily() && !parsed.host().isEmpty()
        && parsed.user().isEmpty() && parsed.password().isEmpty() && (!parsed.port() || *parsed.port() != 0);
}
inline std::size_t encodedSize(const std::string& value) {
    std::size_t count = 0;
    for (unsigned char c : value) count += ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.' || c == '~') ? 1 : 3;
    return count;
}
inline bool validateWire(const WTF::String& string, const std::string& source, std::uint64_t document, std::string& wire) {
    wire.clear();
    if (string.length() > 65536) return false;
    auto raw = utf8(string);
    if (raw.size() > 65536 || encodedSize(raw) > 16384) return false;
    auto value = JSON::Value::parseJSON(string);
    auto object = value ? value->asObject() : nullptr;
    if (!object || object->size() != 5 || object->getInteger("v"_s) != 1) return false;
    if (utf8(object->getString("p"_s)) != source || utf8(object->getString("g"_s)) != std::to_string(document)) return false;
    auto truncated = object->getValue("t"_s);
    if (!truncated || !truncated->asBoolean()) return false;
    auto rows = object->getArray("rows"_s);
    if (!rows || rows->length() > 8) return false;
    const std::set<std::string> kinds { "media-url", "manifest", "metadata-url", "source-page" };
    const std::set<int> scores { 25, 35, 45, 55, 60, 75, 90, 95 };
    const std::set<std::string> codes { "media-current", "media-source", "og-video", "anchor-media", "page-video", "media-blob", "iframe", "encrypted-media-page-fallback", "blob-is-not-a-network-file", "resource-timing", "iframe-media" };
    std::size_t urlBytes = 0;
    std::set<std::string> seenUrls;
    for (std::size_t i = 0; i < rows->length(); ++i) {
        auto row = rows->get(i)->asObject();
        if (!row || row->size() != 4) return false;
        auto url = utf8(row->getString("u"_s)); auto kind = utf8(row->getString("k"_s)); auto score = row->getInteger("s"_s);
        if (!validHttp(url) || !seenUrls.insert(url).second || !kinds.count(kind) || !score || !scores.count(*score)) return false;
        if (kind == "source-page" && url != source) return false;
        urlBytes += url.size(); if (urlBytes > 32768) return false;
        auto evidence = row->getArray("e"_s);
        if (!evidence || !evidence->length() || evidence->length() > 4) return false;
        std::set<std::string> seenEvidence;
        for (std::size_t j = 0; j < evidence->length(); ++j) {
            auto item = evidence->get(j);
            if (item->type() != JSON::Value::Type::String) return false;
            const auto code = utf8(item->asString());
            if (!codes.count(code) || !seenEvidence.insert(code).second) return false;
        }
    }
    wire = WTF::move(raw); return true;
}
}
