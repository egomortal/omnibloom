#!/usr/bin/env python3
"""OMNI_KB_WORDS_V1 word list generator: builds the built-in English completion list for the on-screen keyboard
from (1) SEED, a short everyday-vocabulary list written for this project, ranked first, then (2) word counts over this
project's OWN prose (the Markdown notes, reports and READMEs under the project root). No third-party frequency list is
used, so no outside licence applies; the words are counted, not copied.

Rules: every *.md file (at most 1 MB) under <project root>, skipping vendored / third-party trees (node_modules, .git,
vendor, *-reference, decrypted dumps, baseline, assets, branding) and fenced code blocks / inline code. A token is a
run of ASCII letters with inner apostrophes; it counts when it is all lower case or Capitalised (identifiers such as
omniKbDraw, CamelCase and ALLCAPS are dropped), lower-cased, 2..16 letters. A word is kept when it appears in at least
3 different files and 6 times in all, ranked by count (ties: alphabetical); the top N (default 8000) are written.

usage: gen_kb_words.py <project root> <out.txt> [N]
out.txt: one word per line, most frequent first (apply_kb_words.py embeds it, front-coded, as OmniKbWordsData.h).
"""
import os
import re
import sys

SKIP = {'node_modules', '.git', 'vendor', 'decrypted', '1888.FS-decrypted', 'baseline', 'assets', 'branding', 'third_party',
        'ThirdParty', 'Source', 'LayoutTests', 'WebKitBuild', 'build'}
TOKEN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)*")
FENCE = re.compile(r'^\s*(```|~~~)')
CODE = re.compile(r'`[^`]*`')
URL = re.compile(r'\S+://\S+|\S+@\S+|\S*[/\\]\S*')
# Everyday words written for this project (no external list), roughly most common first: they rank ahead of the
# counted words so that search boxes, comments and chat get "you", "thanks", "weather"... even though the project's
# prose is technical.
SEED = '''the be to of and a in that have it for not on with he as you do at this but his by from they we say her she
or an will my one all would there their what so up out if about who get which go me when make can like time no just
him know take people into year your good some could them see other than then now look only come its over think also
back after use two how our work first well way even new want because any these give day most us is are was were been
has had did does doing done i'm you're it's don't can't won't isn't didn't doesn't i've i'll i'd we're they're that's
there's let's what's where how why yes ok okay please thanks thank hello hi hey sorry great nice love best free more
many much very really still here where every never always something nothing anything everything someone anyone
everyone today tomorrow yesterday tonight morning night week month weekend home house family friend friends kids
child children man woman men women life world school work job money car city country game games play playing music
song songs movie movies video videos show shows watch watching news weather food recipe recipes restaurant near me
open opening hours price prices cheap buy sale shop shopping store online order delivery phone number email address
name password account login sign search find help support question answer problem issue fix update download install
how to what is best way new old big small long short high low right left next last few little own same different
important public private real sure need needs feel try trying ask asked tell told call called keep keeping start
started stop stopped turn turned show showed hear heard read reading write writing wrote learn learning live living
believe hold bring brought happen happened begin began seem seemed leave left put mean meant become became run running
move moved pay paid meet met include including continue set change changed lead understand watch follow followed
create created speak spoke allow add added spend spent grow grew offer offered remember love loved consider appear
wait waiting serve die died send sent expect build built stay fall fell cut reach kill remain suggest raise pass sell
sold require report decide pull return explain hope hoped develop carry break receive agree support hit produce eat
eating cover catch draw choose cause point listen listening plan planning travel trip hotel flight flights ticket
tickets book books story stories picture pictures photo photos image images page pages site website link links
internet computer playstation xbox console controller tv channel stream streaming live episode season series trailer
review reviews rating news sports football soccer basketball baseball team teams score scores player players match
league cup final world cup weather forecast rain snow sun hot cold warm summer winter spring autumn fall christmas
birthday party holiday vacation happy funny cute cool awesome amazing beautiful bad worse worst better easy hard
fast slow early late free full empty open closed true false yes maybe probably actually already almost enough
together alone again away down off around through during before after since until while without within between
under above below behind inside outside across along against among toward towards upon because though although
however therefore instead either neither both each another such whether whatever whenever wherever whoever
question questions answer answers idea ideas reason reasons example examples part parts place places point points
thing things fact case group number numbers system program government company business service services market
community health care doctor hospital water air fire light color colour red blue green black white yellow orange
purple pink brown gray grey dog dogs cat cats animal animals car cars bike bus train road street town village
mother father mom dad brother sister son daughter wife husband baby girl boy girls boys guy guys person body head
face eyes hand hands heart mind word words language english spanish french german japanese chinese korean
translate translation meaning definition weather time zone date calendar clock alarm timer minute minutes hour
hours second seconds day days week weeks month months year years monday tuesday wednesday thursday friday saturday
sunday january february march april may june july august september october november december first second third
one two three four five six seven eight nine ten hundred thousand million billion half quarter dollar dollars
pound pounds euro euros cost costs money bank card pay payment shipping return returns refund deal deals coupon
youtube google wikipedia reddit twitter facebook instagram tiktok netflix twitch spotify amazon discord steam
lyrics chords tutorial guide walkthrough trophy trophies achievement achievements patch patches mod mods tips
tricks cheat cheats boss level levels character characters weapon weapons build builds ending map maps quest
quests multiplayer online offline release date trailer gameplay review'''.split()
# Technical leftovers that are words only in this project (file names, tools, units): kept out of everyday typing.
STOP = set('''omni exbox ps webkit wpe sdl gpu cpu ui wsl cpp py json js html css png jpg exe dll elf sprx prx bin dir
tmp src md txt ok ui id ids url urls api apis sdk sdks ms px kb mb gb fps hz usb ip os vm'''.split())
# Words made only of the letters a-f (2..5 long) are usually hex fragments; these are real words.
COMMON_HEX = set('ad add added be bed bee beef cab cafe dad dead deaf deed face faced fade faded fed fee feed'.split())


