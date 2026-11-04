// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "OmniHdrColour.h"
#include <cstring>
namespace OmniMedia::Hdr {
// Snapshot at session initialization, never poll an environment/file per frame.
// Opt-in is a request, NOT proof of an HDR output. The renderer must confirm the
// registered format and output range before passing true to convertFrame().
class Experiment {
    bool requested_ = false;
public:
    explicit Experiment(const char* runtimeFlag = nullptr)
        : requested_(runtimeFlag && !std::strcmp(runtimeFlag,"1")) {}
    bool requested() const { return requested_; }
    bool convertFrame(bool pqOutputConfirmed,const Signal& s,Plane10 y,Plane10 u,Plane10 v,
        size_t w,size_t h,uint32_t* out,size_t count,size_t stride) const {
        return requested_ && pqOutputConfirmed && convert(s,y,u,v,w,h,out,count,stride);
    }
};
}
