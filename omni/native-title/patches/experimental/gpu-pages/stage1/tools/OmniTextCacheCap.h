// OMNI_TEXT_CACHE_CAP_V1: byte budget + LRU for the shell's rendered-text cache (no SDL, no WebKit).
// omniTextSurface() (OmniBrowser.cpp) keeps SDL_ttf surfaces of UI strings; it was capped at 256 entries only
// (first-in first-out), which at 4K (displayScale 3, 66 px body text, wide labels) could reach ~81 MB.
// Now: entries are dropped least-recently-used first while the bytes exceed the budget or the count exceeds the
// entry cap (both kept). The budget follows the output size: 48 MiB at 3840x2160, scaled by pixel count, 16 MiB min.
// The newest entry is never dropped by its own insert (the caller blits it right away), so one string larger than
// the whole budget stays cached alone until the next insert. The reasons are in tools/apply_text_cache_cap.py;
// tested on the host with g++ (tools/test_text_cache_cap.cpp).
#pragma once
#include <cstddef>
#include <cstdint>
#include <list>
#include <string>
#include <unordered_map>
#include <utility>

namespace OmniTextCacheCap {

constexpr size_t kMiB = size_t(1) << 20;
constexpr size_t kBudget4K = 48 * kMiB, kBudgetMin = 16 * kMiB;
constexpr size_t kMaxEntries = 256;   // the old cap, kept

// 48 MiB x (w*h)/(3840*2160), at least 16 MiB (0 / negative sizes: the minimum).
inline size_t budgetFor(int renderWidth, int renderHeight)
{
    if (renderWidth <= 0 || renderHeight <= 0) return kBudgetMin;
    const unsigned long long px = (unsigned long long)renderWidth * (unsigned long long)renderHeight;
    const unsigned long long b = (unsigned long long)kBudget4K * px / (3840ull * 2160ull);
    return b < kBudgetMin ? kBudgetMin : size_t(b);
}
// Bytes a surface holds: its rows (pitch >= w * 4 for 32-bit text surfaces); w*h*4 when pitch is unknown.
inline size_t surfaceBytes(int w, int h, int pitch = 0)
{
    if (w <= 0 || h <= 0) return 0;
    const size_t row = pitch > 0 ? size_t(pitch) : size_t(w) * 4;
    return row * size_t(h);
}

struct Stats {
    size_t bytes = 0, entries = 0, peakBytes = 0, budget = kBudgetMin;
    unsigned long long hits = 0, misses = 0, evictions = 0;
};

// LRU keyed by string; V is a cheap handle (SDL_Surface* in the shell). `drop(V)` frees an evicted value.
template <class V>
class Lru {
public:
    explicit Lru(size_t budget = kBudgetMin, size_t maxEntries = kMaxEntries) : max_(maxEntries ? maxEntries : 1) { st_.budget = budget; }

    // A hit moves the entry to the front (most recent). nullptr on a miss.
    V* find(const std::string& key)
    {
        auto it = map_.find(key);
        if (it == map_.end()) { ++st_.misses; return nullptr; }
        ++st_.hits;
        if (it->second != order_.begin()) order_.splice(order_.begin(), order_, it->second);
        return &it->second->value;
    }
    bool contains(const std::string& key) const { return map_.count(key) != 0; }

    // Inserts (or replaces: the old value is dropped) as the most recent entry, then evicts the oldest others until
    // bytes <= budget and entries <= the entry cap. The new entry itself is never evicted here.
    template <class Drop>
    void put(const std::string& key, V value, size_t bytes, Drop&& drop)
    {
        if (auto it = map_.find(key); it != map_.end()) {
            Node& n = *it->second;
            st_.bytes -= n.bytes;
            drop(n.value);
            n.value = value; n.bytes = bytes;
            st_.bytes += bytes;
            order_.splice(order_.begin(), order_, it->second);
        } else {
            order_.push_front(Node { key, value, bytes });
            map_.emplace(key, order_.begin());
            st_.bytes += bytes;
        }
        trim(drop, 1);
        if (st_.bytes > st_.peakBytes) st_.peakBytes = st_.bytes;   // resident peak (after eviction)
    }
    // New budget (output size changed): evicts down to it at once (everything may go: no entry is "new" here).
    template <class Drop>
    void setBudget(size_t budget, Drop&& drop)
    {
        st_.budget = budget;
        trim(drop, 0);
    }
    template <class Drop>
    void clear(Drop&& drop)
    {
        for (Node& n : order_) drop(n.value);
        order_.clear(); map_.clear(); st_.bytes = 0;
    }
    const Stats& stats() const { st_.entries = map_.size(); return st_; }
    size_t budget() const { return st_.budget; }
    size_t bytes() const { return st_.bytes; }
    size_t size() const { return map_.size(); }
    // Key of the least recently used entry ("" when empty), for tests.
    std::string oldestKey() const { return order_.empty() ? std::string() : order_.back().key; }

private:
    struct Node { std::string key; V value; size_t bytes; };
    template <class Drop>
    void trim(Drop& drop, size_t keep)
    {
        while (order_.size() > keep && (st_.bytes > st_.budget || order_.size() > max_)) {
            Node& n = order_.back();
            st_.bytes -= n.bytes;
            drop(n.value);
            map_.erase(n.key);
            order_.pop_back();
            ++st_.evictions;
        }
    }
    std::list<Node> order_;   // front = most recent
    std::unordered_map<std::string, typename std::list<Node>::iterator> map_;
    size_t max_;
    mutable Stats st_;
};

} // namespace OmniTextCacheCap
namespace OTCC = OmniTextCacheCap;
