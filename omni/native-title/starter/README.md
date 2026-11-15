# Omni engine starter (`omni-starter.elf`)

A small background program on the PS5 that starts Omni's engine processes (the page and network engines) for the Omni
app, in place of the payload loader (elfldr).

**Why:** elfldr reads the whole ~196 MB engine into its own memory and builds a second full-size copy to prepare it,
and it keeps that memory afterwards: about 240 MB, up to about 420 MB while starting two engines, at the moment Omni
loads a page and the console's memory is tightest. The starter maps the engine file read-only and prepares it in
16 MB pieces, then gives that memory back. Resident, it uses about 4 MB.

**How it runs:**
- Installed by Omnibloom Setup as `/data/omni/native/omni-starter.elf`.
- The Omni app starts it once through elfldr (it is small), then asks it for each engine process on
  `127.0.0.1:9031`, with the same one-line request elfldr understands: `file:<path>`.
- It listens on the console itself only (not the network), starts only `.elf` files directly in
  `/data/omni/native/`, one at a time, and logs to `/data/omni/native/starter.log`.
- If it isn't installed or doesn't answer, Omni uses elfldr as before. `/data/omni/starter-off.flag` makes Omni use
  elfldr always.

**Build** (PS5 payload SDK at `/opt/ps5-payload-sdk`): `make` -> `build/omni-starter.elf`.

**Licence:** GPL-3.0-or-later. `gpl/` is John Törnblom's ps5-payload-elfldr code (see `COPYING` and
[THIRD-PARTY-NOTICES.md](../../../THIRD-PARTY-NOTICES.md)); the change is marked `OMNI_STARTER_V1` in `gpl/elfldr.c`.
