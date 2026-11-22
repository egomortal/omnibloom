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
- Other requests: an empty line is a probe; `version` answers `OMNI_STARTER_V4`; `pt` answers the kernel page-table pool (used, total) for Omni's memory guard; `quit` ends it (a newer starter sends
  this to take over the port). A refused or failed request gets a one-line `omni-starter: ...` answer.

**Safety checks (V3):**
- If it can't bind `127.0.0.1:9031` (an older starter won't let go), it exits. It never listens on any other address.
- Before loading a file it checks the ELF: 64-bit, position-independent (`ET_DYN`), lowest address 0, image at most
  1 GB, and every header, segment and relocation table inside the file. A cut-off or damaged file is refused (logged)
  instead of being read past its end.
- A process that fails to start is killed, never left stopped.
- Omni sends it only `/data/omni/native/<name>.elf`; on its first check each session it asks `version`, and if an older
  starter answers it starts the current one, which tells the old one to quit.

**Versions:** V1 chunked loading. V2 reaps finished engines (V1 left them as zombies), `quit`, takes over from an older
starter. V3 the safety checks above. V4 answers `pt` (Omni 0.5.4-bloom.4+ requires V4). `stop/` is a one-off helper that ended a V1 starter (V1 has no `quit`).

**Build** (PS5 payload SDK at `/opt/ps5-payload-sdk`): `make` -> `build/omni-starter.elf`.

**Licence:** GPL-3.0-or-later. `gpl/` is John Törnblom's ps5-payload-elfldr code (see `COPYING` and
[THIRD-PARTY-NOTICES.md](../../../THIRD-PARTY-NOTICES.md)); the changes are marked `OMNI_STARTER_V1` (chunked loading) and `Omni V3` in `gpl/elfldr.c`.
