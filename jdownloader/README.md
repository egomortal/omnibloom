# JDownloader 2 on the PS5: the engine

JDownloader 2 runs on the PS5 through Omni's downloads. Three pieces make that work:

| Piece | Who made it | Licence | Shipped how |
|---|---|---|---|
| `java-worker.elf`: native entry, watchdog, receipts, filesystem/space adapters (`engine/`) | Omnibloom | GPL-3.0-or-later | release asset `omnibloom-jd-engine-<ver>.zip` |
| Java 25 runtime (HotSpot + core libraries) linked into `java-worker.elf`, plus the runtime image under `native/java25/` | built from **[mateo-cogeanu/ps5-java25-homebrew](https://github.com/mateo-cogeanu/ps5-java25-homebrew)** (the PS5 Java 25 port) on **[freebsd/openjdk](https://github.com/freebsd/openjdk/tree/b219cdec88ca2e165711f63b8158ab78303facc8)** | OpenJDK: GPLv2 with the Classpath Exception; port tooling as its notices say | same release asset, notices unchanged under `notices/` |
| Bridge (`java/OmniJDownloaderBridge.java`) and an adapted JDownloader class (`java/upstream-adapted/…/MyJDownloaderController.java`) | Omnibloom (bridge); AppWork GmbH (JDownloader 2 source), adapted | GPL-3.0-or-later (JDownloader 2's open source is GPL-3.0) | compiled classes in the same release asset |
| **JDownloader 2 itself** | AppWork GmbH | partly closed-source | **never shipped**: Omnibloom Setup copies the user's own install |

**Credit:** the Java runtime exists because of mateo-cogeanu's PS5 Java 25 port. Thank you. Its OpenJDK parts are GPLv2 with the Classpath Exception; the complete corresponding source is the port at commit `db3ac845fa090c64e2a737d6c4222dd37867d7fe`, the OpenJDK fork at `b219cdec88ca2e165711f63b8158ab78303facc8`, and the patches and recipe in this folder.

## Reproducing java-worker.elf byte for byte

`recipe/replay.py` rebuilds the engine from pinned inputs, in a fresh private tree, by replaying the exact build chain (stages jd-002 → jd-008). Every stage re-checks the previous stage's ELF against the original's sha256, so the first difference (if any) is pinpointed.

Environment: Ubuntu 24.04 (WSL2 works), `clang-21`/`lld-21` from apt.llvm.org (Ubuntu clang 21.1.8), `gmake`, `git`, Python 3.12. It builds with 4 jobs, about 7 minutes on a 16-thread PC.

Inputs (`recipe/scripts/acquire.py` fetches and checks them; sha256):

| Input | Source | sha256 |
|---|---|---|
| port.tar.gz | github.com/mateo-cogeanu/ps5-java25-homebrew @ db3ac845… | `e7e73cc3f91135590c4d8b85bcd19de19e7ead16adab1c1bb08137df24062863` |
| openjdk.tar.gz | github.com/freebsd/openjdk @ b219cdec… | `dd52da87ee131a68e8d10d56f7a9adc82d322f0448dcd7438e16e9b8d070fd7a` |
| sdk-v0.42.zip | github.com/ps5-payload-dev/sdk release v0.42 | `8cfbc7cd5811e719eb4f0c47eea668d3dc7b40bc8ab11c4a5031d40c23ec02da` |
| host-jdk.tar.gz | Adoptium Temurin 25.0.4+7 (Linux x64, build tool only) | `e58fcdcd637b25c03ca84cbbcefc70d11efb8f4b4cbd05decc9f661769d77f94` |
| autoconf.tar.gz | GNU autoconf 2.72 | `afb181a76e1ee72832f6581c0eddf8df032b83e2e0239ef79ebedc4467d92d6e` |

Put the five files in one folder, then:

```
python3 recipe/make_layout.py . /tmp/jd-layout /path/to/downloads
OMNIBLOOM_JD_RUN=001 python3 recipe/replay.py recipe /tmp/jd-layout /tmp/jd-status
```

The status is in `/tmp/jd-status/replay-status-001.json`, and the results in `/tmp/jd-status/../build/run-001/`.

`replay.py` pins three strings so the build is identical: `--with-source-date=2026-10-26T06:26:45Z`, `--with-build-user=root` and `--with-version-opt=adhoc.root.openjdk-b219cdec88ca2e165711f63b8158ab78303facc8`.

### Result (2026-11-03)
- `java-worker.elf` matched the original at **every stage**; final `d761c256a9c1153b7e04aa87d2cff75531bd1631b1fa3e66f5185798f7429c2e` (32,549,920 bytes) is the ELF installed and tested on the console.
- The runtime image (`native-image.zip`) is identical in every class and resource. It differs only in (a) the 16-byte random GNU build-id inside each `.so`, and (b) 120 OpenJDK build bookkeeping files (`_the.*`) that carry the build machine's temporary path. Neither is used at run time. Releases ship the console-tested image `81e50f97…4463`.

## What's in this folder
- `engine/`: `java_worker.cpp` (final), the stage versions it grew from (`stages/`), and the adapters and their host tests.
- `openjdk-patches/`: the three OpenJDK files changed for real disk-space and mount reporting on PS5 (stage jd-008).
- `recipe/`: `replay.py` plus every build script (port patches, private SDK and AWT fixes, packaging, relinks).
- `java/`: the bridge, the adapted JDownloader class and the native-provider probe.
- `notices/`: the port's notices and OpenJDK's LICENSE, ADDITIONAL_LICENSE_INFO and ASSEMBLY_EXCEPTION, unchanged.

## Egress policy `omni-public-only-v1` (audit JD-03)
Every connection JDownloader 2 makes on the PS5 (plugins, redirects, sub-requests, the updater) can only reach
public addresses: never loopback, private, link-local, CGNAT, multicast, reserved or documentation ranges, and never
a subnet the console itself is on. The same rule as yt-dlp's guard in the downloads worker (`egress_guard.py`).
The bridge installs these layers before any JDownloader code runs, proves each with a self-test, and doesn't start
JDownloader at all if one is missing:

| Layer | Class | What it stops |
|---|---|---|
| Guard proxy on 127.0.0.1 | `OmniEgressPolicy` | resolves each target once, refuses unless every answer is public, pins the socket to the checked address (DNS rebinding), one request per connection |
| JDownloader's proxy list | `OmniEgressPolicy.JdProxies` | the guard is JD's only proxy; "no proxy", proxy auto-detection, reconnect, local UPnP IP checks and auto-update checks are off; re-verified on every health call |
| AppWork socket factory | `OmniEgressPolicy.JdSockets` | JD's HTTP stack may connect to the guard only, so a "no proxy" fallback fails instead of going direct |
| Every `java.net.Socket` | `OmniEgressPolicy.CheckedSocketImpl` | `Socket.setSocketImplFactory`: raw, SSL and "no proxy" URL sockets connect only to the guard or a public address; `java.net.URL` goes to the guard (ProxySelector) |
| JVM resolver | `OmniPublicResolverProvider` (+ `META-INF/services`) | names with any local/private answer fail JVM-wide |

The health reply carries `egress_policy: "omni-public-only-v1"` (and an `egress` object with each layer's state and
counters) only while all layers hold; replacing a layer at run time drops it for the rest of the session. The
downloads worker uses JDownloader only when that field is present, and the engine package's manifest declares
`jdownloader_engine.egress_policy`, which Setup requires before switching JDownloader 2 on.

Not covered, by design: NIO `SocketChannel`s opened directly, UDP, and a `java.net.Socket` built with an explicit
SOCKS/HTTP `Proxy` pointing at a literal private address. JDownloader's download paths use none of these (names in
them still go through the resolver).

PC tests: `java/tests/run_egress_tests.py` (address rules, every layer, DNS rebinding, redirects, public sites) and
`java/tests/bridge_e2e.py` (the real JDownloader 2 core behind the bridge). Both need your own JDownloader 2 folder.

## How Setup uses it
Omnibloom Setup (`setup/`) downloads the engine asset (or uses one next to Setup), copies the user's JDownloader 2, then runs two short checks on the PS5 before switching it on:
1. the Java runtime boots and its native parts work;
2. the user's JDownloader 2 starts with the bridge.

If either fails, JDownloader 2 stays off and yt-dlp keeps working.
