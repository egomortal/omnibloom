#!/usr/bin/env python3
"""OMNI_KB_EMOJI_V1 (2026-11-16): an emoji page on the on-screen keyboard.

What the user sees
  - The symbols layer (#+=) has an 11th key at the end of its last row, a smiley: Cross opens the emoji page
    (every keyboard: address bar, webpage fields, dialog fields).
  - The page: a row of category tabs (Recent, Smileys, People, Animals, Food, Activity, Travel, Objects, Symbols;
    Flags is in the table but off, see Fonts), a 10 x 4 grid of emoji (scrolls by rows, small arrows right of the
    grid when there is more), and an action row ABC / Space / Delete / Go / Close.
  - Controls: D-pad moves (left/right walk the cells in order and wrap, up/down by rows, past the top/bottom row onto
    the action row, and back); Cross inserts the emoji (or presses the action key); L1/R1 previous/next category;
    Square deletes; Triangle, R3 or the touchpad go back to the letters; Options = Go; Circle / Create close the
    keyboard (as everywhere). L2/R2 still move the caret by words. Pointer clicks: tabs, cells, action keys.
  - Recent: the emoji inserted this session, newest first (up to 20); memory only, never written anywhere. While the
    Recent tab is shown its order stays put (the focus doesn't jump); the next opening starts on Recent.
  - Cross inserts through omniKbType (the path every key uses): webpage fields get WebKit InsertText (real Unicode,
    with U+FE0F where the default presentation is text), the address / dialog fields the usual caret + undo.
  - The accent popup (OMNI_KB_LAYOUTS_V1) is closed when the page opens and only works on the letters; the word chips
    (OMNI_KB_WORDS_V1) are off on the page (omniKwContext needs omniKbPage 0) and come back on the letters.

Fonts (checked 2026-11-16)
  - UI: SDL_ttf (2.20+: has TTF_SetFontSDF) on FreeType 2.13.2 (COLR layers + SVG compiled in, no SVG renderer hooks).
    Faces: Noto Sans JP when installed, else DejaVu Sans; fallbacks Noto Sans KR / SC. None has emoji pictographs.
    The shipped fonts/extra/NotoColorEmoji_400Regular.ttf (25 MB, OFL) is COLRv1 + SVG with empty base glyphs:
    FT_Load_Glyph paints neither, so the shell can't use it. DejaVu Sans (always shipped in /data/omni/fonts) has
    monochrome glyphs for 64 of U+1F600-1F64F and most of Misc Symbols / Dingbats. So UI text gets two more
    fallbacks after KR / SC (omniKemFace, also used by omniPickFace for any UI string no earlier face covers):
    0 DejaVu Sans (Bold for bold faces), 1 the optional /data/omni/fonts/extra/NotoEmoji-Regular.ttf (monochrome
    Noto Emoji, OFL; not shipped: installing it later fills Animals / Food / Travel / Objects with no code change).
  - The page shows only cells a UI face draws (Picker::build with omniKemDrawable, once per run); empty categories
    have no tab. With the shipped fonts: Smileys 69, Symbols ~92, Travel 19, Objects 13, Activity ~8, Animals 5,
    People 3, Food 1 (of 144 / 197 / 183 / 216 / 91 / 126 / 133 / 121 in the table).
  - Flags: off (SDL_ttf draws a regional-indicator pair as two letters; no shipped UI font has them).
  - Pages: what a page shows for an inserted emoji depends on the page's fonts (OmniMain's fontconfig registers
    fonts/extra and prefers Noto Color Emoji for "emoji" and as the last sans/serif fallback; whether WebKit's font
    backend paints its COLRv1 glyphs on the console is not checked here).

Pure part: engine/entry/OmniKbEmoji.h (generated from CATS below): the table, UTF-8 helpers, Picker (filtering,
tabs, grid navigation, scrolling, Recent, pointer hit tests). Tested by tools/test_kb_emoji.cpp:
    python3 apply_kb_emoji.py --header /tmp/h/OmniKbEmoji.h
    g++ -std=c++20 -Wall -Wextra -I/tmp/h test_kb_emoji.cpp -o t && ./t
Shell side: engine/entry/OmniKbEmojiShell.h (included from OmniBrowser.cpp before the on-screen keyboard's drawing).

Anchors in OmniBrowser.cpp (exactly once each, whole lines; MARK makes the file idempotent):
  the OmniKbLayouts.h include (pure include); the omniKbPage declaration (page / key ids, omniKemOn, declarations);
  omniKbBegin's layer/caps + tools lines (a new field leaves the emoji page); the symbols layer's 4th row (11 keys,
  the emoji key last); omniKbAction's newline case (the emoji key); omniKbRepeatable's head (no repeat of Cross,
  Triangle, L1, R1 on the page); omniKbButton's shortcut-page line (the page before the word chips); omniKbClick's
  shortcut-tile line; the comment above omniPickFace (omniKemFace) and its KR/SC loop + return (two more fallbacks);
  omniKbHints' accent-popup line (the page's hints); the "on-screen keyboard" section comment (shell include);
  omniDrawKeyboard's rows / clamp / keysFocused lines (the page drawn in place of the keys).
Ids: omniKbPage 2 (omniKbEmojiPage), key action 100 (omniKbEmojiKey), prefix omniKem / alias OKEM: unused by every
apply_*.py (checked 2026-11-16); the script refuses a tree that has them without MARK.
Apply AFTER apply_kb_words.py and apply_kb_layouts.py (their lines are anchors).
r2 (OMNI_KB_EMOJI_V1_R2, REV): an emoji typed while the shown tab is private is inserted as usual but not added to
Recent. Only OmniKbEmojiShell.h changes (rewritten whole: an r1 tree upgrades).
usage: apply_kb_emoji.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_KB_EMOJI_V1'
REV = 'OMNI_KB_EMOJI_V1_R2'   # r2: Recent is not updated from private tabs (shell only)
root = Path(sys.argv[1]) / 'engine' / 'entry'

# The table: (tab, name, cells separated by spaces). One code point per cell (U+FE0F is added where the default
# presentation is text: TEXT_DEFAULT); Flags: ISO region codes, made into regional-indicator pairs.
CATS = [
 ('Smileys', 'Smileys',
  '😀 😃 😄 😁 😆 😅 🤣 😂 🙂 🙃 😉 😊 😇 🥰 😍 🤩 😘 😗 ☺ 😚 😙 😋 😛 😜 🤪 😝 🤑 🤗 🤭 🤫 🤔 🤐 🤨 😐 😑 😶 😏 😒 🙄 '
  '😬 🤥 😌 😔 😪 🤤 😴 😷 🤒 🤕 🤢 🤮 🤧 🥵 🥶 🥴 😵 🤯 🤠 🥳 😎 🤓 🧐 😕 😟 🙁 ☹ 😮 😯 😲 😳 🥺 😦 😧 😨 😰 😥 😢 😭 '
  '😱 😖 😣 😞 😓 😩 😫 🥱 😤 😡 😠 🤬 😈 👿 💀 ☠ 💩 🤡 👹 👺 👻 👽 👾 🤖 😺 😸 😹 😻 😼 😽 🙀 😿 😾 🙈 🙉 🙊 💋 💌 💘 💝 💖 '
  '💗 💓 💞 💕 💟 ❣ 💔 ❤ 🧡 💛 💚 💙 💜 🤎 🖤 🤍 💯 💢 💥 💫 💦 💨 💬 💭 💤'),
 ('People', 'People',
  '👋 🤚 ✋ 🖖 👌 🤏 ✌ 🤞 🤟 🤘 🤙 👈 👉 👆 🖕 👇 ☝ 👍 👎 ✊ 👊 🤛 🤜 👏 🙌 👐 🤲 🤝 🙏 ✍ 💅 🤳 💪 🦾 🦵 🦶 👂 🦻 👃 '
  '🧠 🦷 🦴 👀 👅 👄 👶 🧒 👦 👧 🧑 👱 👨 🧔 👩 🧓 👴 👵 🙍 🙎 🙅 🙆 💁 🙋 🧏 🙇 🤦 🤷 👮 🕵 💂 👷 🤴 👸 👳 👲 🧕 🤵 👰 🤰 🤱 '
  '👼 🎅 🤶 🦸 🦹 🧙 🧚 🧛 🧜 🧝 🧞 🧟 💆 💇 🚶 🧍 🧎 🏃 💃 🕺 👯 🧖 🧗 🤺 🏇 ⛷ 🏂 🏌 🏄 🚣 🏊 ⛹ 🏋 🚴 🚵 🤸 🤼 🤽 🤾 🤹 🧘 '
  '🛀 🛌 👭 👫 👬 💏 💑 👪 🗣 👤 👥 👣'),
 ('Animals', 'Animals',
  '🐵 🐒 🦍 🦧 🐶 🐕 🦮 🐩 🐺 🦊 🦝 🐱 🐈 🦁 🐯 🐅 🐆 🐴 🐎 🦄 🦓 🦌 🐮 🐂 🐃 🐄 🐷 🐖 🐗 🐽 🐏 🐑 🐐 🐪 🐫 🦙 🦒 🐘 🦏 '
  '🦛 🐭 🐁 🐀 🐹 🐰 🐇 🐿 🦔 🦇 🐻 🐨 🐼 🦥 🦦 🦨 🦘 🦡 🐾 🦃 🐔 🐓 🐣 🐤 🐥 🐦 🐧 🕊 🦅 🦆 🦢 🦉 🦩 🦚 🦜 🐸 🐊 🐢 🦎 🐍 '
  '🐲 🐉 🦕 🦖 🐳 🐋 🐬 🐟 🐠 🐡 🦈 🐙 🐚 🐌 🦋 🐛 🐜 🐝 🐞 🦗 🕷 🕸 🦂 🦟 🦠 💐 🌸 💮 🏵 🌹 🥀 🌺 🌻 🌼 🌷 🌱 🌲 🌳 🌴 🌵 '
  '🌾 🌿 ☘ 🍀 🍁 🍂 🍃'),
 ('Food', 'Food',
  '🍇 🍈 🍉 🍊 🍋 🍌 🍍 🥭 🍎 🍏 🍐 🍑 🍒 🍓 🥝 🍅 🥥 🥑 🍆 🥔 🥕 🌽 🌶 🥒 🥬 🥦 🧄 🧅 🍄 🥜 🌰 🍞 🥐 🥖 🥨 🥯 🥞 🧇 🧀 '
  '🍖 🍗 🥩 🥓 🍔 🍟 🍕 🌭 🥪 🌮 🌯 🥙 🧆 🥚 🍳 🥘 🍲 🥣 🥗 🍿 🧈 🧂 🥫 🍱 🍘 🍙 🍚 🍛 🍜 🍝 🍠 🍢 🍣 🍤 🍥 🥮 🍡 🥟 🥠 '
  '🥡 🦀 🦞 🦐 🦑 🦪 🍦 🍧 🍨 🍩 🍪 🎂 🍰 🧁 🥧 🍫 🍬 🍭 🍮 🍯 🍼 🥛 ☕ 🍵 🍶 🍾 🍷 🍸 🍹 🍺 🍻 🥂 🥃 🥤 🧃 🧉 🧊 🥢 🍽 '
  '🍴 🥄 🔪 🏺'),
 ('Activity', 'Activities',
  '🎃 🎄 🎆 🎇 🧨 ✨ 🎈 🎉 🎊 🎋 🎍 🎎 🎏 🎐 🎑 🧧 🎀 🎁 🎗 🎟 🎫 🎖 🏆 🏅 🥇 🥈 🥉 ⚽ ⚾ 🥎 🏀 🏐 🏈 🏉 🎾 🥏 🎳 🏏 🏑 '
  '🏒 🥍 🏓 🏸 🥊 🥋 🥅 ⛳ ⛸ 🎣 🤿 🎽 🎿 🛷 🥌 🎯 🪀 🪁 🎱 🔮 🧿 🎮 🕹 🎰 🎲 🧩 🧸 ♠ ♥ ♦ ♣ ♟ 🃏 🀄 🎴 🎭 🖼 🎨 🧵 🧶 '
  '🎼 🎵 🎶 🎤 🎧 🎷 🎸 🎹 🎺 🎻 🪕 🥁'),
 ('Travel', 'Travel',
  '🌍 🌎 🌏 🌐 🗺 🗾 🧭 🏔 ⛰ 🌋 🗻 🏕 🏖 🏜 🏝 🏞 🏟 🏛 🏗 🧱 🏘 🏚 🏠 🏡 🏢 🏣 🏤 🏥 🏦 🏨 🏩 🏪 🏫 🏬 🏭 🏯 🏰 💒 🗼 '
  '🗽 ⛪ 🕌 🛕 🕍 ⛩ 🕋 ⛲ ⛺ 🌁 🌃 🏙 🌄 🌅 🌆 🌇 🌉 ♨ 🎠 🎡 🎢 💈 🎪 🚂 🚃 🚄 🚅 🚆 🚇 🚈 🚉 🚊 🚝 🚞 🚋 🚌 🚍 🚎 🚐 '
  '🚑 🚒 🚓 🚔 🚕 🚖 🚗 🚘 🚙 🚚 🚛 🚜 🏎 🏍 🛵 🦽 🦼 🛺 🚲 🛴 🛹 🚏 🛣 🛤 ⛽ 🚨 🚥 🚦 🛑 🚧 ⚓ ⛵ 🛶 🚤 🛳 ⛴ 🛥 🚢 ✈ '
  '🛩 🛫 🛬 🪂 💺 🚁 🚟 🚠 🚡 🛰 🚀 🛸 ⌛ ⏳ ⌚ ⏰ ⏱ ⏲ 🕰 🌑 🌒 🌓 🌔 🌕 🌖 🌗 🌘 🌙 🌚 🌛 🌜 🌡 ☀ 🌝 🌞 🪐 ⭐ 🌟 '
  '🌠 🌌 ☁ ⛅ ⛈ 🌤 🌥 🌦 🌧 🌨 🌩 🌪 🌫 🌬 🌀 🌈 🌂 ☂ ☔ ⛱ ⚡ ❄ ☃ ⛄ ☄ 🔥 💧 🌊'),
 ('Objects', 'Objects',
  '👓 🕶 🥽 🥼 🦺 👔 👕 👖 🧣 🧤 🧥 🧦 👗 👘 🥻 🩱 🩲 🩳 👙 👚 👛 👜 👝 🛍 🎒 👞 👟 🥾 🥿 👠 👡 🩰 👢 👑 👒 🎩 🎓 🧢 ⛑ '
  '📿 💄 💍 💎 🔇 🔈 🔉 🔊 📢 📣 📯 🔔 🔕 📻 📱 📲 ☎ 📞 📟 📠 🔋 🔌 💻 🖥 🖨 ⌨ 🖱 🖲 💽 💾 💿 📀 🧮 🎥 🎞 📽 🎬 📺 📷 '
  '📸 📹 📼 🔍 🔎 🕯 💡 🔦 🏮 🪔 📔 📕 📖 📗 📘 📙 📚 📓 📒 📃 📜 📄 📰 🗞 📑 🔖 🏷 💰 💴 💵 💶 💷 💸 💳 🧾 💹 ✉ 📧 📨 📩 '
  '📤 📥 📦 📫 📪 📬 📭 📮 🗳 ✏ ✒ 🖋 🖊 🖌 🖍 📝 💼 📁 📂 🗂 📅 📆 🗒 🗓 📇 📈 📉 📊 📋 📌 📍 📎 🖇 📏 📐 ✂ 🗃 🗄 🗑 🔒 '
  '🔓 🔏 🔐 🔑 🗝 🔨 🪓 ⛏ ⚒ 🛠 🗡 ⚔ 🔫 🏹 🛡 🔧 🔩 ⚙ 🗜 ⚖ 🦯 🔗 ⛓ 🧰 🧲 ⚗ 🧪 🧫 🧬 🔬 🔭 📡 💉 🩸 💊 🩹 🩺 🚪 🛏 🛋 🪑 '
  '🚽 🚿 🛁 🪒 🧴 🧷 🧹 🧺 🧻 🧼 🧽 🧯 🛒 🚬 ⚰ ⚱ 🗿'),
 ('Symbols', 'Symbols',
  '🏧 🚮 🚰 ♿ 🚹 🚺 🚻 🚼 🚾 🛂 🛃 🛄 🛅 ⚠ 🚸 ⛔ 🚫 🚳 🚭 🚯 🚱 🚷 📵 🔞 ☢ ☣ ⬆ ↗ ➡ ↘ ⬇ ↙ ⬅ ↖ ↕ ↔ ↩ ↪ ⤴ ⤵ 🔃 '
  '🔄 🔙 🔚 🔛 🔜 🔝 🛐 ⚛ 🕉 ✡ ☸ ☯ ✝ ☦ ☪ ☮ 🕎 🔯 ♈ ♉ ♊ ♋ ♌ ♍ ♎ ♏ ♐ ♑ ♒ ♓ ⛎ 🔀 🔁 🔂 ▶ ⏩ ⏭ ⏯ ◀ ⏪ ⏮ 🔼 ⏫ 🔽 '
  '⏬ ⏸ ⏹ ⏺ ⏏ 🎦 🔅 🔆 📶 📳 📴 ♀ ♂ ✖ ➕ ➖ ➗ ♾ ‼ ⁉ ❓ ❔ ❕ ❗ 〰 💱 💲 ⚕ ♻ ⚜ 🔱 📛 🔰 ⭕ ✅ ☑ ✔ ❌ ❎ ➰ ➿ 〽 ✳ ✴ '
  '❇ © ® ™ 🔟 🔠 🔡 🔢 🔣 🔤 🅰 🆎 🅱 🆑 🆒 🆓 ℹ 🆔 Ⓜ 🆕 🆖 🅾 🆗 🅿 🆘 🆙 🆚 🈁 🈂 🔴 🟠 🟡 🟢 🔵 🟣 🟤 ⚫ ⚪ 🟥 🟧 🟨 🟩 '
  '🟦 🟪 🟫 ⬛ ⬜ ◼ ◻ ◾ ◽ ▪ ▫ 🔶 🔷 🔸 🔹 🔺 🔻 💠 🔘 🔳 🔲 🏁 🚩 🎌 🏴 🏳'),
 ('Flags', 'Flags',
  'US GB CA AU NZ IE FR DE IT ES PT NL BE CH AT SE NO DK FI IS PL CZ GR TR UA RU JP KR CN TW HK IN BR MX AR CL CO ZA NG EG '
  'SA AE IL SG PH TH VN ID MY EU UN'),
]

# Text-presentation-default code points (they get U+FE0F so pages show the emoji form).
TEXT_DEFAULT = set(map(ord, '☺☹☠❣❤✌☝✍⛷🏌⛹🏋🕵🗣🐿🕊🕷🕸🏵☘🌶🍽🎗🎟🎖⛸🕹♠♥♦♣♟🖼🗺🏔⛰🏕🏖🏜🏝🏞🏟🏛🏗🏘🏚⛩🏙♨🏎🏍🛣🛤🛳⛴🛥✈'
                        '🛩🛰⏱⏲🕰🌡☀☁⛈🌤🌥🌦🌧🌨🌩🌪🌫🌬☂⛱❄☃☄🕶🛍⛑☎🖥🖨⌨🖱🖲🎞📽🕯🗞🏷✉🗳✏✒🖋🖊🖌🖍🗂🗒🗓🖇✂🗃🗄🗑🗝⛏⚒🛠🗡⚔🛡⚙🗜⚖⛓⚗'
                        '🛏🛋⚰⚱⚠☢☣⬆↗➡↘⬇↙⬅↖↕↔↩↪⤴⤵⚛🕉✡☸☯✝☦☪☮▶⏭⏯◀⏮⏸⏹⏺⏏♀♂✖♾‼⁉〰⚕♻⚜☑✔〽✳✴❇©®™🅰🅱ℹⓂ🅾🅿🈂◼◻▪▫🏳'))


def cell(tok, flags):
    if flags:
        return ''.join(chr(0x1F1E6 + ord(ch) - ord('A')) for ch in tok)
    if len(tok) != 1:
        sys.exit('table: %r is not one code point' % tok)
    return tok + ('️' if ord(tok) in TEXT_DEFAULT else '')


def c_escape(s):
    return ''.join(ch if 0x20 <= ord(ch) < 0x7f and ch not in '"\\' else ''.join('\\x%02x' % b for b in ch.encode('utf-8'))
                   for ch in s)


def lists():
    out, seen = [], set()
    for tab, name, text in CATS:
        cells = [cell(t, name == 'Flags') for t in text.split()]
        for c in cells:
            if c in seen:
                sys.exit('table: %r twice' % c)
            seen.add(c)
        parts = [' '.join(cells[i:i + 16]) for i in range(0, len(cells), 16)]   # adjacent literals, 16 cells a line
        lit = '\n            '.join('"%s%s"' % (c_escape(p), ' ' if i + 1 < len(parts) else '') for i, p in enumerate(parts))
        out.append('        { "%s", "%s",\n            %s },' % (tab, name, lit))
    return '\n'.join(out)


PURE_IN = r'''// OMNI_KB_EMOJI_V1: the pure part of the keyboard's emoji page (no SDL, no WebKit). Generated by
// tools/apply_kb_emoji.py (edit the table there). Shell side: OmniKbEmojiShell.h.
// The table: one emoji per cell, a single code point (+ U+FE0F where the default presentation is text) or a
// regional-indicator pair (flags); no ZWJ sequences and no skin tones, so the shell can check exactly whether its
// fonts draw a cell (Picker::build hides the ones they don't, and categories left empty).
// The grid: kCols x kRows cells visible, scrolled by rows; below it the action row (ABC, Space, Delete, Go, Close).
// Recent: the emoji used this session, newest first (memory only, never written anywhere).
#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace OmniKbEmoji {

constexpr int kCols = 10, kRows = 4;   // visible grid (keyboard rows 1-4; row 0 holds the category tabs)
enum Action { kActLetters = 0, kActSpace, kActDelete, kActGo, kActClose, kActionCount };
constexpr size_t kRecentMax = 20;
constexpr const char* kKeyLabel = "\xf0\x9f\x98\x80";   // the key on the symbols layer that opens the page
enum Cat { kRecent = 0, kSmileys, kPeople, kAnimals, kFood, kActivities, kTravel, kObjects, kSymbols, kFlags, kCatCount };

struct Category { const char* tab; const char* name; const char* list; };   // list: emoji separated by single spaces
inline const Category& category(int c)
{
    static const Category table[kCatCount] = {
        { "Recent", "Recent", "" },
@LISTS@
    };
    return table[std::clamp(c, 0, int(kCatCount) - 1)];
}

// UTF-8 -> code points (invalid bytes are skipped).
inline std::vector<uint32_t> codepoints(std::string_view s)
{
    std::vector<uint32_t> out;
    for (size_t i = 0; i < s.size();) {
        const unsigned char c = static_cast<unsigned char>(s[i]);
        const int n = c < 0x80 ? 1 : (c >> 5) == 6 ? 2 : (c >> 4) == 14 ? 3 : (c >> 3) == 30 ? 4 : 0;
        if (!n || i + size_t(n) > s.size()) { ++i; continue; }
        uint32_t cp = n == 1 ? c : uint32_t(c & (0x7f >> n));
        bool ok = true;
        for (int k = 1; k < n; ++k) {
            const unsigned char d = static_cast<unsigned char>(s[i + size_t(k)]);
            if ((d & 0xc0) != 0x80) { ok = false; break; }
            cp = (cp << 6) | (d & 0x3f);
        }
        if (ok) out.push_back(cp);
        i += ok ? size_t(n) : 1;
    }
    return out;
}
// What the shell draws: the cell without U+FE0F (its fonts have no emoji presentation; the page gets the full text).
inline std::string display(std::string_view s)
{
    std::string out(s);
    for (size_t p; (p = out.find("\xef\xb8\x8f")) != std::string::npos;) out.erase(p, 3);
    return out;
}
inline bool isRegionalIndicator(uint32_t cp) { return cp >= 0x1f1e6 && cp <= 0x1f1ff; }
inline std::vector<std::string> split(std::string_view list)
{
    std::vector<std::string> out;
    size_t i = 0;
    while (i < list.size()) {
        size_t j = list.find(' ', i);
        if (j == std::string_view::npos) j = list.size();
        if (j > i) out.emplace_back(list.substr(i, j - i));
        i = j + 1;
    }
    return out;
}

struct Picker {
    std::vector<std::string> items[kCatCount];   // drawable cells per category (kRecent unused: `recent`)
    std::vector<std::string> recent;             // this session only
    bool built = false;
    int cat = kSmileys, sel = 0, top = 0, action = 0;
    bool onActions = false;

    // drawable(display text) -> bool; flagsOk: the shell can draw a flag from a regional-indicator pair.
    template <class Pred> void build(Pred drawable, bool flagsOk)
    {
        for (int c = kSmileys; c < kCatCount; ++c) {
            items[c].clear();
            if (c == kFlags && !flagsOk) continue;
            for (std::string& e : split(category(c).list))
                if (drawable(display(e))) items[c].push_back(std::move(e));
        }
        built = true;
    }
    const std::vector<std::string>& list(int c) const { return c == kRecent ? recent : items[std::clamp(c, 0, int(kCatCount) - 1)]; }
    const std::vector<std::string>& list() const { return list(cat); }
    bool hasItems(int c) const { return !list(c).empty(); }
    int count() const { return int(list().size()); }
    int rowCount() const { return (count() + kCols - 1) / kCols; }
    // The categories with something to show, in table order (the tab row).
    std::vector<int> tabs() const
    {
        std::vector<int> t;
        for (int c = 0; c < kCatCount; ++c) if (hasItems(c)) t.push_back(c);
        return t;
    }
    void ensureVisible()
    {
        const int rows = rowCount();
        if (onActions || !rows) { top = std::clamp(top, 0, std::max(0, rows - kRows)); return; }
        sel = std::clamp(sel, 0, count() - 1);
        const int r = sel / kCols;
        if (r < top) top = r;
        if (r >= top + kRows) top = r - kRows + 1;
        top = std::clamp(top, 0, std::max(0, rows - kRows));
    }
    void select(int c)
    {
        cat = c;
        sel = top = 0;
        onActions = !hasItems(c);
        if (onActions) action = kActLetters;
    }
    // The page opens on Recent when something was used this session, else on the first category with cells.
    void open()
    {
        const std::vector<int> t = tabs();
        select(t.empty() ? int(kSmileys) : t.front());
    }
    void switchCategory(int dir)
    {
        const std::vector<int> t = tabs();
        if (t.empty()) return;
        int i = int(std::find(t.begin(), t.end(), cat) - t.begin());
        if (i >= int(t.size())) i = dir > 0 ? -1 : 0;
        select(t[size_t((i + (dir > 0 ? 1 : -1) + int(t.size())) % int(t.size()))]);
    }
    // D-pad: left/right walk the cells in order (wrapping), up/down move by a row; past the top or bottom row the
    // focus goes to the action row (whose keys are 2 columns wide), and from there back into the grid.
    void move(int dx, int dy)
    {
        const int n = count();
        if (onActions) {
            if (dx) action = (action + dx + kActionCount) % kActionCount;
            if (dy && n) {
                const int col = std::min(action * 2, kCols - 1);
                onActions = false;
                if (dy > 0) sel = std::min(col, n - 1);
                else sel = std::min((rowCount() - 1) * kCols + col, n - 1);
            }
            ensureVisible();
            return;
        }
        if (!n) { onActions = true; return; }
        if (dx) sel = (sel + dx % n + n) % n;
        if (dy < 0) {
            if (sel >= kCols) sel -= kCols;
            else { onActions = true; action = std::min(sel / 2, kActionCount - 1); }
        } else if (dy > 0) {
            if (sel + kCols < n) sel += kCols;
            else if (sel / kCols + 1 < rowCount()) sel = n - 1;   // the last row is short: its last cell
            else { onActions = true; action = std::min(sel % kCols / 2, kActionCount - 1); }
        }
        ensureVisible();
    }
    // The focused cell, or nullptr (action row, empty category).
    const std::string* current() const
    {
        if (onActions || sel < 0 || sel >= count()) return nullptr;
        return &list()[size_t(sel)];
    }
    // A cell was inserted: it goes to the front of Recent (once). While Recent is shown its order stays put, so the
    // focus doesn't jump under the user; the next opening shows the new order.
    void remember(const std::string& e)
    {
        auto it = std::find(recent.begin(), recent.end(), e);
        if (cat == kRecent && it != recent.end()) return;
        if (it != recent.end()) recent.erase(it);
        recent.insert(recent.begin(), e);
        if (recent.size() > kRecentMax) recent.resize(kRecentMax);
    }
    // Pointer: the grid cell index at visible row r (0..kRows-1) and column c, or -1.
    int cellAt(int r, int c) const
    {
        if (r < 0 || r >= kRows || c < 0 || c >= kCols) return -1;
        const int i = (top + r) * kCols + c;
        return i < count() ? i : -1;
    }
    // Pointer: the category of the tab at x (layout px from the left of the tab row, tabs `tabW` wide), or -1.
    int tabAt(int x, int tabW) const
    {
        const std::vector<int> t = tabs();
        if (x < 0 || tabW <= 0 || x / tabW >= int(t.size())) return -1;
        return t[size_t(x / tabW)];
    }
};

} // namespace OmniKbEmoji
'''

SHELL = r'''// OMNI_KB_EMOJI_V1: the keyboard's emoji page (shell side). Included from OmniBrowser.cpp before the on-screen
// keyboard's drawing code; pure part: OmniKbEmoji.h; reasons and anchors: tools/apply_kb_emoji.py.
// omniKbPage == omniKbEmojiPage (any keyboard: address, webpage field, dialog field). Opened by the emoji key at the
// end of the symbols layer's last row. Cross inserts through omniKbType (the path of every key), so webpage fields
// get InsertText and the address/dialog fields their usual undo/caret handling.
// The UI fonts (Noto Sans JP/KR/SC or DejaVu) have no colour emoji: cells are drawn in monochrome by DejaVu Sans (always
// shipped: emoticons, symbols, a few pictographs) or an optional fonts/extra/NotoEmoji-Regular.ttf (omniKemFace), and
// cells no font draws are left out (OmniKbEmoji::Picker::build, once per run). Flags are off: SDL_ttf draws a
// regional-indicator pair as two letters.
#pragma once

namespace OKEM = OmniKbEmoji;
static OKEM::Picker omniKem;

// The faces omniPickFace would use for a label in face `id` (and nothing else): true when one of them has every code point.
static bool omniKemDrawable(const std::string& value)
{
    const std::vector<uint32_t> cps = OKEM::codepoints(value);
    if (cps.empty()) return false;
    auto covers = [&](TTF_Font* f) { if (!f) return false; for (uint32_t cp : cps) if (!omniGlyph(f, cp)) return false; return true; };
    const int id = omniTitle;
    if (covers(omniFaces[id].f)) return true;
    for (int which = 0; which < 2; ++which) if (covers(omniFallbackFace(id, which))) return true;
    for (int which = 0; which < 2; ++which) if (covers(omniKemFace(id, which))) return true;
    return false;
}
static void omniKemOpen()
{
    omniKblClose();               // OMNI_KB_LAYOUTS_V1: no accent popup / waiting letter over the page
    omniKbl.pending = false;
    if (!omniKem.built) {
        const uint32_t t0 = SDL_GetTicks();
        omniKem.build(omniKemDrawable, false);
        int n = 0;
        for (int c = 0; c < OKEM::kCatCount; ++c) n += int(omniKem.items[c].size());
        fprintf(stderr, "OMNI_KB_EMOJI_V1: %d emoji drawable (%u ms)\n", n, unsigned(SDL_GetTicks() - t0));
    }
    omniKem.open();
    omniKbPage = omniKbEmojiPage;
    omniShellDirty = true;
}
static void omniKemLetters()
{
    omniKbPage = 0;
    omniKb.layer = omniKbLetters;
    omniKbFocusClamp();
}
static void omniKemDo(int a)
{
    switch (a) {
    case OKEM::kActLetters: omniKemLetters(); break;
    case OKEM::kActSpace: omniKbAction(omniKbSpaceKey); break;
    case OKEM::kActDelete: omniKbAction(omniKbBackKey); break;
    case OKEM::kActGo: omniKbAction(omniKbGoKey); break;
    case OKEM::kActClose: omniKbAction(omniKbCloseKey); break;
    default: break;
    }
}
static void omniKemInsert(int i)
{
    const auto& list = omniKem.list();
    if (i < 0 || i >= int(list.size())) return;
    const std::string e = list[size_t(i)];   // a copy: remember() may reorder Recent
    if (!(active() && active()->omniPrivate)) omniKem.remember(e);   // OMNI_KB_EMOJI_V1_R2: not from private tabs
    omniKbType(e);
}
// Every controller button on the emoji page (from omniKbButton; Circle / Create closed the keyboard before this).
static void omniKemButton(int b)
{
    omniShellDirty = true;
    switch (b) {
    case SDL_CONTROLLER_BUTTON_A:
        if (omniKem.onActions) omniKemDo(omniKem.action);
        else omniKemInsert(omniKem.sel);
        break;
    case SDL_CONTROLLER_BUTTON_X: omniKbAction(omniKbBackKey); break;   // Square: delete, as on the letters
    case SDL_CONTROLLER_BUTTON_Y: case SDL_CONTROLLER_BUTTON_RIGHTSTICK: case SDL_CONTROLLER_BUTTON_TOUCHPAD: omniKemLetters(); break;
    case SDL_CONTROLLER_BUTTON_START: omniKbAction(omniKbGoKey); break;
    case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: omniKem.switchCategory(-1); break;
    case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: omniKem.switchCategory(1); break;
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: omniKem.move(-1, 0); break;
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: omniKem.move(1, 0); break;
    case SDL_CONTROLLER_BUTTON_DPAD_UP: omniKem.move(0, -1); break;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: omniKem.move(0, 1); break;
    default: break;
    }
}
// Pointer clicks on the emoji page: r = keyboard row (0 tabs, 1-4 grid, 5 actions), x in layout px.
static void omniKemClick(int x, int r)
{
    const int dx = x - keyboardX;
    if (r == 0) { if (const int c = omniKem.tabAt(dx, keyWidth); c >= 0) omniKem.select(c); return; }
    if (r >= 1 && r <= 4) {
        const int i = omniKem.cellAt(r - 1, dx / keyWidth);
        if (i >= 0) { omniKem.onActions = false; omniKem.sel = i; omniKemInsert(i); }
        return;
    }
    const int a = std::clamp(dx / (2 * keyWidth), 0, int(OKEM::kActionCount) - 1);
    omniKem.onActions = true;
    omniKem.action = a;
    omniKemDo(a);
}
// Drawn by omniDrawKeyboard in place of the keys (same geometry: keyboardY + r * keyHeight, actionY).
static void omniKemDraw(int keyH, SDL_Color emptyKey)
{
    const OmniTheme& T = omniTheme();
    omniKem.ensureVisible();
    const std::vector<int> tabs = omniKem.tabs();
    for (int i = 0; i < int(tabs.size()) && i < OKEM::kCols; ++i) {
        const int x = keyboardX + i * keyWidth;
        const bool on = tabs[size_t(i)] == omniKem.cat;
        fillRounded(x, keyboardY, keyWidth - 4, keyH, omniRadius, on ? omniMix(T.key, T.accent, 0.45f) : omniMix(T.key, T.panel, 0.35f));
        omniLabel(OKEM::category(tabs[size_t(i)]).tab, x + (keyWidth - 4) / 2.f, keyboardY + keyH / 2.f, on ? omniCaptionBold : omniCaption, on ? T.ink : T.inkDim, 1, keyWidth - 10);
    }
    const auto& list = omniKem.list();
    for (int r = 0; r < OKEM::kRows; ++r)
        for (int c = 0; c < OKEM::kCols; ++c) {
            const int x = keyboardX + c * keyWidth, y = keyboardY + (r + 1) * keyHeight;
            const int i = omniKem.cellAt(r, c);
            const bool sel = i >= 0 && !omniKem.onActions && i == omniKem.sel;
            fillRounded(x, y, keyWidth - 4, keyH, omniRadius, sel ? T.accent : i >= 0 ? T.key : emptyKey);
            if (i >= 0) omniLabel(OKEM::display(list[size_t(i)]), x + (keyWidth - 4) / 2.f, y + keyH / 2.f, omniTitle, sel ? T.accentInk : T.ink, 1, keyWidth - 8);
        }
    // More rows above / below: small arrows right of the grid.
    if (omniKem.top > 0) omniLabel("\xe2\x96\xb2", float(keyboardX + keyboardWidth + 6), keyboardY + keyHeight + keyH / 2.f, omniCaption, T.inkFaint, 0);
    if (omniKem.top + OKEM::kRows < omniKem.rowCount())
        omniLabel("\xe2\x96\xbc", float(keyboardX + keyboardWidth + 6), keyboardY + OKEM::kRows * keyHeight + keyH / 2.f, omniCaption, T.inkFaint, 0);
    static const char* const names[OKEM::kActionCount] = { "ABC", "Space", "Delete", nullptr, "Close" };
    for (int a = 0; a < OKEM::kActionCount; ++a) {
        const int x = keyboardX + a * 2 * keyWidth;
        const bool sel = omniKem.onActions && omniKem.action == a;
        fillRounded(x, actionY, 2 * keyWidth - 4, keyH, omniRadius, sel ? T.accent : omniMix(T.key, T.panel, 0.35f));
        const std::string label = names[a] ? std::string(names[a]) : omniKbGoLabel();
        omniLabel(label, x + keyWidth - 2.f, actionY + keyH / 2.f, omniSmall, sel ? T.accentInk : a == OKEM::kActGo ? T.accent : T.ink, 1, 2 * keyWidth - 12);
    }
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniKbLayouts.h" // OMNI_KB_LAYOUTS_V1: keyboard layouts, accent variants, UTF-8 (pure)\n',
         '#include "OmniKbLayouts.h" // OMNI_KB_LAYOUTS_V1: keyboard layouts, accent variants, UTF-8 (pure)\n'
         '#include "OmniKbEmoji.h" // OMNI_KB_EMOJI_V1: the keyboard\'s emoji page, table + grid (pure)\n'),
        ('static int omniKbPage = 0;          // 0 = letters, 1 = shortcuts (address keyboard only)\n',
         'static int omniKbPage = 0;          // 0 = letters, 1 = shortcuts (address keyboard only)\n'
         '// OMNI_KB_EMOJI_V1: omniKbPage 2 = the emoji page on every keyboard (OmniKbEmojiShell.h); omniKbEmojiKey opens it.\n'
         'constexpr int omniKbEmojiPage = 2, omniKbEmojiKey = 100;\n'
         'static bool omniKemOn() { return editing && omniKbPage == omniKbEmojiPage; }\n'
         'static void omniKemOpen();\n'
         'static void omniKemButton(int b);\n'
         'static void omniKemClick(int x, int r);\n'),
        ('    omniKb.layer = omniKbLetters; omniKb.caps = 0; shift = false;\n    omniKb.tools = omniKb.select = false;\n',
         '    omniKb.layer = omniKbLetters; omniKb.caps = 0; shift = false;\n    omniKb.tools = omniKb.select = false;\n'
         '    if (omniKbPage == omniKbEmojiPage) omniKbPage = 0; // OMNI_KB_EMOJI_V1: a new field starts on the letters\n'),
        ('        chars(rows[3], "` ~ \\xe2\\x82\\xac \\xc2\\xa3 \\xc2\\xa5 \\xc2\\xb0 \\xe2\\x80\\xa2 \\xc2\\xab \\xc2\\xbb \\xc2\\xa7", 1);\n',
         '        chars(rows[3], "` ~ \\xe2\\x82\\xac \\xc2\\xa3 \\xc2\\xa5 \\xc2\\xb0 \\xe2\\x80\\xa2 \\xc2\\xab \\xc2\\xbb \\xc2\\xa7", 10.f / 11); // OMNI_KB_EMOJI_V1: 11 keys\n'
         '        rows[3].push_back({ OmniKbEmoji::kKeyLabel, "", omniKbEmojiKey, 10.f / 11 }); // OMNI_KB_EMOJI_V1: opens the emoji page\n'),
        ('    case omniKbNewlineKey: if (page) omniKbPageCmd(omniKb.contentEditable ? "InsertLineBreak" : "InsertNewline"); return;\n',
         '    case omniKbNewlineKey: if (page) omniKbPageCmd(omniKb.contentEditable ? "InsertLineBreak" : "InsertNewline"); return;\n'
         '    case omniKbEmojiKey: omniKemOpen(); return; // OMNI_KB_EMOJI_V1\n'),
        ('static bool omniKbRepeatable(int b)\n{\n',
         'static bool omniKbRepeatable(int b)\n{\n'
         '    if (omniKemOn() && (b == SDL_CONTROLLER_BUTTON_A || b == SDL_CONTROLLER_BUTTON_Y || b == SDL_CONTROLLER_BUTTON_LEFTSHOULDER\n'
         '        || b == SDL_CONTROLLER_BUTTON_RIGHTSHOULDER)) return false; // OMNI_KB_EMOJI_V1: one emoji / category per press\n'),
        ('    if (omniKb.kind == 0 && omniKbPage == 1) { omniKbShortcutButton(b); return; }\n',
         '    if (omniKb.kind == 0 && omniKbPage == 1) { omniKbShortcutButton(b); return; }\n'
         '    if (omniKemOn()) { omniKemButton(b); return; } // OMNI_KB_EMOJI_V1: the emoji page (before the word chips)\n'),
        ('    if (omniKb.kind == 0 && omniKbPage == 1) { // OMNI_SHORTCUTS_V1 tiles\n',
         '    if (omniKemOn()) { omniKemClick(x, r); return; } // OMNI_KB_EMOJI_V1\n'
         '    if (omniKb.kind == 0 && omniKbPage == 1) { // OMNI_SHORTCUTS_V1 tiles\n'),
        ('// Only called when a string is rendered or measured for the first time (results are cached).\n',
         '// OMNI_KB_EMOJI_V1: monochrome emoji for UI text after the KR / SC fallbacks: 0 DejaVu Sans (always shipped:\n'
         '// emoticons, symbols), 1 fonts/extra/NotoEmoji-Regular.ttf when installed (optional). Opened on first need.\n'
         'static TTF_Font* omniKemFaces[omniFaceCount][2] = {};\n'
         'static bool omniKemTried[omniFaceCount][2] = {};\n'
         'static TTF_Font* omniKemFace(int id, int which)\n'
         '{\n'
         '    if (id < 0 || id >= omniFaceCount || which < 0 || which > 1) return nullptr;\n'
         '    if (!omniKemTried[id][which]) {\n'
         '        omniKemTried[id][which] = true;\n'
         '        const char* path = which == 1 ? "/data/omni/fonts/extra/NotoEmoji-Regular.ttf"\n'
         '            : omniFaces[id].bold ? "/data/omni/fonts/DejaVuSans-Bold.ttf" : "/data/omni/fonts/DejaVuSans.ttf";\n'
         '        if (omniFaces[id].px > 0 && !access(path, R_OK) && (omniKemFaces[id][which] = TTF_OpenFont(path, omniFaces[id].px)) && which == 1)\n'
         '            TTF_SetFontHinting(omniKemFaces[id][which], TTF_HINTING_LIGHT);\n'
         '    }\n'
         '    return omniKemFaces[id][which];\n'
         '}\n'
         '// Only called when a string is rendered or measured for the first time (results are cached).\n'),
        ('        if (TTF_Font* f = omniFallbackFace(id, which); f && covers(f)) return f;\n    return base;\n',
         '        if (TTF_Font* f = omniFallbackFace(id, which); f && covers(f)) return f;\n'
         '    for (int which = 0; which < 2; ++which) // OMNI_KB_EMOJI_V1: DejaVu Sans, then the optional mono emoji font\n'
         '        if (TTF_Font* f = omniKemFace(id, which); f && covers(f)) return f;\n'
         '    return base;\n'),
        ('    if (omniKbl.open) { face(0, "Insert"); face(1, "Cancel"); pill("D-pad"); label("Choose accent"); return; } // OMNI_KB_LAYOUTS_V1\n',
         '    if (omniKemOn()) { // OMNI_KB_EMOJI_V1: the emoji page\n'
         '        face(0, "Insert"); face(2, "Delete"); face(3, "Letters"); face(1, "Close"); options(omniKbGoLabel());\n'
         '        shoulders("Category");\n'
         '        return;\n'
         '    }\n'
         '    if (omniKbl.open) { face(0, "Insert"); face(1, "Cancel"); pill("D-pad"); label("Choose accent"); return; } // OMNI_KB_LAYOUTS_V1\n'),
        ('// OMNI_STYLE_V1 / OMNI_KEYBOARD_V2: on-screen keyboard ----------------------------------------------\n',
         '#include "OmniKbEmojiShell.h" // OMNI_KB_EMOJI_V1: the emoji page (shell side)\n'
         '// OMNI_STYLE_V1 / OMNI_KEYBOARD_V2: on-screen keyboard ----------------------------------------------\n'),
        ('    const auto& rows = omniKbRows();\n    omniKbFocusClamp();\n    const bool keysFocused = ',
         '    if (omniKemOn()) { omniKemDraw(keyH, emptyKey); return; } // OMNI_KB_EMOJI_V1: the emoji page in place of the keys\n'
         '    const auto& rows = omniKbRows();\n    omniKbFocusClamp();\n    const bool keysFocused = '),
    ],
}
# Names this script adds: a tree that has them without MARK was patched by something else (refuse).
OWN_IDS = ('omniKem', 'OKEM', 'OmniKbEmoji', 'omniKbEmojiPage', 'omniKbEmojiKey', 'omniKbPage == 2', 'omniKbPage = 2')


# The Controls guide's table names other patches' handlers by design: never a name clash (numbers still count there).
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): an id or name in another patch's notes (e.g. "834-839" in a generated header) is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def check(name, edits):
    s = (root / name).read_bytes().decode('utf-8')
    if MARK in s:
        return
    code = cpp_code(s)
    for i in OWN_IDS:
        if i in code:
            sys.exit('%s: %r already used (without %s): refusing' % (name, i, MARK))
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits):
    p = root / name
    s = p.read_bytes().decode('utf-8')
    if MARK in s:
        return name + ': already'
    for old0, new0 in edits:
        old, e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))
        s = s.replace(old, new0.replace('\n', e), 1)
    p.write_bytes(s.encode('utf-8'))
    return name + ': applied'


def write_new(name, text, like):
    raw = (root / like).read_bytes()
    nl = '\r\n' if raw.count(b'\r\n') * 2 > raw.count(b'\n') else '\n'
    data = text.replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    if h.exists() and MARK not in h.read_bytes().decode('utf-8', 'replace'):
        sys.exit('%s exists and is not ours: refusing' % name)
    h.write_bytes(data)
    return name + ': written'


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--header':   # tests: write the pure header only
        Path(sys.argv[2]).write_bytes(PURE_IN.replace('@LISTS@', lists()).encode('utf-8'))
        return
    s = (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8')
    for need, tool in (('OMNI_KB_LAYOUTS_V1', 'apply_kb_layouts.py'), ('OMNI_KB_WORDS_V1', 'apply_kb_words.py')):
        if need not in s:
            sys.exit('OmniBrowser.cpp: %s missing: %s first' % (need, tool))
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniKbEmoji.h', PURE_IN.replace('@LISTS@', lists()), 'OmniKbLayouts.h'),
            write_new('OmniKbEmojiShell.h', SHELL, 'OmniKbLayouts.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK + ' (r2)')


main()
