# Omni's ad block rule sets

Omni blocks ads with uBlock Origin's network engine (`engine/resources/ublock-engine.js`), running on the console from
a rule set compiled ahead of time. This folder builds those rule sets from current lists.

| File | What it is |
| --- | --- |
| `fetch-lists.sh` | Downloads uBlock Origin's lists (uBlock filters, EasyList, EasyPrivacy, annoyances...) into `lists/` |
| `compile-lists.cjs` | Compiles them, with Peter Lowe's host list and Omni's link-skip list, into `out/ublock-compiled-full.txt`; also writes the popup rules in `engine/resources/` |
| `promote.cjs` | Makes a compiled set the one Omnibloom ships: copies it to `engine/resources/ublock-compiled.txt` and writes `ublock-rules.json` (version and file hashes) |
| `peter-lowe-hosts.txt` | Peter Lowe's ad and tracker host list (<https://pgl.yoyo.org/adservers/>), with its own header and terms |
| `omni-link-skip.txt` | Omni's link-skip rules (go straight to the destination of known redirectors) |

## Refreshing the lists

```
sh fetch-lists.sh
node compile-lists.cjs
node promote.cjs 2026-11-20.1 "uBlock Origin default lists, EasyList, EasyPrivacy, annoyances, Peter Lowe's hosts"
```

Needs Node.js. `compile-lists.cjs` checks that the set loads in a bare runtime like the console's and stays under the
8 MiB Omni reads. Rule files are written with Unix line endings: with Windows ones Omni loads them but blocks nothing.

## How the update reaches consoles

Omnibloom Setup carries `engine/resources` and installs the rule files to `/data/omni/` with `ublock-rules.json`. On
Install or Repair it updates a console's rules only when **Setup installed them** and its own set is newer. Rules put
there by hand (any files without a `ublock-rules.json`, or one Setup never shipped) are never replaced.

**Memory:** a bigger set costs memory in Omni's network engine. Measure it on a console before shipping a much larger
set; the console's memory is tight while pages load.