def walk(root):
    for top in sorted(os.listdir(root)):
        p = os.path.join(root, top)
        if top in SKIP or top.endswith('-reference'):
            continue
        if os.path.isfile(p):
            if top.lower().endswith('.md'):
                yield p
            continue
        for d, dirs, files in os.walk(p):
            dirs[:] = sorted(x for x in dirs if x not in SKIP and not x.endswith('-reference'))
            for f in sorted(files):
                if f.lower().endswith('.md'):
                    yield os.path.join(d, f)


def main():
    root, out = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 8000
    count, docs, files = {}, {}, 0
    for path in walk(root):
        try:
            if os.path.getsize(path) > 1_000_000:
                continue
            text = open(path, encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        files += 1
        seen, fenced = set(), False
        for line in text.splitlines():
            if FENCE.match(line):
                fenced = not fenced
                continue
            if fenced:
                continue
            line = URL.sub(' ', CODE.sub(' ', line))
            for tok in TOKEN.findall(line):
                if not (tok.islower() or (tok[0].isupper() and tok[1:].islower())):
                    continue
                w = tok.lower()
                if not 2 <= len(w.replace("'", '')) <= 16 or w in STOP:
                    continue
                count[w] = count.get(w, 0) + 1
                if w not in seen:
                    seen.add(w)
                    docs[w] = docs.get(w, 0) + 1
    hexish = re.compile(r'^[a-f]{2,5}$')
    seed, seen = [], set()
    for w in SEED:
        if len(w.replace("'", '')) >= 2 and w not in seen:
            seen.add(w)
            seed.append(w)
    kept = [w for w in count if docs[w] >= 3 and count[w] >= 6 and w not in seen
            and not w.endswith("'s") and not (hexish.match(w) and w not in COMMON_HEX)]
    kept.sort(key=lambda w: (-count[w], w))
    kept = (seed + kept)[:n]
    with open(out, 'w', encoding='ascii', newline='\n') as f:
        f.write(''.join(w + '\n' for w in kept))
    print('%d files, %d distinct, %d written to %s' % (files, len(count), len(kept), out))


main()
