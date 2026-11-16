// OMNI_KB_SHOWPW_V1: "Show password while typing", the pure part (no SDL, no WebKit). Reasons: tools/apply_kb_showpw.py.
// One Guard per keyboard session and field. It holds counts only, never text: the field's length as last read, how
// many code points the keyboard typed into it since it was last seen empty, whether it is "clean" (everything in it
// was typed here), and whether the user asked to see it.
//   - A field is shown only while it is clean: it was seen empty in this keyboard session (a field that already held
//     text when the keyboard opened, e.g. a saved login filled earlier or a saved password being edited, never is),
//     and since then it never held more code points than the keyboard typed (a page script or anything else filling
//     it hides it).
//   - A saved login filled into the page, or Undo (it may bring back text from before), hides it: taint().
//   - Hidden again when the keyboard closes or the field changes (a new session / field resets the guard).
#pragma once
#include <cstddef>
#include <string>
#include <string_view>

namespace OmniKbShowPw {

constexpr int kKbKey = 7571;   // the keyboard's Show / Hide key (edit row, password fields, in place of Copy)

inline size_t cpCount(std::string_view s)
{
    size_t n = 0;
    for (unsigned char c : s) if ((c & 0xC0) != 0x80) ++n;
    return n;
}

enum class Toggle { Shown, Hidden, Refused, Pending };

class Guard {
public:
    // A new keyboard session or field: everything forgotten, hidden.
    void reset(int session, int field)
    {
        session_ = session; field_ = field;
        known_ = clean_ = wanted_ = false;
        typed_ = 0;
    }
    bool same(int session, int field) const { return session_ == session && field_ == field; }
    // The field's length in code points, as read now (the webpage mirror or the dialog's own text).
    void observe(size_t cps)
    {
        if (cps == 0) { known_ = clean_ = true; typed_ = 0; return; }   // empty: what comes next is typed here
        if (!known_) { known_ = true; drop(); return; }                // it held text before this session
        if (cps > typed_) drop();                                       // more than the keyboard typed
    }
    // The keyboard inserted this many code points (keys, Space, Paste).
    void typed(size_t cps) { typed_ = typed_ + cps < typed_ ? typed_ : typed_ + cps; }
    // A saved login was filled, or Undo: hidden until the field is seen empty again.
    void taint() { drop(); }
    Toggle toggle()
    {
        if (wanted_) { wanted_ = false; return Toggle::Hidden; }
        if (!known_) return Toggle::Pending;
        if (!clean_) return Toggle::Refused;
        wanted_ = true;
        return Toggle::Shown;
    }
    bool reveal() const { return wanted_ && known_ && clean_; }
    bool clean() const { return known_ && clean_; }
    size_t typedCount() const { return typed_; }

private:
    void drop() { clean_ = false; wanted_ = false; }
    int session_ = -1, field_ = -1;
    bool known_ = false, clean_ = false, wanted_ = false;
    size_t typed_ = 0;
};

inline const char* keyLabel(bool shown) { return shown ? "Hide" : "Show"; }

// The preview row's field name while the text is shown: "Password" -> "Password (shown)",
// "Password (hidden)" -> "Password (shown)".
inline std::string shownLabel(std::string_view label)
{
    constexpr std::string_view hidden = " (hidden)";
    if (label.size() >= hidden.size() && label.substr(label.size() - hidden.size()) == hidden) label.remove_suffix(hidden.size());
    if (label.empty()) label = "Password";
    return std::string(label) + " (shown)";
}

inline const char* toggleNotice(Toggle t)
{
    switch (t) {
    case Toggle::Shown: return "Password shown in this field until the keyboard closes";
    case Toggle::Hidden: return "Password hidden";
    case Toggle::Pending: return "One moment: the field is still being read";
    case Toggle::Refused: return "Only text typed here can be shown: Clear the field, then type";
    }
    return "";
}

} // namespace OmniKbShowPw
