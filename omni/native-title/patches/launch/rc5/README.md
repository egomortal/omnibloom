# Launch build rc5 (2026-11-11): YouTube "stops at 1:00" fixed

rc5 is the launch build: **title rc5** on the rc2 title, and **child rc5** on the rc4 child (`../README.md`).

| | sha256 |
|---|---|
| title rc5 `eboot.bin` | `2e2a06a94af335901cbcc107a48886794f38fed02a629f523006891ee717d578` |
| child rc5 `omni-engine-child.elf` | `5b92d84061dc283ff33dc32bf558ad5b38ff5413353bdbc9384288ae307196ff` |
| rollback | title rc2 `100236b3…` + child rc4 `e48c0001…` |

## What was wrong

YouTube played about a minute and then stopped. Two causes, both in Omni:

1. **Omni's HTTP cache never stored a large response.** WebKit stores large bodies as a shared file and hard-links it next to the cache record. On the PS5's `/data` the hard-link call reports success without creating anything, so every large body (YouTube's player script, BotGuard's scripts, fonts, big images) was lost and re-downloaded on every visit. A cache built that way also stops YouTube's player from ever minting its PO token, so YouTube's stream protection never attests the session.
2. **YouTube rejects about half of the PO tokens Omni's player mints**, even with no extension or script in the page (2 of 4 runs stalled in two separate tests). Other YouTube clients report the same pattern (re-running BotGuard usually yields an accepted token).

## What rc5 changes

**Child** (`child/apply_nc_blob_copy.py`, `OMNI_NC_BLOB_COPY_V3`): the two link sites in `NetworkCacheBlobStorage.cpp` check that the link really produced the record's blob (same size); if not they copy it with plain POSIX I/O. Diagnostics: `/data/omni/ncblob.log` (first failure of each kind, a tally every 50). On the console the cache now keeps its large files, and YouTube's player script loads from the cache on repeat visits.

**Title** (`title/OmniYtGuard.h`):
- `OMNI_YT_ATTEST_GUARD_V1`: a page script on youtube.com `/watch` reads `STREAM_PROTECTION_STATUS` (UMP part 58) from each SABR response with a streaming walk (part types and the status number only, nothing else).
  - A request sent after GenerateIT that still gets "pending" means the token was rejected: the shell reloads the page (a new BotGuard run) at the current position, up to 5 times per video per tab.
  - "Pending" for 20 s with no token minted: one reload with the cache bypassed.
  - Kill switch `/data/omni/ytguard-off.flag`.
- `OMNI_NC_RESET_V1`: once per profile, before the data store is configured, the cache built by the old child is renamed to `NetworkCache.before-rc5-<time>`. Never deleted. Kill switch `/data/omni/nc-reset-off.flag`.

The title is built by `../../build/build-omni-ytguard-title.sh` (`MODE=ship`; `MODE=test` adds the diagnostic probe), and the child by `../../build/build-omni-launch-child.sh` (`VARIANT=rc5`).

## Console results (2026-11-11)

- The ship pairing on the user's profile, with a cache it built itself: **4/4 played to the end**. Runs 1-2 were attested first time; runs 3-4 needed one guard reload each.
- Installed as the launch build: **2/2 played to the end**. The one-time reset ran on the first start.
- Without the guard, rc5's cache alone: 2 of 4 stalled. The guard is what makes it reliable.

## Tests

`tests/guard_ump_test.js` (231 checks of the streaming UMP walk) and `tests/guard_sim_test.js` (the guard's decisions on the three console patterns plus an in-flight request) run with Node: `node tests/guard_ump_test.js`.

The build script also has `rc5np` (rc5 + the network profiler) and `rc6` (rc5 + `OMNI_JSC_JIT_V4`, a W^X JIT pool) variants. They are experimental and not part of this release.
