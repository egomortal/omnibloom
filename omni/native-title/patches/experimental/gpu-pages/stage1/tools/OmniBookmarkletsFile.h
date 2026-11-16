// OMNI_BOOKMARKLETS_V1: bookmarks.txt with bookmarklets (pure; needs OmniBookmarksModel.h and OmniBookmarklets.h).
// OMNI_BOOKMARKS_MANAGER_V1 reads the file the way the first loader did (fgets with a 2400-byte buffer: a longer line
// counts as several) and cuts addresses at 2048 bytes when it saves; a bookmarklet is often longer than that and a cut
// one is broken code. Here a line that starts with "javascript:" (any case) is read whole up to kScriptLineBuffer - 1
// bytes and saved with up to 64 KB of address; every other line is read, cut and written exactly as the model does
// (so a file without bookmarklets loads and saves byte-identically). Lines are handed to OmniBookmarksModel::parse
// one at a time, so columns, folders, titles and the 500 cap stay its rules.
#pragma once
#include "OmniBookmarksModel.h"
#include "OmniBookmarklets.h"
#include <string>
#include <vector>

namespace OmniBookmarkletsFile {

namespace M = OmniBookmarksModel;
constexpr std::size_t kScriptLineBuffer = OmniBookmarklets::kMaxBytes + 1 + M::kTitleMax + 1 + M::kFolderMax + 1 + 56;

inline bool scriptAt(const std::string& s, std::size_t at)   // "javascript:" in any case at `at` (no trimming)
{
    static const char* p = "javascript:";
    for (std::size_t k = 0; p[k]; ++k)
        if (at + k >= s.size() || OmniBookmarklets::lowerAscii(s[at + k]) != p[k]) return false;
    return true;
}
inline std::vector<M::Entry> parse(const std::string& data, std::size_t max = M::kMax)
{
    std::vector<M::Entry> out;
    const std::size_t n = data.size();
    std::size_t i = 0;
    while (i < n && out.size() < max) {
        const std::size_t room = scriptAt(data, i) ? kScriptLineBuffer - 1 : M::kLineBuffer - 1;
        const std::size_t nl = data.find('\n', i);
        const std::size_t stop = nl != std::string::npos && nl < i + room ? nl + 1 : std::min(i + room, n);
        std::string piece = data.substr(i, stop - i);
        i = stop;
        if (!scriptAt(piece, 0)) {   // at most 2399 bytes: the model reads it as one line, by its own rules
            for (auto& e : M::parse(piece, 1)) out.push_back(std::move(e));
            continue;
        }
        // the model's column rules, for a line longer than its buffer (M::parse would split it again)
        const std::size_t nul = piece.find('\0');
        if (nul != std::string::npos) piece.resize(nul);
        while (!piece.empty() && (piece.back() == '\n' || piece.back() == '\r')) piece.pop_back();
        const std::size_t t1 = piece.find('\t');
        M::Entry e;
        e.url = piece.substr(0, t1);
        if (t1 != std::string::npos) {
            const std::size_t t2 = piece.find('\t', t1 + 1);
            e.title = piece.substr(t1 + 1, t2 == std::string::npos ? std::string::npos : t2 - t1 - 1);
            if (t2 != std::string::npos) {
                const std::size_t t3 = piece.find('\t', t2 + 1);
                e.folder = M::cleanFolder(piece.substr(t2 + 1, t3 == std::string::npos ? std::string::npos : t3 - t2 - 1));
            }
        }
        if (e.title.empty()) e.title = e.url;
        out.push_back(std::move(e));
    }
    return out;
}
inline std::string serializeLine(const M::Entry& e)
{
    if (!scriptAt(e.url, 0)) return M::serializeLine(e);
    M::Entry cut = e;
    cut.url.clear();   // the model writes the rest; the address goes in front with the larger limit
    const std::string rest = M::serializeLine(cut);
    return M::oneLine(e.url, OmniBookmarklets::kMaxBytes) + rest;
}
inline std::string serialize(const std::vector<M::Entry>& list)
{
    std::string s;
    for (const auto& e : list) s += OmniBookmarkletsFile::serializeLine(e);   // qualified: ADL also finds M::serializeLine
    return s;
}

} // namespace OmniBookmarkletsFile
