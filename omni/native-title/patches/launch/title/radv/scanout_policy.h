/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef EXBOX_SCANOUT_POLICY_H
#define EXBOX_SCANOUT_POLICY_H
#include <stdint.h>
#include <stdbool.h>
/* Numeric Vulkan values are checked against the SDK enums by the WSI build. */
#define EXBOX_BGRA8 44u
#define EXBOX_BGRA8_SRGB 50u
#define EXBOX_RGB10A2 64u
#define EXBOX_SRGB_SPACE 0u
#define EXBOX_PQ_SPACE 1000104008u
#define EXBOX_HDR_ATTRIBUTE UINT64_C(0x20000000)
static inline bool exbox_pair_valid(uint32_t format,uint32_t space) {
 return ((format==EXBOX_BGRA8||format==EXBOX_BGRA8_SRGB)&&space==EXBOX_SRGB_SPACE)||
        (format==EXBOX_RGB10A2&&space==EXBOX_PQ_SPACE);
}
static inline uint64_t exbox_scanout_format(uint32_t format,uint32_t space) {
 if(!exbox_pair_valid(format,space))return 0;
 return format==EXBOX_RGB10A2?UINT64_C(0x8100070422000000):UINT64_C(0x8000000000000000);
}
static inline bool exbox_wants_pq(bool full_screen,bool pq_content,uint64_t attributes) {
 return full_screen&&pq_content&&(attributes&EXBOX_HDR_ATTRIBUTE)!=0;
}
static inline bool exbox_range_matches(bool pq,uint32_t actual_range) {return actual_range==(pq?2u:1u);}
#endif
