// OMNI_FEATURES_V2: small shared helpers for the second-round features.
#pragma once
static std::string omniF2OriginOf(const std::string& url)   // scheme://host[:port], host lowercased, www. dropped
{
    const size_t s = url.find("://");
    if (s == std::string::npos) return {};
    const std::string scheme = omniLower(url.substr(0, s));
    if (scheme != "http" && scheme != "https") return {};
    std::string host = omniBlockerHostOf(url);
    if (host.empty()) return {};
    size_t begin = s + 3, end = url.find_first_of("/?#", begin), port = 0;
    std::string authority = url.substr(begin, end == std::string::npos ? std::string::npos : end - begin);
    if (auto at = authority.rfind('@'); at != std::string::npos) authority = authority.substr(at + 1);
    if (auto colon = authority.find(':'); colon != std::string::npos) port = size_t(atoi(authority.c_str() + colon + 1));
    std::string origin = scheme + "://" + host;
    if (port && !((scheme == "http" && port == 80) || (scheme == "https" && port == 443))) origin += ":" + std::to_string(port);
    return origin;
}
static std::string omniF2Json(const std::string& s)   // a JSON string literal (for building fill scripts)
{
    std::string o = "\"";
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') { o += '\\'; o += char(c); }
        else if (c == '\n') o += "\\n"; else if (c == '\r') o += "\\r"; else if (c == '\t') o += "\\t";
        else if (c < 0x20) { char b[8]; snprintf(b, sizeof(b), "\\u%04x", c); o += b; }
        else if (c == '<') o += "\\u003c"; else if (c == '>') o += "\\u003e"; else if (c == '&') o += "\\u0026";
        else o += char(c);
    }
    return o + "\"";
}
