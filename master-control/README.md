# Master Control

Master Control, the controller app that comes with Omnibloom, has its own repository:

**<https://github.com/egomortal/master-control>**

Its source, build instructions, supported controllers and releases (`master-control.elf`) are there.

How Omnibloom uses it:

- **Omni** opens Master Control's hub (the "Controllers" page) over its local web API, and passes the
  controller through to it with `window.omniPadController(action)`. Omni doesn't compile any Master
  Control code, so the two are built and released separately.
- **Omnibloom Setup** downloads the released `master-control.elf`, installs it and adds it to autoload.
- The hub's port is the one contract between them. If it changes, it changes in both: Master Control's
  `src/web.h` and `src/launcher.h`, and Omni's localhost allowlist (`OMNI_SEC_LOCALHOST_V1`) and page
  hooks (`OMNI_PAD_CONTROLLER_V1` in `omni/engine/entry/OmniBrowser.cpp`, `omni/engine/entry/OmniGamepad.h`).
