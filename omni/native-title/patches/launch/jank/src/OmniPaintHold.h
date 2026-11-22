// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdint>
namespace OmniPaintHold {
struct Gate {
    uint64_t epoch=0;
    uint32_t started=0,lastProbe=0;
    bool active=false,pending=false;
    void begin(uint64_t id,uint32_t now,bool enabled) { epoch=id;started=now;lastProbe=now-250;active=enabled;pending=false; }
    void cancel() { active=false;pending=false; }
    bool holding(uint32_t now) { if(active && uint32_t(now-started)>=2000)cancel();return active; }
    bool probe(uint32_t now) { if(!holding(now)||pending||uint32_t(now-lastProbe)<250)return false;pending=true;lastProbe=now;return true; }
    bool reply(uint64_t id,bool ready) { if(id!=epoch)return false;pending=false;if(ready)active=false;return true; }
};
// A reveal key owns its repeats and text, including text queued after key-up.
// A fresh key-down begins a new gesture; window focus changes reset stale ownership.
struct RevealInput {
    int32_t revealKey=0;
    bool armed=false,held=false,suppressText=false;
    void consumeGesture(int32_t code) { revealKey=code;armed=true;held=true;suppressText=true; }
    bool keyDown(int32_t code,bool repeat) {
        if(armed && code==revealKey && (held||repeat)) { suppressText=true;return true; }
        if(!repeat) { suppressText=false;if(!held)armed=false; }
        return false;
    }
    void keyUp(int32_t code) { if(armed&&code==revealKey)held=false; }
    bool textInput() const { return suppressText; }
    void reset() { revealKey=0;armed=false;held=false;suppressText=false; }
};

}
