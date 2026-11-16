"""The Omnibloom Setup window: a simple step-by-step guide for people who've never used FTP or payloads.

Steps: Welcome → Find your PS5 → Check → Choose apps → JDownloader 2 → Install → Done.
Or the one button on the Welcome page ("Install the full package (recommended)", or "Customize…" to untick apps and
options first): Setup waits for the PS5 and does every step
itself (oneclick.py), ticking off a checklist and saying what it's doing; "Undo this install" puts it all back.
Bloom Core is required and always installed first. Apps already on the PS5 are listed on the
"Installed apps" page with Update, Repair and Uninstall per app.
Slow work runs on a background thread; Tk variables are only read on the window's thread.
"""
import os
import queue
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from . import backup, bookmarks, checks, config, devflags, diagnostics, installer, jd, oneclick, ps5, release, shortcuts

C = config.COLORS
STATUS_MARK = {"ok": ("✓", C["ok"]), "warn": ("!", C["warn"]), "bad": ("✕", C["bad"]), "info": ("i", C["accent"])}
STEP_MARK = {"pending": ("·", C["muted"]), "active": ("…", C["accent"]), "ok": ("✓", C["ok"]), "fail": ("✕", C["bad"]),
             "skip": ("–", C["muted"]), "undone": ("↺", C["warn"])}
SUB_APPS = {"downloads": "Downloads (yt-dlp built in)", "files-broker": "USB file access"}


def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    return os.path.join(base, "assets", name)


class SetupApp:
    def __init__(self, root, test_ports=None):
        self.root = root
        self.ports = test_ports or {}
        self.q = queue.Queue()
        self.host = tk.StringVar(value=self.ports.get("host", ""))
        self.catalog = None
        self.catalog_error = None
        self.summary = None
        self.installed = {}
        self.pick = {g["id"]: tk.BooleanVar(value=True) for g in config.GROUPS}
        self.sub = {k: tk.BooleanVar(value=True) for k in SUB_APPS}
        self.autoload_mc = tk.BooleanVar(value=True)   # Master Control starts with the PS5 unless you untick it
        self.start_mc = tk.BooleanVar(value=True)
        self.jd_folder = tk.StringVar()
        self.jd_copy = tk.BooleanVar(value=False)
        self.job = {"mode": "install"}
        self.result = {}
        self.oc_cancel = threading.Event()
        self.oc_running = False
        self.oc_result = None
        # Customize (one-button with choices): everything on by default, like the full package.
        self.c_apps = {a: tk.BooleanVar(value=True) for a in ("omni", "downloads", "files-broker", "master-control")}
        self.c_jd = tk.BooleanVar(value=True)
        self.c_jd_get = tk.BooleanVar(value=True)
        self.c_hdr = tk.BooleanVar(value=True)

        root.title(config.APP_NAME)
        root.geometry("800x680")
        root.minsize(720, 640)
        root.configure(bg=C["ground"])
        try:
            self.icon = tk.PhotoImage(file=resource("omnibloom-256.png"))
            root.iconphoto(True, self.icon)
            self.logo = self.icon.subsample(2, 2)
        except tk.TclError:
            self.icon = self.logo = None
        self._style()

        bar = tk.Frame(root, bg=C["ground"])           # packed first so it never scrolls off
        bar.pack(side="bottom", fill="x", padx=28, pady=(0, 18))
        self.body = tk.Frame(root, bg=C["ground"])
        self.body.pack(fill="both", expand=True, padx=28, pady=(18, 8))
        self.back_btn = ttk.Button(bar, text="Back", style="Ghost.TButton", command=self.back)
        self.back_btn.pack(side="left")
        self.next_btn = ttk.Button(bar, text="Next", style="Accent.TButton", command=self.next)
        self.next_btn.pack(side="right")
        self.steps = [self.page_welcome, self.page_find, self.page_check, self.page_choose, self.page_jd,
                      self.page_work, self.page_done]
        self.step = 0
        self.show(0)
        root.after(100, self._pump)

    # -- look -----------------------------------------------------------------
    def _style(self):
        s = ttk.Style(self.root)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        base = ("Segoe UI", 11) if sys.platform.startswith("win") else ("Helvetica", 12)
        self.f_body, self.f_small = base, (base[0], base[1] - 1)
        self.f_title = (base[0], base[1] + 11, "bold")
        self.f_head = (base[0], base[1] + 3, "bold")
        s.configure(".", background=C["ground"], foreground=C["text"], font=base)
        for w in ("TCheckbutton", "TRadiobutton", "Panel.TCheckbutton"):
            s.configure(w, indicatorbackground=C["ground"], indicatorforeground=C["accent"], indicatorcolor=C["ground"])
            s.map(w, indicatorcolor=[("selected", C["accent"])])
        for w in ("TCheckbutton", "TRadiobutton"):
            s.configure(w, background=C["ground"], foreground=C["text"])
            s.map(w, background=[("active", C["ground"])], foreground=[("disabled", C["muted"])])
        s.configure("Panel.TCheckbutton", background=C["panel"], foreground=C["text"])
        s.map("Panel.TCheckbutton", background=[("active", C["panel"])], foreground=[("disabled", C["muted"])])
        s.configure("Accent.TButton", background=C["accent"], foreground=C["ink_on_accent"], padding=(18, 8), borderwidth=0,
                    font=(base[0], base[1], "bold"))
        s.map("Accent.TButton", background=[("disabled", "#2A3B4A"), ("active", C["accent_light"])], foreground=[("disabled", C["muted"])])
        s.configure("Ghost.TButton", background=C["panel"], foreground=C["text"], padding=(16, 8), borderwidth=0)
        s.configure("Alt.TButton", background="#1C3042", foreground=C["text"], padding=(18, 8), borderwidth=0)   # on a panel
        s.map("Alt.TButton", background=[("active", "#264058")])
        s.map("Ghost.TButton", background=[("active", "#1A2A38"), ("disabled", C["ground"])], foreground=[("disabled", "#3A4A58")])
        s.configure("Small.TButton", background="#16242F", foreground=C["text"], padding=(10, 4), borderwidth=0)
        s.map("Small.TButton", background=[("active", "#1F3141"), ("disabled", C["panel"])], foreground=[("disabled", "#3A4A58")])
        s.configure("Horizontal.TProgressbar", troughcolor=C["panel"], background=C["accent"], bordercolor=C["panel"],
                    lightcolor=C["accent"], darkcolor=C["accent_dark"])
        s.configure("TEntry", fieldbackground=C["panel"], foreground=C["text"], insertcolor=C["text"])

    def label(self, parent, text, kind="body", **kw):
        font = {"title": self.f_title, "head": self.f_head, "small": self.f_small}.get(kind, self.f_body)
        fg = C["muted"] if kind in ("muted", "small") else C["text"]
        return tk.Label(parent, text=text, font=font, fg=kw.pop("fg", fg), bg=kw.pop("bg", C["ground"]),
                        justify="left", anchor="w", wraplength=kw.pop("wrap", 700), **kw)

    def panel(self, parent):
        return tk.Frame(parent, bg=C["panel"], padx=16, pady=8)

    # -- navigation ------------------------------------------------------------
    def show(self, index):
        self.step = index
        self._clear()
        self.next_btn.configure(text="Next", state="normal", command=self.next)
        self.back_btn.configure(state="normal" if 0 < index < 5 else "disabled", command=self.back)
        self.steps[index]()

    def _clear(self):
        for w in self.body.winfo_children():
            w.destroy()

    def next(self):
        handler = getattr(self, "_next_" + self.steps[self.step].__name__[5:], None)
        if handler and handler() is False:
            return
        if self.step < len(self.steps) - 1:
            self.show(self.step + 1)
        else:
            self.root.destroy()

    def back(self):
        if self.step > 0:
            self.show(self.step - 1)

    def run_bg(self, fn, done):
        def work():
            try:
                self.q.put((done, fn(), None))
            except Exception as e:  # shown to the user in plain words
                self.q.put((done, None, e))
        threading.Thread(target=work, daemon=True).start()

    def _pump(self):
        try:
            while True:
                item = self.q.get_nowait()
                if callable(item):
                    item()
                else:
                    done, result, err = item
                    done(result, err)
        except queue.Empty:
            pass
        self.root.after(80, self._pump)

    def console(self, host):
        return ps5.Console(host, ftp_port=self.ports.get("ftp"), loader_port=self.ports.get("loader"),
                           websrv_port=self.ports.get("websrv"), launcher_port=self.ports.get("launcher"))

    # -- 1. welcome -------------------------------------------------------------
    def page_welcome(self):
        top = tk.Frame(self.body, bg=C["ground"])
        top.pack(fill="x", pady=(10, 18))
        if self.logo:
            tk.Label(top, image=self.logo, bg=C["ground"]).pack(side="left", padx=(0, 18))
        words = tk.Frame(top, bg=C["ground"])
        words.pack(side="left", fill="x")
        self.label(words, "Omnibloom", "title").pack(anchor="w")
        self.label(words, config.TAGLINE, "muted").pack(anchor="w")
        self.label(self.body, "Omnibloom Setup puts the Omnibloom apps on your PS5 over your home network. You can add, "
                              "update or remove apps any time.").pack(anchor="w", pady=(0, 10))
        p = self.panel(self.body)
        p.pack(fill="x")
        self.label(p, "Before you start", "head", bg=C["panel"]).pack(anchor="w")
        for line in ("Your PS5 is jailbroken and on the same network as this computer.",
                     "ShadowMountPlus and kstuff are loaded (Omnibloom needs both).",
                     "Your payload loader and FTP server are running (most jailbreak setups start them for you)."):
            self.label(p, "•  " + line, bg=C["panel"]).pack(anchor="w", pady=2)
        one = self.panel(self.body)
        one.pack(fill="x", pady=(10, 0))
        self.label(one, "One button: press it and sit back", "head", bg=C["panel"]).pack(anchor="w")
        self.label(one, "Setup waits for your PS5 to come on, then installs Bloom Core, Omni, Downloads, USB file access, "
                        "Master Control and your JDownloader 2 one at a time, checks each one, and tells you what it's doing. "
                        "If anything goes wrong it puts your PS5 back as it was.", "small",
                   bg=C["panel"]).pack(anchor="w", pady=(2, 8))
        row = tk.Frame(one, bg=C["panel"])
        row.pack(fill="x")
        ttk.Button(row, text="Install the full package (recommended)", style="Accent.TButton",
                   command=self.page_oneclick).pack(side="left")
        ttk.Button(row, text="Customize…", style="Alt.TButton", command=self.page_customize).pack(side="left", padx=(10, 0))
        addr = tk.Frame(one, bg=C["panel"])
        addr.pack(fill="x", pady=(8, 0))
        if not self.host.get():
            self.host.set(oneclick._remembered_host() or "")
        self.label(addr, "PS5 address (optional; Setup finds it by itself):", "small", bg=C["panel"], wrap=0).pack(side="left", padx=(0, 6))
        ttk.Entry(addr, textvariable=self.host, width=16).pack(side="left")
        self.label(self.body, "Advanced: press Next to go through each step yourself. Nothing is deleted from your PS5. Anything "
                              "Setup replaces is kept as a backup, and Uninstall puts it back.", "small").pack(anchor="w", pady=(10, 0))

    # -- customize (the one button, with your choices) --------------------------------
    def page_customize(self):
        self._clear()
        self.label(self.body, "Customize", "title").pack(anchor="w")
        self.label(self.body, "Untick what you don't want, then press Install. Setup still does every step for you.",
                   "muted").pack(anchor="w", pady=(2, 10))
        box = self.panel(self.body)
        box.pack(fill="x")

        def tick(text, var, indent=0, state="normal"):
            w = ttk.Checkbutton(box, text=text, variable=var, style="Panel.TCheckbutton", state=state)
            w.pack(anchor="w", padx=(indent, 0), pady=1)
            return w
        core = tk.BooleanVar(value=True)
        self._c_core = core
        tick("%s (required: lets the apps work together)" % config.HUB_NAME, core, state="disabled")
        tick("Omni: the web browser", self.c_apps["omni"])
        tick("Downloads: save videos and files (yt-dlp built in)", self.c_apps["downloads"])
        tick("USB file access: open and save files on USB drives", self.c_apps["files-broker"])
        tick("Master Control: use other controllers", self.c_apps["master-control"])
        mc_now = tick("Start it now", self.start_mc, indent=24)
        mc_boot = tick("Start it with the PS5 (takes PadBridge's / EeveeLution's place)", self.autoload_mc, indent=24)
        jd_tick = tick("JDownloader 2: your own copy, through Downloads", self.c_jd)
        jd_row = tk.Frame(box, bg=C["panel"])
        jd_row.pack(fill="x", padx=(24, 0), pady=1)
        if not self.jd_folder.get():
            found = jd.detect()
            if found:
                self.jd_folder.set(found[0])
        self.label(jd_row, "Folder (empty: Setup looks for it):", "small", bg=C["panel"], wrap=0).pack(side="left")
        jd_entry = ttk.Entry(jd_row, textvariable=self.jd_folder, width=34)
        jd_entry.pack(side="left", padx=6)
        jd_browse = ttk.Button(jd_row, text="Browse…", style="Small.TButton", command=self._browse_jd_folder)
        jd_browse.pack(side="left")
        jd_get = tick("If it isn't on this computer, open the official download page for me and wait", self.c_jd_get, indent=24)
        tick("Set Omni's HDR to Auto (only if you haven't picked an HDR setting)", self.c_hdr)

        def refresh(*_):
            mc = "normal" if self.c_apps["master-control"].get() else "disabled"
            for w in (mc_now, mc_boot):
                w.configure(state=mc)
            dl = self.c_apps["downloads"].get()
            jd_tick.configure(state="normal" if dl else "disabled")
            on = dl and self.c_jd.get()
            for w in (jd_entry, jd_browse, jd_get):
                w.configure(state="normal" if on else "disabled")
        for var in (self.c_apps["master-control"], self.c_apps["downloads"], self.c_jd):
            var.trace_add("write", refresh)
        refresh()
        self.label(self.body, "Bloom Core is always installed first. Everything you leave out can be added later by running Setup "
                              "again.", "small").pack(anchor="w", pady=(10, 0))
        self.back_btn.configure(state="normal", command=lambda: self.show(0))
        self.next_btn.configure(text="Install", state="normal", command=lambda: self.page_oneclick(customized=True))

    def _browse_jd_folder(self):
        folder = filedialog.askdirectory(title="Pick your JDownloader 2 folder")
        if folder:
            self.jd_folder.set(folder)

    def customized_choices(self):
        """The Customize ticks as OneClick options (read on the window's thread)."""
        apps = [a for a, v in self.c_apps.items() if v.get()]
        mc = "master-control" in apps
        jd_on = "downloads" in apps and self.c_jd.get()
        return {"apps": apps, "master_control": mc, "start_master_control": mc and self.start_mc.get(),
                "autoload_master_control": mc and self.autoload_mc.get(), "jdownloader": jd_on,
                "jd_folder": (self.jd_folder.get().strip() or None) if jd_on else None,
                "get_jdownloader": jd_on and self.c_jd_get.get(), "hdr": "auto-if-unset" if self.c_hdr.get() else "keep"}

    # -- the one button ------------------------------------------------------------
    def page_oneclick(self, customized=False):
        choice = self.customized_choices() if customized else None
        self._clear()
        self.label(self.body, "Installing your choices" if customized else "Installing the full package", "title").pack(anchor="w")
        self.label(self.body, "Setup does each step for you and says what it's doing. Keep this window open and your PS5 on.",
                   "muted").pack(anchor="w", pady=(2, 10))
        lst = tk.Frame(self.body, bg=C["panel"], padx=12, pady=6)
        lst.pack(fill="x")
        self.oc_rows = {}
        for key, name in oneclick.STEPS:
            row = tk.Frame(lst, bg=C["panel"])
            row.pack(fill="x")
            mark = tk.Label(row, text=STEP_MARK["pending"][0], fg=STEP_MARK["pending"][1], bg=C["panel"], font=self.f_body, width=2)
            mark.pack(side="left")
            tk.Label(row, text=name, fg=C["text"], bg=C["panel"], font=self.f_small, width=22, anchor="w").pack(side="left")
            note = tk.Label(row, text="", fg=C["muted"], bg=C["panel"], font=self.f_small, anchor="w", justify="left", wraplength=470)
            note.pack(side="left", fill="x", expand=True)
            self.oc_rows[key] = (mark, note)
        self.bar = ttk.Progressbar(self.body, mode="determinate")
        self.bar.pack(fill="x", pady=(10, 0))
        self.oc_actions = tk.Frame(self.body, bg=C["ground"])
        self.oc_actions.pack(side="bottom", fill="x")   # packed first so the log shrinks, not the buttons
        self.logbox = tk.Text(self.body, height=8, bg=C["panel"], fg=C["muted"], bd=0, highlightthickness=0, font=self.f_small, wrap="word")
        self.logbox.pack(fill="both", expand=True, pady=(8, 4))
        self.back_btn.configure(state="disabled")
        self.next_btn.configure(text="Stop", state="normal", command=self._oc_stop)
        self.oc_cancel = threading.Event()
        self.oc_running = True
        self.oc_result = None
        host = self.host.get().strip() or None
        nets = None
        if self.ports.get("host"):   # test mode: the fake PS5 is on this computer
            import ipaddress
            nets = [ipaddress.ip_network(self.ports["host"] + "/30", strict=False)]
        if choice is None:   # the full package: everything, Master Control started now and with the PS5, HDR Auto if unset
            choice = {"apps": None, "master_control": True, "start_master_control": True, "autoload_master_control": True,
                      "jdownloader": True, "jd_folder": self.jd_folder.get().strip() or None, "get_jdownloader": False,
                      "hdr": "auto-if-unset"}
        self.oc_choice = choice
        confirm = (lambda question: True) if choice.pop("get_jdownloader") else self._ask_from_worker
        oc = oneclick.OneClick(host=host, ftp_port=self.ports.get("ftp"), loader_port=self.ports.get("loader"),
                               websrv_port=self.ports.get("websrv"), launcher_port=self.ports.get("launcher"), catalog=self.catalog,
                               catalog_loader=lambda log: release.load_catalog(log=log),
                               report=lambda e: self.q.put(lambda: self._oc_event(e)), progress=self._progress,
                               cancel=self.oc_cancel, networks=nets, confirm=confirm, auto_backup=True, **choice)
        self.run_bg(oc.run, lambda result, err: self._oc_done(oc, result, err))

    def _ask_from_worker(self, question):
        """Yes/No asked on the window's thread for the one-button worker thread (which waits for the answer)."""
        answer, done = [False], threading.Event()

        def ask():
            try:
                answer[0] = self.ask_yes_no(question)
            finally:
                done.set()
        self.q.put(ask)
        done.wait()
        return answer[0]

    def ask_yes_no(self, question):   # tests replace this
        return messagebox.askyesno(config.APP_NAME, question)

    def _oc_event(self, e):
        if not self.logbox.winfo_exists():
            return
        if e.get("step") in self.oc_rows:
            mark, note = self.oc_rows[e["step"]]
            sym, color = STEP_MARK.get(e["state"], STEP_MARK["pending"])
            mark.configure(text=sym, fg=color)
            note.configure(text=e.get("text", ""), fg=C["bad"] if e["state"] == "fail" else C["muted"])
            if e["state"] == "active":
                self.bar.configure(value=0)
        if e.get("text"):
            self.logbox.insert("end", e["text"] + "\n")
            self.logbox.see("end")

    def _oc_stop(self):
        if self.oc_running:
            self.oc_cancel.set()
            self._oc_event({"text": "Stopping when the current wait ends (an install that has started finishes or is put back first)…"})
            self.next_btn.configure(state="disabled")
        else:
            self.root.destroy()

    def _oc_done(self, oc, result, err):
        self.oc_running = False
        self.oc_result = result or {}
        if oc.host:
            self.host.set(oc.host)
        if oc.catalog is not None:
            self.catalog = oc.catalog
        if not self.logbox.winfo_exists():
            return
        if err:
            self._oc_event({"text": "Stopped: %s" % err})
        self.next_btn.configure(text="Close", state="normal", command=self._oc_stop)
        self.back_btn.configure(state="normal", command=lambda: self.show(0))
        for w in self.oc_actions.winfo_children():
            w.destroy()
        if self.oc_result.get("ok"):
            mc = self.oc_result["installed"].get("master-control")
            if mc and mc.get("port"):
                self.label(self.oc_actions, "Master Control's menu: http://%s:%d/  (also from Omni)" % (oc.host, mc["port"]),
                           "small").pack(anchor="w")
            ttk.Button(self.oc_actions, text="Undo this install", style="Ghost.TButton", command=self._oc_undo).pack(side="left", pady=4)
            ttk.Button(self.oc_actions, text="Controller shortcuts…", style="Ghost.TButton",
                       command=self.show_shortcuts).pack(side="left", padx=8, pady=4)
        else:
            again = self.page_customize if self.oc_choice.get("apps") is not None else self.page_oneclick
            ttk.Button(self.oc_actions, text="Try again", style="Accent.TButton", command=again).pack(side="left", pady=4)

    def _oc_undo(self, confirm=True):
        host = self.host.get().strip()
        if confirm and not messagebox.askyesno(
                config.APP_NAME, "Put your PS5 back the way it was before this install?\n\nApps that are running keep "
                                 "running until the PS5 restarts. Your own data is kept."):
            return
        for w in self.oc_actions.winfo_children():
            w.destroy()
        self.next_btn.configure(state="disabled")
        self.back_btn.configure(state="disabled")
        self.oc_undo_result = None
        report = lambda e: self.q.put(lambda: self._oc_event(e))

        def done(ok, err):
            self.oc_undo_result = bool(ok)
            if err:
                self._oc_event({"text": "Undo stopped: %s" % err})
            self.next_btn.configure(state="normal")
            self.back_btn.configure(state="normal")
        self.run_bg(lambda: oneclick.undo_last(host, ftp_port=self.ports.get("ftp"), loader_port=self.ports.get("loader"),
                                               websrv_port=self.ports.get("websrv"), report=report), done)

    # -- 2. find -----------------------------------------------------------------
    def page_find(self):
        self.label(self.body, "Find your PS5", "title").pack(anchor="w")
        self.label(self.body, "Looking for PS5s on your network…", "muted").pack(anchor="w", pady=(2, 12))
        self.scan_bar = ttk.Progressbar(self.body, mode="determinate")
        self.scan_bar.pack(fill="x")
        self.found_box = tk.Frame(self.body, bg=C["ground"])
        self.found_box.pack(fill="x", pady=12)
        manual = tk.Frame(self.body, bg=C["ground"])
        manual.pack(fill="x", pady=(8, 0))
        self.label(manual, "Or type your PS5's IP address:", wrap=0).pack(side="left")
        ttk.Entry(manual, textvariable=self.host, width=18).pack(side="left", padx=10)
        ttk.Button(manual, text="Search again", style="Ghost.TButton", command=self._start_scan).pack(side="right")
        self.label(self.body, "Tip: the address is on your PS5 under Settings → Network → Connection Status.", "small").pack(anchor="w", pady=(12, 0))
        self._start_scan()
        if self.catalog is None:   # start fetching the apps while the user finds the PS5
            self.run_bg(lambda: release.load_catalog(log=lambda m: None), self._catalog_done)

    def _catalog_done(self, cat, err):
        self.catalog, self.catalog_error = cat, err

    def _start_scan(self):
        self.scan_bar["value"] = 0
        for w in self.found_box.winfo_children():
            w.destroy()

        def prog(done, total):
            self.q.put(lambda: self.scan_bar.winfo_exists() and self.scan_bar.configure(maximum=total, value=done))
        nets = None
        if self.ports.get("host"):  # test mode: the fake PS5 is on this computer
            import ipaddress
            nets = [ipaddress.ip_network(self.ports["host"] + "/30", strict=False)]
        self.run_bg(lambda: ps5.scan(nets, progress=prog, ftp_port=self.ports.get("ftp"), loader_port=self.ports.get("loader"),
                                     websrv_port=self.ports.get("websrv")),
                    self._scan_done)

    def _scan_done(self, found, err):
        if not self.found_box.winfo_exists():
            return
        self.scan_bar["value"] = self.scan_bar["maximum"]
        if err or not found:
            self.label(self.found_box, "No PS5 found automatically. Check it's on and jailbroken, or type its address below.",
                       fg=C["warn"]).pack(anchor="w")
            return
        for f in found:
            note = "ready" if f["ftp"] else "PS5 found, but its FTP server isn't running: load your FTP payload (ftpsrv)"
            ttk.Radiobutton(self.found_box, text="%s   (%s)" % (f["host"], note), value=f["host"], variable=self.host).pack(anchor="w", pady=2)
        if not self.host.get():
            self.host.set(found[0]["host"])

    def _next_find(self):
        if not self.host.get().strip():
            messagebox.showinfo(config.APP_NAME, "Pick your PS5 or type its IP address first.")
            return False

    # -- 3. check ----------------------------------------------------------------
    def page_check(self):
        self.label(self.body, "Checking your PS5", "title").pack(anchor="w")
        self.check_note = self.label(self.body, "Reading your PS5's setup (about 20 seconds; nothing is changed)…", "muted")
        self.check_note.pack(anchor="w", pady=(2, 12))
        self.check_box = tk.Frame(self.body, bg=C["ground"])
        self.check_box.pack(fill="both", expand=True)
        self.next_btn.configure(state="disabled")
        host = self.host.get().strip()
        self.run_bg(lambda: self._do_checks(host), self._checks_done)
        if self.catalog is None and self.catalog_error is not None:
            self.catalog_error = None
            self.run_bg(lambda: release.load_catalog(log=lambda m: None), self._catalog_done)

    def _do_checks(self, host):
        with self.console(host) as c:
            result = checks.run_checks(c)
            from . import autobackup                            # S06: opt-in, at most once a day
            autobackup.maybe_run(c)
            return result

    def _checks_done(self, result, err):
        if not self.check_box.winfo_exists():
            return
        if err:
            self.check_note.configure(text="Couldn't reach the PS5 at %s. Is its FTP server running?\n(%s)" % (self.host.get(), err), fg=C["bad"])
            ttk.Button(self.check_box, text="Check again", style="Ghost.TButton", command=lambda: self.show(self.step)).pack(anchor="w")
            return
        items, self.summary = result
        self.installed = self.summary.get("installed") or {}
        self.check_note.configure(text="Here's what we found:")
        for it in items:
            row = tk.Frame(self.check_box, bg=C["panel"], padx=12, pady=7)
            row.pack(fill="x", pady=3)
            mark, color = STATUS_MARK[it["status"]]
            tk.Label(row, text=mark, font=self.f_head, fg=color, bg=C["panel"], width=2).pack(side="left", anchor="n")
            t = tk.Frame(row, bg=C["panel"])
            t.pack(side="left", fill="x", expand=True)
            self.label(t, it["label"], "head", bg=C["panel"]).pack(anchor="w")
            self.label(t, it["detail"], "small", bg=C["panel"], wrap=620).pack(anchor="w")
        actions = tk.Frame(self.check_box, bg=C["ground"])
        actions.pack(fill="x", pady=10)
        ttk.Button(actions, text="Check again", style="Ghost.TButton", command=lambda: self.show(self.step)).pack(side="left")
        if self.installed:
            ttk.Button(actions, text="Installed apps…", style="Ghost.TButton", command=self.page_manage).pack(side="left", padx=8)
        # Technical logs only, personal data redacted, previewed, saved on this PC: for bug reports (nothing is uploaded)
        ttk.Button(actions, text="Save a diagnostics bundle…", style="Ghost.TButton",
                   command=self.page_diagnostics).pack(side="left", padx=8)
        # Same bundle, redacted again, reviewed in full, then a pre-filled GitHub issue (bug_report.py; no upload)
        ttk.Button(actions, text="Report a bug…", style="Ghost.TButton",
                   command=self.page_bug_report).pack(side="left", padx=(0, 8))
        # What Omni uses on the PS5, with confirmed clean-ups of caches, trash and old copies (storage.py)
        ttk.Button(actions, text="Storage on the PS5…", style="Ghost.TButton",
                   command=self.page_storage).pack(side="left")
        ttk.Button(actions, text="Advanced: Omni developer flags…", style="Ghost.TButton",
                   command=self.page_devflags).pack(side="right")
        more = tk.Frame(self.check_box, bg=C["ground"])
        more.pack(fill="x")
        ttk.Button(more, text="Import bookmarks from this PC…", style="Ghost.TButton", command=self.page_bookmarks).pack(side="left")
        ttk.Button(more, text="Sync bookmarks…", style="Ghost.TButton",
                   command=lambda: self.page_bookmarks(sync=True)).pack(side="left", padx=(8, 0))
        ttk.Button(more, text="Import read later…", style="Ghost.TButton",
                   command=self.readlater_window).pack(side="left", padx=(8, 0))
        ttk.Button(more, text="Most visited sites…", style="Ghost.TButton",   # S14 (topsites.py)
                   command=self.topsites_window).pack(side="left", padx=(8, 0))
        ttk.Button(more, text="Back up Omni…", style="Ghost.TButton", command=self.page_backup).pack(side="left", padx=8)
        ttk.Button(more, text="Restore Omni backup…", style="Ghost.TButton", command=self.page_restore).pack(side="left")
        ttk.Button(more, text="Export reading list…", style="Ghost.TButton",
                   command=self.page_reading_list).pack(side="left", padx=(8, 0))
        copy_row = tk.Frame(self.check_box, bg=C["ground"])     # screenshots + saved downloads -> this PC (pccopy)
        copy_row.pack(fill="x", pady=(8, 0))
        ttk.Button(copy_row, text="Copy from PS5…", style="Ghost.TButton",
                   command=self.page_copy_to_pc).pack(side="left")
        link_row = tk.Frame(self.check_box, bg=C["ground"])     # OMNI_PC_LINKS_V1: a link from this PC -> Omni (pclinks)
        link_row.pack(fill="x", pady=(8, 0))
        ttk.Button(link_row, text="Send a link to Omni…", style="Ghost.TButton",
                   command=self.page_send_link).pack(side="left")
        se_row = tk.Frame(self.check_box, bg=C["ground"])       # S04: search-shortcuts.txt / quick-access.txt editor
        se_row.pack(fill="x", pady=(8, 0))
        ttk.Button(se_row, text="Search shortcuts and Quick access…", style="Ghost.TButton",
                   command=self.page_shortcuts_edit).pack(side="left")
        mf_row = tk.Frame(self.check_box, bg=C["ground"])       # S10: ublock-user-filters.txt ("My filters") editor
        mf_row.pack(fill="x", pady=(8, 0))
        ttk.Button(mf_row, text="My filters…", style="Ghost.TButton",
                   command=self.page_filters_edit).pack(side="left")
        ttk.Button(mf_row, text="Omni add-ons…", style="Ghost.TButton",      # S12: push / list / remove user add-ons
                   command=self.page_addons).pack(side="left", padx=(8, 0))
        bi_row =tk.Frame(self.check_box, bg=C["ground"])       # S05: look inside a backup, restore single items
        bi_row.pack(fill="x", pady=(8, 0))
        ttk.Button(bi_row, text="Inspect a backup…", style="Ghost.TButton",
                   command=self.page_backup_inspect).pack(side="left")
        sr_row = tk.Frame(self.check_box, bg=C["ground"])       # S08: reset Omni settings (backup first, undo)
        sr_row.pack(fill="x", pady=(8, 0))
        ttk.Button(sr_row, text="Reset Omni settings…", style="Ghost.TButton",
                   command=self.page_settings_reset).pack(side="left")
        ttk.Button(sr_row, text="All Omni settings…", style="Ghost.TButton",   # S15: settings editor (settings_editor.py)
                   command=self.page_settings_editor).pack(side="left", padx=(8, 0))
        from . import autobackup                              # S06: automatic backup when the PS5 is found
        ab_row = tk.Frame(self.check_box, bg=C["ground"])
        ab_row.pack(fill="x", pady=(8, 0))
        ab_line = self.label(ab_row, autobackup.status_line(), "small", wrap=0)
        ttk.Button(ab_row, text="Automatic backup…", style="Ghost.TButton", command=lambda: autobackup.open_window(
            self.root, on_change=lambda: ab_line.configure(text=autobackup.status_line()))).pack(side="left")
        ab_line.pack(side="left", padx=8)
        if self.summary["can_install"]:
            self.next_btn.configure(state="normal")

    def _need_catalog(self):
        if self.catalog:
            return True
        msg = "Still getting the Omnibloom apps. Try again in a moment."
        if self.catalog_error:
            msg = ("Couldn't get the Omnibloom apps: %s\n\nCheck your internet connection, or put the console package "
                   "zips from the release pages next to this setup file." % self.catalog_error)
        messagebox.showinfo(config.APP_NAME, msg)
        return False

    def _next_check(self):
        return None if self._need_catalog() else False

    # -- installed apps (from the check page) -------------------------------------
    def page_manage(self):
        if not self._need_catalog():
            return
        self._clear()
        self.next_btn.configure(state="disabled")
        self.back_btn.configure(state="normal")
        self.label(self.body, "Installed apps", "title").pack(anchor="w")
        self.label(self.body, "Update, repair or remove one app at a time. The others keep working.", "muted").pack(anchor="w", pady=(2, 12))
        order = [config.HUB_ID] + sorted(a for a in self.installed if a != config.HUB_ID)
        for app_id in [a for a in order if a in self.installed]:
            rec = self.installed[app_id]
            row = self.panel(self.body)
            row.pack(fill="x", pady=3)
            words = tk.Frame(row, bg=C["panel"])
            words.pack(side="left", fill="x", expand=True)
            self.label(words, rec["name"], "head", bg=C["panel"]).pack(anchor="w")
            latest = self.catalog.apps.get(app_id, {}).get("version")
            note = "Version %s" % rec["version"]
            if installer.update_available(rec["version"], latest):
                note += "  ·  update to %s available" % latest
            if rec.get("port"):
                note += "  ·  port %d" % rec["port"]
            self.label(words, note, "small", bg=C["panel"]).pack(anchor="w")
            lone_core = app_id == config.HUB_ID and len(self.installed) > 1
            ttk.Button(row, text="Uninstall", style="Small.TButton", state="disabled" if lone_core else "normal",
                       command=lambda a=app_id: self._confirm_uninstall(a)).pack(side="right", padx=(6, 0))
            ttk.Button(row, text="Repair", style="Small.TButton", state="normal" if self.catalog.has(app_id) else "disabled",
                       command=lambda a=app_id: self._start_job({"mode": "repair", "app": a})).pack(side="right")
        self.label(self.body, "%s stays while other apps are installed. To update apps, go Back and press Next."
                   % config.HUB_NAME, "small").pack(anchor="w", pady=(10, 0))

    def _confirm_uninstall(self, app_id):
        name = self.installed[app_id]["name"]
        if messagebox.askyesno(config.APP_NAME, "Remove %s from this PS5?\n\nIts earlier files are put back. Your browsing "
                                                "data, downloads and controller pairings are kept." % name):
            self._start_job({"mode": "uninstall", "app": app_id})

    def _start_job(self, job):
        self.job = job
        self.show(5)

    # -- S14: most-visited sites from this PC's browser history -> Omni's "Most visited" bookmarks folder (topsites.py) --
    def topsites_window(self):
        from . import bookmarks as bm, topsites as ts
        win = tk.Toplevel(self.root)
        win.title("Most visited sites")
        win.configure(bg=C["ground"])
        win.transient(self.root)
        tk.Label(win, text="Find the sites you visit most in this PC's browsers (Chrome, Edge, Brave, Firefox) and add their "
                           "home pages to Omni's \"%s\" bookmarks folder. Nothing is read until you press Find; you see "
                           "the list first and can untick sites. Only the chosen home pages go to the PS5. Close Omni on "
                           "the PS5 first." % ts.FOLDER,
                 font=self.f_body, fg=C["text"], bg=C["ground"], wraplength=520, justify="left").pack(anchor="w", padx=14, pady=(12, 6))
        listbox = tk.Frame(win, bg=C["ground"])
        listbox.pack(fill="x", padx=14)
        note = tk.Label(win, text="", font=self.f_small, fg=C["text"], bg=C["ground"], wraplength=520, justify="left")
        note.pack(anchor="w", padx=14, pady=6)
        btns = tk.Frame(win, bg=C["ground"])
        btns.pack(fill="x", padx=14, pady=(0, 12))
        ttk.Button(btns, text="Close", style="Ghost.TButton", command=win.destroy).pack(side="right")
        found, ticks = [], []

        def shown(sites, err):
            if not win.winfo_exists():
                return
            find.configure(state="normal")
            if err:
                note.configure(text="Couldn't read the browsers' history: %s" % err, fg=C["bad"])
                return
            found[:] = sites
            ticks[:] = []
            for w in listbox.winfo_children():
                w.destroy()
            for s in sites:
                v = tk.BooleanVar(value=True)
                ticks.append(v)
                ttk.Checkbutton(listbox, text="%s  (%s)" % (s.title, s.host), variable=v).pack(anchor="w")
            note.configure(text="%d sites found." % len(sites) if sites else "No browser history found on this PC.", fg=C["text"])
            add.configure(state="normal" if sites else "disabled")

        def go_find():
            find.configure(state="disabled")
            note.configure(text="Reading this PC's browser history…", fg=C["text"])
            self.run_bg(lambda: ts.top_sites(bm.find_sources()), shown)

        def added(r, err):
            if not win.winfo_exists():
                return
            add.configure(state="normal")
            note.configure(text=("Couldn't add them: %s. Your earlier bookmarks are still on the PS5." % err) if err else
                           "%d added to \"%s\", %d were already in Omni." % (r["added"], ts.FOLDER, r["already"]),
                           fg=C["bad"] if err else C["text"])

        def go_add():
            chosen = [s for s, v in zip(found, ticks) if v.get()]
            if not chosen:
                note.configure(text="Tick at least one site.", fg=C["text"])
                return
            host = self.host.get().strip()
            add.configure(state="disabled")

            def work():
                with self.console(host) as c:
                    return ts.import_sites(c, chosen)
            self.run_bg(work, added)

        add = ttk.Button(btns, text="Add to Omni", style="Accent.TButton", command=go_add, state="disabled")
        add.pack(side="right", padx=8)
        find = ttk.Button(btns, text="Find", style="Ghost.TButton", command=go_find)
        find.pack(side="right")

    # -- read-later queue (Pocket / Instapaper / bookmarks HTML) into Omni's "Read later" folder (readlater_import.py) --
    def readlater_window(self):
        from . import readlater_import as rl
        win = tk.Toplevel(self.root)
        win.title("Import read later")
        win.configure(bg=C["ground"])
        win.transient(self.root)
        tk.Label(win, text="Pick a Pocket export (ril_export.html or CSV), an Instapaper CSV or a bookmarks HTML file. "
                           "Pages go into Omni's \"%s\" bookmarks folder; nothing in Omni is removed. Only web pages "
                           "are added, each address once, up to %d bookmarks in all. Close Omni on the PS5 first."
                           % (rl.READ_LATER_FOLDER, config.OMNI_BOOKMARK_MAX),
                 font=self.f_body, fg=C["text"], bg=C["ground"], wraplength=520, justify="left").pack(
            anchor="w", padx=14, pady=(12, 6))
        archive, notes = tk.BooleanVar(value=False), tk.BooleanVar(value=False)
        ttk.Checkbutton(win, text="Also read / archived items (into \"%s\")" % rl.READ_LATER_ARCHIVE_FOLDER,
                        variable=archive).pack(anchor="w", padx=14)
        ttk.Checkbutton(win, text="Add Instapaper highlighted text to titles (stays on this PC and the PS5)",
                        variable=notes).pack(anchor="w", padx=14)
        note = tk.Label(win, text="", font=self.f_small, fg=C["text"], bg=C["ground"], wraplength=520, justify="left")
        note.pack(anchor="w", padx=14, pady=6)
        btns = tk.Frame(win, bg=C["ground"])
        btns.pack(fill="x", padx=14, pady=(0, 12))
        ttk.Button(btns, text="Close", style="Ghost.TButton", command=win.destroy).pack(side="right")

        def done(r, err):
            if not win.winfo_exists():
                return
            pick.configure(state="normal")
            if err:
                note.configure(text="Couldn't import: %s\nYour earlier bookmarks are still on the PS5." % err, fg=C["bad"])
            else:
                note.configure(text=rl.summary(r), fg=C["text"])

        def go():
            path = filedialog.askopenfilename(parent=win, title="Read-later export", filetypes=[
                ("Pocket, Instapaper or bookmarks", "*.html *.htm *.csv"), ("All files", "*.*")])
            if not path:
                return
            host, arch, keep = self.host.get().strip(), archive.get(), notes.get()
            pick.configure(state="disabled")
            note.configure(text="Reading the file and adding it to Omni…", fg=C["text"])

            def work():   # read on this PC; sent only to the PS5's bookmarks file
                _, items, bad = rl.read_file(path, include_notes=keep)
                plan = rl.plan_import(items, include_archive=arch, include_notes=keep, bad_rows=bad)
                with self.console(host) as c:
                    return rl.import_to_console(c, plan)
            self.run_bg(work, done)

        pick = ttk.Button(btns, text="Choose file and import…", style="Accent.TButton", command=go)
        pick.pack(side="right", padx=8)

    # -- bookmarks from this PC (from the check page) -------------------------------
    def page_bookmarks(self, sync=False):
        self._clear()
        self.bm_sync = sync
        self.next_btn.configure(text="Preview" if sync else "Import", state="disabled",
                                command=self._bm_preview if sync else self._bm_import)
        self.back_btn.configure(state="normal", command=lambda: self.show(self.step))
        self.label(self.body, "Sync bookmarks" if sync else "Import bookmarks", "title").pack(anchor="w")
        self.bm_note = self.label(self.body, "Looking for bookmarks on this PC…", "muted")
        self.bm_note.pack(anchor="w", pady=(2, 12))
        self.bm_box = tk.Frame(self.body, bg=C["ground"])
        self.bm_box.pack(fill="both", expand=True)
        self.bm_sources, self.bm_pick = [], []
        self.run_bg(bookmarks.find_sources, self._bm_found)

    def _bm_found(self, sources, err):
        if not self.bm_box.winfo_exists():
            return
        sources = [s for s in sources or [] if s.count or s.error]
        if err or not sources:
            self.bm_note.configure(text="No Chrome, Edge, Brave or Firefox bookmarks found on this PC.")
            return
        self.bm_sources = sources
        self.bm_note.configure(text="Pick the ones to sync with Omni:" if self.bm_sync else "Pick the ones to add to Omni:")
        p = self.panel(self.bm_box)
        p.pack(fill="x")
        for s in sources:
            var = tk.BooleanVar(value=bool(s.count))
            self.bm_pick.append(var)
            if s.error:
                text = "%s  (couldn't read it; close that browser and try again)" % s.label
            else:
                text = "%s  (%d bookmark%s)" % (s.label, s.count, "" if s.count == 1 else "s")
            ttk.Checkbutton(p, text=text, variable=var, style="Panel.TCheckbutton",
                            state="disabled" if s.error or not s.count else "normal").pack(anchor="w", pady=2)
        if self.bm_sync:
            text = ("Next you'll see what would change, before anything is written. Bookmarks only on this PC are added "
                    "to Omni (up to %d in all); bookmarks only in Omni are saved to an HTML file you can import in your "
                    "browser. Nothing is removed on either side." % config.OMNI_BOOKMARK_MAX)
        else:
            text = ("They're added after the bookmarks already in Omni; none are removed or changed. Omni keeps "
                    "up to %d, bookmarks-bar ones first. Only web pages and bookmarklets are added. If Omni is open on "
                    "the PS5, close it first." % config.OMNI_BOOKMARK_MAX)
        self.label(self.bm_box, text, "small", wrap=640).pack(anchor="w", pady=(10, 0))
        self.next_btn.configure(state="normal")

    # -- two-way sync: preview, then confirm --
    def _bm_chosen(self):
        chosen = [s for s, v in zip(self.bm_sources, self.bm_pick) if v.get()]
        if not chosen:
            messagebox.showinfo(config.APP_NAME, "Tick at least one browser.")
        return chosen

    def _bm_busy(self, note):
        self.next_btn.configure(state="disabled")
        self.back_btn.configure(state="disabled")
        for w in self.bm_box.winfo_children():
            w.destroy()
        self.bm_note.configure(text=note, fg=C["muted"])

    def _bm_preview(self):
        chosen = self._bm_chosen()
        if not chosen:
            return
        self.bm_chosen_sources = chosen
        self._bm_busy("Comparing this PC's bookmarks with Omni's…")
        host = self.host.get().strip()

        def work():
            marks = bookmarks.collect(chosen)      # read on this PC; sent only to the PS5
            with self.console(host) as c:
                return bookmarks.plan_sync(marks, bookmarks.read_console_file(c))
        self.run_bg(work, self._bm_previewed)

    def _bm_list(self, title, marks, more_note=""):
        p = self.panel(self.bm_box)
        p.pack(fill="x", pady=(0, 6))
        self.label(p, title, "head", bg=C["panel"]).pack(anchor="w")
        show = 6
        for b in marks[:show]:
            text = (b.title or b.url) + ("   (%s)" % b.folder if b.folder else "")
            self.label(p, text, "small", bg=C["panel"], wrap=620).pack(anchor="w")
        if len(marks) > show:
            self.label(p, "…and %d more" % (len(marks) - show), "small", bg=C["panel"]).pack(anchor="w")
        if more_note:
            self.label(p, more_note, "small", bg=C["panel"], wrap=620).pack(anchor="w", pady=(4, 0))

    def _bm_previewed(self, plan, err):
        if not self.bm_box.winfo_exists():
            return
        self.back_btn.configure(state="normal")
        if err:
            self.bm_note.configure(text="Couldn't read Omni's bookmarks from the PS5: %s" % err, fg=C["bad"])
            return
        self.bm_plan = plan
        if not plan.to_console and not plan.to_pc:
            text = "Nothing to sync: Omni and this PC have the same bookmarks."
            if plan.cap_skipped:
                text = ("Omni is full (it keeps up to %d bookmarks), so the %d only on this PC can't be added."
                        % (config.OMNI_BOOKMARK_MAX, plan.cap_skipped))
            self.bm_note.configure(text=text, fg=C["text"])
            self.next_btn.configure(text="Done", state="normal", command=lambda: self.show(self.step))
            return
        self.bm_note.configure(text="Here's what the sync would do (nothing is removed on either side):", fg=C["text"])
        cap = ""
        if plan.cap_skipped:
            cap = ("%d more can't be added: Omni keeps up to %d bookmarks. Bookmarks-bar ones go first."
                   % (plan.cap_skipped, config.OMNI_BOOKMARK_MAX))
        self._bm_list("Add %d to Omni on the PS5" % len(plan.to_console), plan.to_console, cap)
        self._bm_list("Save %d from Omni for this PC's browser" % len(plan.to_pc), plan.to_pc,
                      "They go in a new HTML file in Downloads that you import in your browser's bookmark settings. "
                      "Setup doesn't change your browser's own files." if plan.to_pc else "")
        self.next_btn.configure(text="Sync", state="normal", command=self._bm_sync_go)

    def _bm_sync_go(self):
        if self.bm_plan.to_console and not messagebox.askokcancel(
                config.APP_NAME, "Close Omni on the PS5 first.\n\nOmni keeps its bookmarks in memory while it's open and "
                                 "would save over the ones Setup adds. Press OK once Omni is closed."):
            return
        plan, sources = self.bm_plan, self.bm_chosen_sources
        self._bm_busy("Syncing bookmarks…")
        host = self.host.get().strip()

        def work():
            with self.console(host) as c:
                return bookmarks.apply_sync(c, plan, sources=sources)
        self.run_bg(work, self._bm_synced)

    def _bm_synced(self, r, err):
        if not self.bm_box.winfo_exists():
            return
        self.back_btn.configure(state="normal")
        self.next_btn.configure(text="Done", state="normal", command=lambda: self.show(self.step))
        if err:
            self.bm_note.configure(text="Couldn't finish the sync: %s\nYour earlier bookmarks are still on the PS5." % err,
                                   fg=C["bad"])
            return
        lines = ["Added %d bookmark%s to Omni." % (r["added"], "" if r["added"] == 1 else "s")]
        if r["no_room"]:
            lines.append("%d left out: Omni keeps up to %d bookmarks." % (r["no_room"], config.OMNI_BOOKMARK_MAX))
        if r["exported"]:
            lines += ["Saved %d bookmark%s from Omni to:" % (r["exported"], "" if r["exported"] == 1 else "s"),
                      r["export_path"]]
        self.bm_note.configure(text="\n".join(lines), fg=C["text"])
        if r["exported"]:
            self.label(self.bm_box, "To add them to your browser, open its bookmark manager, choose Import bookmarks from "
                                    "an HTML file and pick this file. They arrive in a folder named \"%s\"."
                       % bookmarks.EXPORT_TOP_FOLDER, "small", wrap=640).pack(anchor="w")
            folder = os.path.dirname(r["export_path"])
            ttk.Button(self.bm_box, text="Open folder", style="Ghost.TButton",
                       command=lambda: self._open_folder(folder)).pack(anchor="w", pady=(8, 0))
        if r["added"]:
            self.label(self.bm_box, "The earlier bookmarks file was kept on the PS5 as a backup.", "small",
                       wrap=640).pack(anchor="w", pady=(8, 0))

    def _bm_import(self):
        chosen = [s for s, v in zip(self.bm_sources, self.bm_pick) if v.get()]
        if not chosen:
            messagebox.showinfo(config.APP_NAME, "Tick at least one browser.")
            return
        self.next_btn.configure(state="disabled")
        self.back_btn.configure(state="disabled")
        for w in self.bm_box.winfo_children():
            w.destroy()
        self.bm_note.configure(text="Adding them to Omni…")
        host = self.host.get().strip()
        self.run_bg(lambda: self._do_bm_import(host, chosen), self._bm_done)

    def _do_bm_import(self, host, chosen):
        marks = bookmarks.collect(chosen)    # read on this PC; sent only to the PS5
        with self.console(host) as c:
            return bookmarks.import_to_console(c, marks)

    def _bm_done(self, r, err):
        if not self.bm_box.winfo_exists():
            return
        self.back_btn.configure(state="normal")
        self.next_btn.configure(text="Done", state="normal", command=lambda: self.show(self.step))
        if err:
            self.bm_note.configure(text="Couldn't add the bookmarks: %s\nYour earlier bookmarks are still on the PS5." % err, fg=C["bad"])
            return
        lines = ["Added %d bookmark%s to Omni." % (r["added"], "" if r["added"] == 1 else "s")]
        if r["already"]:
            lines.append("%d %s already there." % (r["already"], "was" if r["already"] == 1 else "were"))
        if r["no_room"]:
            lines.append("%d left out: Omni keeps up to %d bookmarks." % (r["no_room"], config.OMNI_BOOKMARK_MAX))
        self.bm_note.configure(text="\n".join(lines), fg=C["text"])
        if r["added"]:
            self.label(self.bm_box, "Find them in Omni's quick menu (Options), Bookmarks. The earlier bookmarks file was "
                                    "kept on the PS5 as a backup.", "small", wrap=640).pack(anchor="w")

    # -- Omni backup and restore (from the check page) --------------------------------
    @staticmethod
    def _size_text(n):
        return "%.1f MB" % (n / 1048576.0) if n >= 1048576 else "%d KB" % ((n + 1023) // 1024)

    def _sub_page(self, title, note):
        self._clear()
        self.back_btn.configure(state="normal", command=lambda: self.show(self.step))
        self.label(self.body, title, "title").pack(anchor="w")
        note_label = self.label(self.body, note, "muted")
        note_label.pack(anchor="w", pady=(2, 12))
        box = tk.Frame(self.body, bg=C["ground"])
        box.pack(fill="both", expand=True)
        return note_label, box

    def page_backup(self):
        self.bk_note, self.bk_box = self._sub_page(
            "Back up Omni", "Saves Omni's settings from the PS5 to one zip on this PC. Tick any personal data to save too.")
        self.next_btn.configure(text="Back up", state="normal", command=self._bk_start)
        p = self.panel(self.bk_box)
        p.pack(fill="x")
        self.bk_pick = {}
        for g in backup.GROUPS:
            var = tk.BooleanVar(value=bool(g.get("always")))
            self.bk_pick[g["id"]] = var
            ttk.Checkbutton(p, text="%s  (%s)" % (g["name"], g["detail"]), variable=var, style="Panel.TCheckbutton",
                            state="disabled" if g.get("always") else "normal").pack(anchor="w", pady=2)
        row = tk.Frame(self.bk_box, bg=C["ground"])
        row.pack(fill="x", pady=(10, 0))
        self.label(row, "Save in:", "small").pack(side="left")
        self.bk_folder = tk.StringVar(value=backup.default_folder())
        ttk.Entry(row, textvariable=self.bk_folder, width=56).pack(side="left", padx=8, fill="x", expand=True)
        ttk.Button(row, text="Browse…", style="Small.TButton", command=self._bk_browse).pack(side="left")
        self.label(self.bk_box, "Saved passwords, cookies, sign-ins and open tabs are never included. The zip holds what "
                                "you tick in plain form: keep it somewhere private.", "small", wrap=640).pack(anchor="w", pady=(10, 0))

    def _bk_browse(self):
        d = filedialog.askdirectory(title="Where to save the Omni backup", initialdir=self.bk_folder.get() or None)
        if d:
            self.bk_folder.set(d)

    def _bk_start(self):
        groups = [g for g, v in self.bk_pick.items() if v.get()]
        folder = self.bk_folder.get().strip() or backup.default_folder()
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as e:
            messagebox.showerror(config.APP_NAME, "Can't save in that folder: %s" % e)
            return
        dest = backup.default_path(folder)
        self.next_btn.configure(state="disabled")
        self.back_btn.configure(state="disabled")
        for w in self.bk_box.winfo_children():
            w.destroy()
        self.bk_note.configure(text="Reading Omni's files from the PS5…")
        host = self.host.get().strip()
        self.run_bg(lambda: self._do_backup(host, groups, dest), self._bk_done)

    def _do_backup(self, host, groups, dest):
        with self.console(host) as c:
            return backup.backup(c, groups, dest)

    def _bk_done(self, r, err):
        if not self.bk_box.winfo_exists():
            return
        self.back_btn.configure(state="normal")
        self.next_btn.configure(text="Done", state="normal", command=lambda: self.show(self.step))
        if err:
            self.bk_note.configure(text="Couldn't back up Omni: %s\nNothing on the PS5 was changed." % err, fg=C["bad"])
            return
        lines = ["Saved %d file%s (%s) to:" % (r["files"], "" if r["files"] == 1 else "s", self._size_text(r["bytes"])),
                 r["path"]]
        if r["left_out"]:
            lines.append("%d file%s left out: bigger than Omni uses." % (r["left_out"], "" if r["left_out"] == 1 else "s"))
        self.bk_note.configure(text="\n".join(lines), fg=C["text"])
        folder = os.path.dirname(r["path"])
        ttk.Button(self.bk_box, text="Open folder", style="Ghost.TButton",
                   command=lambda: self._open_folder(folder)).pack(anchor="w", pady=(8, 0))

    @staticmethod
    def _open_folder(folder):
        if hasattr(os, "startfile"):
            os.startfile(folder)    # noqa: S606 (a folder Setup just wrote to)
        else:
            webbrowser.open("file://" + folder)

    # -- diagnostics bundle (from the check page): read + redact, preview, then save ---------------
    def page_diagnostics(self):
        self.dg_note, self.dg_box = self._sub_page(
            "Save a diagnostics bundle", "Reading Omni's logs and versions from the PS5 (nothing is changed)…")
        self.next_btn.configure(text="Save…", state="disabled", command=lambda: self._dg_save())
        self.dg_bundle = None
        host = self.host.get().strip()

        def work():
            with self.console(host) as c:
                return diagnostics.gather(c, setup_version=config.SETUP_VERSION)

        def ready(bundle, err):
            if not self.dg_box.winfo_exists():
                return
            if err:
                self.dg_note.configure(text="Couldn't read the PS5: %s\nNothing was saved." % err, fg=C["bad"])
                return
            self.dg_bundle = bundle
            removed = ", ".join("%d %s" % (n, w) for w, n in bundle["removed"].items()) or "nothing personal was found"
            self.dg_note.configure(text="Check what will be saved. Personal details are already replaced (%s). "
                                        "Nothing is uploaded: you attach the zip to a GitHub issue yourself." % removed,
                                   fg=C["text"], wraplength=640, justify="left")
            for title, text, height in (("Files", "\n".join(diagnostics.file_list(bundle)), 7),
                                        ("Preview (first lines, as saved)", diagnostics.preview(bundle), 12)):
                self.label(self.dg_box, title, "head").pack(anchor="w", pady=(6, 2))
                box = tk.Text(self.dg_box, height=height, bg=C["panel"], fg=C["muted"], bd=0, highlightthickness=0,
                              font=("Consolas", 9), wrap="none")
                box.insert("1.0", text)
                box.configure(state="disabled")
                box.pack(fill="both", expand=True)
            self.next_btn.configure(state="normal")

        def save():
            path = filedialog.asksaveasfilename(
                title="Save the diagnostics bundle", defaultextension=".zip", filetypes=[("Zip", "*.zip")],
                initialdir=diagnostics.default_folder(), initialfile=os.path.basename(diagnostics.default_path()))
            if not path or not self.dg_bundle:
                return
            try:
                diagnostics.save(self.dg_bundle, path)
            except OSError as e:
                messagebox.showerror(config.APP_NAME, "Couldn't save the bundle: %s" % e)
                return
            self.dg_note.configure(text="Saved to:\n%s\nAttach it to an issue at github.com/egomortal/omnibloom/issues."
                                        % path, fg=C["text"])
            self.next_btn.configure(text="Done", command=lambda: self.show(self.step))
            ttk.Button(self.dg_box, text="Open folder", style="Ghost.TButton",
                       command=lambda: self._open_folder(os.path.dirname(path))).pack(anchor="w", pady=(8, 0))

        self._dg_save = save
        self.run_bg(work, ready)

    def page_bug_report(self):
        """Ask for a short summary, read + redact the bundle, show all of it read-only; save/open only on confirm."""
        from tkinter import simpledialog
        from . import bug_report
        summary = simpledialog.askstring(config.APP_NAME, "What went wrong? (one or two sentences)", parent=self.root)
        if summary is None:
            return
        host = self.host.get().strip()

        def work():
            with self.console(host) as c:
                return diagnostics.gather(c, setup_version=config.SETUP_VERSION)

        def ready(bundle, err):
            if err:
                messagebox.showerror(config.APP_NAME, "Couldn't read the PS5: %s\nNothing was saved or sent." % err)
                return
            report = bug_report.BugReport(bundle, summary=summary)
            bug_report.review_window(self.root, report, diagnostics.default_path(), on_done=lambda path, url:
                                     messagebox.showinfo(config.APP_NAME, "Zip saved to:\n%s\n\nGitHub's new-issue page "
                                                         "is open in your browser. Attach the zip there yourself, "
                                                         "then press Submit." % path))
        self.run_bg(work, ready)

    def page_restore(self):
        start = backup.default_folder()
        path = filedialog.askopenfilename(title="Open an Omni backup", filetypes=[("Omni backup", "*.zip")],
                                          initialdir=start if os.path.isdir(start) else None)
        if not path:
            return
        self.rs_note, self.rs_box = self._sub_page("Restore Omni backup", "Checking the backup…")
        self.next_btn.configure(text="Restore", state="disabled", command=self._rs_start)
        self.rs_path = path
        self.run_bg(lambda: backup.read_backup(path), self._rs_loaded)

    def _rs_loaded(self, manifest, err):
        if not self.rs_box.winfo_exists():
            return
        if err:
            self.rs_note.configure(text="Can't use this backup: %s" % err, fg=C["bad"])
            return
        self.rs_note.configure(text="Made %s (Omni %s, Setup %s). Tick what to put back on the PS5:" % (
            str(manifest.get("created") or "?").replace("T", " ").rstrip("Z"), manifest.get("omni_version") or "?",
            manifest.get("setup_version") or "?"), fg=C["muted"])
        names = {g["id"]: g["name"] for g in backup.GROUPS}
        p = self.panel(self.rs_box)
        p.pack(fill="x")
        self.rs_pick = {}
        for g, s in manifest["summary"].items():
            var = tk.BooleanVar(value=True)
            self.rs_pick[g] = var
            ttk.Checkbutton(p, text="%s  (%d file%s, %s)" % (names[g], s["files"], "" if s["files"] == 1 else "s",
                            self._size_text(s["bytes"])), variable=var, style="Panel.TCheckbutton").pack(anchor="w", pady=2)
        if not self.rs_pick:
            self.rs_note.configure(text="This backup is empty.")
            return
        self.label(self.rs_box, "Close Omni on the PS5 first: Omni keeps these files in memory and saves its own copy over "
                                "them when it closes. The files they replace stay on the PS5 beside them as backups "
                                "(.before-setup-…).", "small", wrap=640).pack(anchor="w", pady=(10, 4))
        self.rs_closed = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.rs_box, text="Omni is closed on the PS5", variable=self.rs_closed,
                        command=lambda: self.next_btn.configure(state="normal" if self.rs_closed.get() else "disabled")
                        ).pack(anchor="w")

    def _rs_start(self):
        groups = [g for g, v in self.rs_pick.items() if v.get()]
        if not groups:
            messagebox.showinfo(config.APP_NAME, "Tick at least one thing to restore.")
            return
        if not self.rs_closed.get():
            return
        self.next_btn.configure(state="disabled")
        self.back_btn.configure(state="disabled")
        for w in self.rs_box.winfo_children():
            w.destroy()
        self.rs_note.configure(text="Putting the backup on the PS5…", fg=C["muted"])
        host, path = self.host.get().strip(), self.rs_path
        self.run_bg(lambda: self._do_restore(host, path, groups), self._rs_done)

    def _do_restore(self, host, path, groups):
        with self.console(host) as c:
            return backup.restore(c, path, groups)

    def _rs_done(self, r, err):
        if not self.rs_box.winfo_exists():
            return
        self.back_btn.configure(state="normal")
        self.next_btn.configure(text="Done", state="normal", command=lambda: self.show(self.step))
        if err:
            self.rs_note.configure(text="Couldn't restore the backup: %s" % err, fg=C["bad"])
            return
        lines = ["Restored %d file%s." % (r["written"], "" if r["written"] == 1 else "s")]
        if r["same"]:
            lines.append("%d %s already the same." % (r["same"], "was" if r["same"] == 1 else "were"))
        self.rs_note.configure(text="\n".join(lines), fg=C["text"])
        tip = "Start Omni to use them."
        if "downloads" in r["groups"]:
            tip += " The Downloads list comes back the next time the Downloads app starts (restart the PS5)."
        if r["written"]:
            tip += " The files they replaced were kept on the PS5 beside them (%s)." % r["parked_suffix"].lstrip(".")
        self.label(self.rs_box, tip, "small", wrap=640).pack(anchor="w")

    # -- S04 search shortcuts / Quick access editor (from the check page): its own window, shortcuts_edit.py ------
    def page_shortcuts_edit(self):
        from . import shortcuts_edit
        host = self.host.get().strip()
        shortcuts_edit.open_editor(self.root, connect=(lambda: self.console(host)) if host else None,
                                   run_bg=self.run_bg)

    # -- S10 "My filters" editor (from the check page): its own window, filters_edit.py ------------------------------
    def page_filters_edit(self):
        from . import filters_edit
        host = self.host.get().strip()
        filters_edit.open_editor(self.root, connect=(lambda: self.console(host)) if host else None,
                                 run_bg=self.run_bg)

    # -- S12 user add-ons (from the check page): push a checked .zip / folder, list, remove, roll back; addon_push.py --
    def page_addons(self):
        from . import addon_push
        host = self.host.get().strip()
        addon_push.open_window(self.root, connect=(lambda: self.console(host)) if host else None, run_bg=self.run_bg)

    # -- S08 settings reset (from the check page): its own window, settings_reset.py ---------------------------
    def page_settings_reset(self):
        from . import settings_reset
        host = self.host.get().strip()
        settings_reset.open_window(self.root, connect=(lambda: self.console(host)) if host else None,
                                   dest_fn=lambda: backup.default_path(backup.default_folder()), run_bg=self.run_bg)

    # -- S15 settings editor (from the check page): its own window, settings_editor.py / settings_catalog.py -----
    def page_settings_editor(self):
        from . import settings_editor
        host = self.host.get().strip()
        settings_editor.open_window(self.root, connect=(lambda: self.console(host)) if host else None,
                                    run_bg=self.run_bg)

    # -- S05 backup inspector (from the check page): its own window, backup_inspect.py --------------------------
    def page_backup_inspect(self):
        from . import backup_inspect
        start = backup.default_folder()
        path = filedialog.askopenfilename(title="Inspect an Omni backup", filetypes=[("Omni backup", "*.zip")],
                                          initialdir=start if os.path.isdir(start) else None)
        if not path:
            return
        host = self.host.get().strip()
        backup_inspect.open_window(self.root, path, connect=(lambda: self.console(host)) if host else None,
                                   run_bg=self.run_bg)

    # -- Omni developer flags (Advanced, from the check page): DEVELOPERS.md's flags as tick boxes -------------
    def page_devflags(self):
        if not messagebox.askokcancel(config.APP_NAME, "Omni developer flags are for testing. They can break pages, video "
                                      "or ad blocking, and Omni has no screen to undo them.\n\nOnly change them if you "
                                      "know why. Continue?", icon="warning"):
            return
        note, box = self._sub_page("Omni developer flags", "Reading which flags are set on the PS5 (names only)…")
        self.next_btn.configure(text="Apply", state="disabled")
        host = self.host.get().strip()
        picks, removes = {}, {}

        def work():
            with self.console(host) as c:
                return devflags.state(c)

        def ready(current, err):
            if not box.winfo_exists():
                return
            if err:
                note.configure(text="Couldn't read the PS5: %s\nNothing was changed." % err, fg=C["bad"])
                return
            note.configure(text="Ticked = the flag file is on the PS5. Omni reads them when it starts, so restart Omni "
                                "after applying. Removing a file always brings back the default.", fg=C["muted"])
            canvas = tk.Canvas(box, bg=C["ground"], highlightthickness=0)
            bar = ttk.Scrollbar(box, command=canvas.yview)
            inner = tk.Frame(canvas, bg=C["ground"])
            inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.create_window((0, 0), window=inner, anchor="nw")
            canvas.configure(yscrollcommand=bar.set)
            canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))
            bar.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)
            for kind, title, about in devflags.KINDS:
                self.label(inner, title, "head").pack(anchor="w", pady=(8, 0))
                self.label(inner, about, "small", wrap=640).pack(anchor="w", pady=(0, 4))
                for row in [r for r in devflags.ROWS if r["kind"] == kind]:
                    p = self.panel(inner)
                    p.pack(fill="x", pady=2)
                    for name in row["files"]:
                        on = bool(current.get(name))
                        if kind == devflags.OVERRIDE:
                            var = removes[name] = tk.BooleanVar(value=False)
                            ttk.Checkbutton(p, text="Move %s aside  (%s)" % (name, "on the PS5" if on else "not there"),
                                            variable=var, style="Panel.TCheckbutton",
                                            state="normal" if on else "disabled").pack(anchor="w")
                        else:
                            var = picks[name] = tk.BooleanVar(value=on)
                            ttk.Checkbutton(p, text=name, variable=var, style="Panel.TCheckbutton").pack(anchor="w")
                    self.label(p, "%s. Without it: %s. For: %s." % (row["effect"], row["default"], row["for"]), "small",
                               bg=C["panel"], wrap=600).pack(anchor="w")
                    self.label(p, "Risk: " + row["risk"], "small", bg=C["panel"], fg=C["warn"], wrap=600).pack(anchor="w")
            self.label(inner, "Setup only switches these files. It never edits a user agent or tuning value; use an FTP "
                              "client for that (see DEVELOPERS.md).", "small", wrap=640).pack(anchor="w", pady=(8, 0))
            self.next_btn.configure(state="normal", command=lambda: go(current))

        def go(current):
            try:
                changes = devflags.plan(current, {n: v.get() for n, v in picks.items()},
                                        [n for n, v in removes.items() if v.get()])
            except devflags.FlagError as e:
                messagebox.showerror(config.APP_NAME, str(e))
                return
            if not changes:
                messagebox.showinfo(config.APP_NAME, "Nothing to change.")
                return
            if not messagebox.askokcancel(config.APP_NAME, "Make these changes on the PS5?\n\n%s\n\nFiles are moved aside "
                                          "(.before-setup-…), never deleted. Restart Omni to apply."
                                          % "\n".join(devflags.describe(changes))):
                return
            self.next_btn.configure(state="disabled")
            self.back_btn.configure(state="disabled")
            for w in box.winfo_children():
                w.destroy()
            note.configure(text="Changing the flags on the PS5…", fg=C["muted"])

            def apply():
                with self.console(host) as c:
                    return devflags.apply(c, changes)
            self.run_bg(apply, done)

        def done(r, err):
            if not box.winfo_exists():
                return
            self.back_btn.configure(state="normal")
            self.next_btn.configure(text="Done", state="normal", command=lambda: self.show(self.step))
            if err:
                note.configure(text="Couldn't change the flags: %s" % err, fg=C["bad"])
                return
            lines = ["Turned on: %s" % ", ".join(r["created"]) if r["created"] else "",
                     "Moved aside: %s" % ", ".join(n for n, _ in r["removed"]) if r["removed"] else "",
                     "Already as asked: %s" % ", ".join(r["skipped"]) if r["skipped"] else "",
                     "Restart Omni to apply."]
            note.configure(text="\n".join(x for x in lines if x), fg=C["text"])

        self.run_bg(work, ready)

    # -- reading list export (from the check page): read-only copy to a PC folder, optional EPUB ----------------
    def page_reading_list(self):
        from . import readinglist
        note, box = self._sub_page("Export reading list", "Reading Omni's reading list from the PS5 (nothing is changed)…")
        self.next_btn.configure(text="Export", state="disabled")
        host = self.host.get().strip()
        state = {}

        def work():
            with self.console(host) as c:
                return readinglist.plan(c)

        def ready(p, err):
            if not box.winfo_exists():
                return
            if err:
                note.configure(text="Couldn't read the PS5: %s\nNothing was copied." % err, fg=C["bad"])
                return
            if p.get("no_index") or not p["pages"]:
                note.configure(text="There are no saved pages in Omni's reading list on this PS5.", fg=C["text"])
                return
            state["plan"] = p
            n = len(p["pages"])
            note.configure(text="%d saved page%s (%s). They are copied to a folder on this PC with an index page you "
                                "open in any browser." % (n, "" if n == 1 else "s", self._size_text(p["total"])),
                           fg=C["text"], wraplength=640, justify="left")
            if p["warn"]:
                self.label(box, "That is more than 500 MB: the copy takes a while and needs the space on this PC.",
                           "small", wrap=640).pack(anchor="w")
            state["epub"] = tk.BooleanVar(value=False)
            ttk.Checkbutton(box, text="Also make an e-book (EPUB) of the articles selected below: text and saved "
                            "pictures only", variable=state["epub"]).pack(anchor="w", pady=(6, 2))
            lb = tk.Listbox(box, selectmode="multiple", height=9, bg=C["panel"], fg=C["text"], bd=0,
                            highlightthickness=0, activestyle="none", exportselection=False)
            for pg in p["pages"]:
                title = " ".join((pg.title or readinglist.site(pg.url) or pg.id).split())[:90]
                extra = " · ".join(x for x in (readinglist.site(pg.url), readinglist.read_label(pg)) if x)
                lb.insert("end", "%s  (%s)" % (title, extra) if extra else title)
            lb.pack(fill="both", expand=True)
            state["list"] = lb
            row = tk.Frame(box, bg=C["ground"])
            row.pack(fill="x", pady=(10, 0))
            self.label(row, "Save in:", "small").pack(side="left")
            state["folder"] = tk.StringVar(value=readinglist.default_folder())
            ttk.Entry(row, textvariable=state["folder"], width=56).pack(side="left", padx=8, fill="x", expand=True)

            def browse():
                d = filedialog.askdirectory(title="Where to save the reading list",
                                            initialdir=state["folder"].get() or None)
                if d:
                    state["folder"].set(d)

            ttk.Button(row, text="Browse…", style="Small.TButton", command=browse).pack(side="left")
            self.next_btn.configure(state="normal", command=start)

        def start():
            p = state["plan"]
            ids = [p["pages"][i].id for i in state["list"].curselection()] if state["epub"].get() else []
            if state["epub"].get() and not ids:
                messagebox.showinfo(config.APP_NAME, "Select the articles to put in the e-book (or untick it).")
                return
            if p["warn"] and not messagebox.askyesno(config.APP_NAME, "Copy %s from the PS5?" % self._size_text(p["total"])):
                return
            folder = state["folder"].get().strip() or readinglist.default_folder()
            self.next_btn.configure(state="disabled")
            self.back_btn.configure(state="disabled")
            for w in box.winfo_children():
                w.destroy()
            note.configure(text="Copying the reading list from the PS5…", fg=C["muted"])

            def copy():
                with self.console(host) as c:
                    return readinglist.export(c, folder, epub_ids=ids, plan_result=p)

            self.run_bg(copy, done)

        def done(r, err):
            if not box.winfo_exists():
                return
            self.back_btn.configure(state="normal")
            self.next_btn.configure(text="Done", state="normal", command=lambda: self.show(self.step))
            if err:
                note.configure(text="Couldn't export the reading list: %s\nNothing on the PS5 was changed." % err,
                               fg=C["bad"])
                return
            lines = ["Copied %d page%s (%s) to:" % (r["pages"], "" if r["pages"] == 1 else "s", self._size_text(r["bytes"])),
                     r["path"], "Open index.html there to read them."]
            if r["epub"]:
                lines.append("E-book: %d article%s (reading-list.epub)." % (r["epub"]["chapters"],
                             "" if r["epub"]["chapters"] == 1 else "s"))
            if r["missing"] or r["too_big"]:
                lines.append("%d left out (missing on the PS5 or too big)." % (r["missing"] + r["too_big"]))
            note.configure(text="\n".join(lines), fg=C["text"])
            ttk.Button(box, text="Open folder", style="Ghost.TButton",
                       command=lambda: self._open_folder(r["path"])).pack(anchor="w", pady=(8, 0))

        self.run_bg(work, ready)

    # -- copy screenshots and saved downloads to this PC (from the check page) ------------------------
    def page_copy_to_pc(self):
        from . import pccopy
        import datetime as _dt
        note, box = self._sub_page("Copy from PS5", "Reading Omni's screenshots and the Downloads app's saved files "
                                                    "(nothing is changed)…")
        self.next_btn.configure(text="Copy", state="disabled")
        host = self.host.get().strip()
        st = {"picked": set(), "cancel": threading.Event()}

        def work():
            with self.console(host) as c:
                return pccopy.scan(c)

        def when(it):
            return _dt.datetime.fromtimestamp(it.mtime, _dt.timezone.utc).strftime("%Y-%m-%d %H:%M") if it.mtime else ""

        def ready(s, err):
            if not box.winfo_exists():
                return
            if err:
                note.configure(text="Couldn't read the PS5: %s\nNothing was copied." % err, fg=C["bad"])
                return
            items = st["items"] = s["items"]
            if not items:
                note.configure(text="There are no screenshots or saved downloads on this PS5 yet.", fg=C["text"])
                return
            note.configure(text="%d file%s on the PS5 (%s). Tick what to copy; files already on this PC are skipped."
                           % (len(items), "" if len(items) == 1 else "s", self._size_text(sum(i.size for i in items))),
                           fg=C["text"], wraplength=640, justify="left")
            labels = dict(pccopy.KIND_LABELS)
            filt = tk.Frame(box, bg=C["ground"])
            filt.pack(fill="x", pady=(0, 6))
            kind = tk.StringVar(value="Everything")
            ttk.Combobox(filt, textvariable=kind, state="readonly", width=16,
                         values=["Everything"] + [v for _k, v in pccopy.KIND_LABELS]).pack(side="left")
            self.label(filt, "from", "small").pack(side="left", padx=(8, 4))
            since = tk.StringVar(value="")
            ttk.Entry(filt, textvariable=since, width=11).pack(side="left")
            self.label(filt, "(YYYY-MM-DD, optional)", "small").pack(side="left", padx=(4, 8))

            def select_matching():
                kinds = None if kind.get() == "Everything" else {k for k, v in pccopy.KIND_LABELS if v == kind.get()}
                t = None
                if since.get().strip():
                    try:
                        t = int((_dt.datetime.strptime(since.get().strip(), "%Y-%m-%d")
                                 - _dt.datetime(1970, 1, 1)).total_seconds())
                    except ValueError:
                        messagebox.showinfo(config.APP_NAME, "Type the date as YYYY-MM-DD, for example 2026-11-01.")
                        return
                st["picked"] = {i.rel for i in pccopy.select(items, kinds, since=t)}
                redraw()

            ttk.Button(filt, text="Select these", style="Small.TButton", command=select_matching).pack(side="left")
            ttk.Button(filt, text="All", style="Small.TButton",
                       command=lambda: (st["picked"].update(i.rel for i in items), redraw())).pack(side="left", padx=4)
            ttk.Button(filt, text="None", style="Small.TButton",
                       command=lambda: (st["picked"].clear(), redraw())).pack(side="left")
            lf = tk.Frame(box, bg=C["ground"])
            lf.pack(fill="both", expand=True)
            tree = ttk.Treeview(lf, columns=("pick", "name", "kind", "size", "date"), show="headings", height=9,
                                selectmode="none")
            for col, text, w in (("pick", "", 30), ("name", "Name", 300), ("kind", "Type", 110), ("size", "Size", 80),
                                 ("date", "Date", 120)):
                tree.heading(col, text=text)
                tree.column(col, width=w, stretch=col == "name", anchor="w")
            sb = ttk.Scrollbar(lf, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=sb.set)
            tree.pack(side="left", fill="both", expand=True)
            sb.pack(side="left", fill="y")
            for n, it in enumerate(items):
                tree.insert("", "end", iid=str(n), values=("☐", it.rel, labels.get(it.kind, ""),
                                                           self._size_text(it.size), when(it)))

            def redraw():
                for n, it in enumerate(items):
                    tree.set(str(n), "pick", "☑" if it.rel in st["picked"] else "☐")

            def toggle(event):
                row = tree.identify_row(event.y)
                if row:
                    rel = items[int(row)].rel
                    st["picked"].symmetric_difference_update({rel})
                    redraw()

            tree.bind("<Button-1>", toggle)
            pics, dls = pccopy.default_folders()
            st["pics"], st["dls"] = tk.StringVar(value=pics), tk.StringVar(value=dls)
            for label, var in (("Screenshots to:", st["pics"]), ("Downloads to:", st["dls"])):
                row = tk.Frame(box, bg=C["ground"])
                row.pack(fill="x", pady=(6, 0))
                self.label(row, label, "small").pack(side="left")
                ttk.Entry(row, textvariable=var, width=56).pack(side="left", padx=8, fill="x", expand=True)
                ttk.Button(row, text="Browse…", style="Small.TButton",
                           command=lambda v=var: v.set(filedialog.askdirectory(initialdir=v.get() or None) or v.get())
                           ).pack(side="left")
            st["trash"] = tk.BooleanVar(value=False)
            ttk.Checkbutton(box, text="After copying, move the files to the Downloads app's trash on the PS5 (you can "
                                      "restore them there)", variable=st["trash"]).pack(anchor="w", pady=(8, 0))
            self.next_btn.configure(state="normal", command=start)

        def start():
            chosen = [i for i in st["items"] if i.rel in st["picked"]]
            if not chosen:
                messagebox.showinfo(config.APP_NAME, "Tick the files to copy first.")
                return
            pics = st["pics"].get().strip() or pccopy.default_folders()[0]
            dls = st["dls"].get().strip() or pccopy.default_folders()[1]
            try:
                pccopy.check_space(chosen, pics, dls)
            except (pccopy.CopyError, OSError) as e:
                messagebox.showerror(config.APP_NAME, str(e))
                return
            trash = st["trash"].get()
            if trash and not messagebox.askyesno(config.APP_NAME, "Move the %d copied file%s to the Downloads app's "
                                                 "trash on the PS5?" % (len(chosen), "" if len(chosen) == 1 else "s")):
                return
            self.next_btn.configure(text="Stop", state="normal", command=st["cancel"].set)
            self.back_btn.configure(state="disabled")
            for w in box.winfo_children():
                w.destroy()
            note.configure(text="Copying from the PS5…", fg=C["muted"])
            bar = ttk.Progressbar(box, mode="determinate", maximum=max(sum(i.size for i in chosen), 1))
            bar.pack(fill="x", pady=(6, 0))
            status = self.label(box, "", "small")
            status.pack(anchor="w", pady=(4, 0))
            last = [0.0]

            def progress(done_b, total_b, i, n):
                now = time.time()
                if now - last[0] < 0.15 and done_b < total_b:
                    return
                last[0] = now

                def show():
                    if bar.winfo_exists():
                        bar.configure(value=done_b)
                        status.configure(text="File %d of %d · %s of %s" % (i + 1, n, self._size_text(done_b),
                                                                           self._size_text(total_b)))
                self.q.put(show)

            def copy():
                with self.console(host) as c:
                    return pccopy.copy(c, chosen, pics, dls, move_to_trash=trash, progress=progress,
                                       cancel=st["cancel"])

            self.run_bg(copy, done)

        def done(r, err):
            if not box.winfo_exists():
                return
            self.back_btn.configure(state="normal")
            self.next_btn.configure(text="Done", state="normal", command=lambda: self.show(self.step))
            if err:
                note.configure(text="Couldn't copy: %s\nFiles already copied stay on this PC; run it again to carry "
                                    "on." % err, fg=C["bad"])
                return
            lines = ["Copied %d file%s (%s); %d already on this PC." % (r["copied"], "" if r["copied"] == 1 else "s",
                                                                      self._size_text(r["bytes"]), r["same"])]
            if r.get("cancelled"):
                lines.append("Stopped. Run it again to carry on where it stopped.")
            if r["renamed"]:
                lines.append("%d saved under a new name (a different file had the same name)." % r["renamed"])
            if r["trashed"]:
                lines.append("%d moved to the Downloads app's trash on the PS5." % r["trashed"])
            if r["failed"]:
                lines.append("%d couldn't be copied." % len(r["failed"]))
            note.configure(text="\n".join(lines), fg=C["text"])
            row = tk.Frame(box, bg=C["ground"])
            row.pack(anchor="w", pady=(8, 0))
            for text, folder in (("Open screenshots folder", r["pictures"]), ("Open downloads folder", r["downloads"])):
                if os.path.isdir(folder):
                    ttk.Button(row, text=text, style="Ghost.TButton",
                               command=lambda f=folder: self._open_folder(f)).pack(side="left", padx=(0, 8))

        self.run_bg(work, ready)

    # -- 4. choose ---------------------------------------------------------------
    def page_choose(self):
        cat = self.catalog
        self.job = {"mode": "install"}
        self.label(self.body, "Choose apps", "title").pack(anchor="w")
        self.label(self.body, "Tick what you want on your PS5.", "muted").pack(anchor="w", pady=(2, 10))
        core = self.panel(self.body)
        core.pack(fill="x", pady=3)
        self.label(core, "%s  ·  required" % config.HUB_NAME, "head", bg=C["panel"]).pack(anchor="w")
        self.label(core, "Lets the apps find and work with each other. Installed first and started with your PS5.",
                   "small", bg=C["panel"]).pack(anchor="w")
        for g in config.GROUPS:
            box = self.panel(self.body)
            box.pack(fill="x", pady=3)
            available = [a for a in g["apps"] if cat.has(a)]
            if not available:
                self.pick[g["id"]].set(False)
                self.label(box, g["name"], "head", bg=C["panel"], fg=C["muted"]).pack(anchor="w")
                self.label(box, config.COMING_SOON.get(g["id"], "Not in this release yet."), "small", bg=C["panel"]).pack(anchor="w")
                continue
            main = g["apps"][0]
            have = self.installed.get(main)
            status = "new"
            if have:
                latest = cat.apps[main]["version"]
                status = ("update %s → %s" % (have["version"], latest)) if installer.update_available(have["version"], latest) else "installed %s" % have["version"]
            ttk.Checkbutton(box, text="%s  (%s)" % (g["name"], status), variable=self.pick[g["id"]], style="Panel.TCheckbutton").pack(anchor="w")
            self.label(box, g["description"], "small", bg=C["panel"]).pack(anchor="w", padx=(24, 0))
            for sub in g["apps"][1:]:
                if cat.has(sub):
                    ttk.Checkbutton(box, text=SUB_APPS.get(sub, sub), variable=self.sub[sub], style="Panel.TCheckbutton").pack(anchor="w", padx=(24, 0))
            if g["id"] == "master-control":
                ttk.Checkbutton(box, text="Start it now", variable=self.start_mc, style="Panel.TCheckbutton").pack(anchor="w", padx=(24, 0), pady=(4, 0))
                ttk.Checkbutton(box, text="Start it automatically when the PS5 starts (takes PadBridge/EeveeLution's place)",
                                variable=self.autoload_mc, style="Panel.TCheckbutton").pack(anchor="w", padx=(24, 0))

    def _chosen_apps(self):
        apps = []
        for g in config.GROUPS:
            if not self.pick[g["id"]].get():
                continue
            for a in g["apps"]:
                if self.catalog.has(a) and (a == g["apps"][0] or self.sub.get(a, tk.BooleanVar(value=True)).get()):
                    apps.append(a)
        return apps

    def _next_choose(self):
        if not self._chosen_apps():
            messagebox.showinfo(config.APP_NAME, "Tick at least one app.")
            return False

    # -- 5. jdownloader -----------------------------------------------------------
    def page_jd(self):
        self.label(self.body, "JDownloader 2 (optional)", "title").pack(anchor="w")
        self.label(self.body, "Omni's downloads already work for most sites with yt-dlp, which is built in. JDownloader 2 "
                              "adds file hosts and link containers. We can't include JDownloader 2, so Setup uses the copy on "
                              "this computer.").pack(anchor="w", pady=(4, 10))
        wants_downloads = "downloads" in self._chosen_apps() or "downloads" in self.installed
        if not self.jd_folder.get():
            found = jd.detect()
            if found:
                self.jd_folder.set(found[0])
        row = tk.Frame(self.body, bg=C["ground"])
        row.pack(fill="x")
        self.label(row, "Where is JDownloader 2?", wrap=0).pack(side="left")
        ttk.Entry(row, textvariable=self.jd_folder, width=44).pack(side="left", padx=8)
        ttk.Button(row, text="Browse…", style="Ghost.TButton", command=self._browse_jd).pack(side="left")
        self.jd_status = self.label(self.body, "", "small")
        self.jd_status.pack(anchor="w", pady=(8, 0))
        link = self.label(self.body, "Don't have it? Get JDownloader 2 from jdownloader.org", fg=C["accent"], cursor="hand2")
        link.pack(anchor="w", pady=(6, 0))
        link.bind("<Button-1>", lambda e: webbrowser.open(config.JD_OFFICIAL_URL))
        p = self.panel(self.body)
        p.pack(fill="x", pady=(14, 0))
        if not config.jd_enabled():      # audit JD-03
            self.jd_copy.set(False)
            self.label(p, config.JD_HELD_REASON, "small", bg=C["panel"]).pack(anchor="w")
        elif wants_downloads:
            ttk.Checkbutton(p, text="Set up JDownloader 2 on the PS5", variable=self.jd_copy, style="Panel.TCheckbutton").pack(anchor="w")
            self.label(p, "Setup copies your JDownloader 2, adds the PS5 engine (about 70 MB, downloaded once), and runs a short "
                          "check on the PS5 before switching it on. The check can take a few minutes.", "small",
                       bg=C["panel"]).pack(anchor="w", pady=(2, 0))
        else:
            self.jd_copy.set(False)
            self.label(p, "JDownloader 2 works through Omni's downloads. Tick Omni's downloads on the previous page to use it.",
                       "small", bg=C["panel"]).pack(anchor="w")
        credit = self.panel(self.body)
        credit.pack(fill="x", pady=(12, 0))
        self.label(credit, "Credit", "head", bg=C["panel"]).pack(anchor="w")
        self.label(credit, "JDownloader 2 runs on the PS5 thanks to the PS5 Java 25 port by mateo-cogeanu. Its OpenJDK parts are "
                           "GPLv2 with the Classpath Exception; the source is at the port's repo.", "small",
                   bg=C["panel"]).pack(anchor="w")
        plink = self.label(credit, config.JAVA_PORT_URL, "small", fg=C["accent"], bg=C["panel"], cursor="hand2")
        plink.pack(anchor="w", pady=(2, 0))
        plink.bind("<Button-1>", lambda e: webbrowser.open(config.JAVA_PORT_URL))
        self._jd_refresh()
        self.next_btn.configure(text="Install")

    def _browse_jd(self):
        folder = filedialog.askdirectory(title="Pick your JDownloader 2 folder")
        if folder:
            self.jd_folder.set(folder)
            self._jd_refresh()

    def _jd_refresh(self):
        folder = self.jd_folder.get()
        if not folder:
            self.jd_status.configure(text="JDownloader 2 wasn't found on this computer.", fg=C["muted"])
        elif jd.is_jd_folder(folder):
            try:
                s = jd.summary(folder)
                text = "Found: %d files, %.0f MB." % (s["files"], s["megabytes"])
                self.jd_status.configure(text=text + ((" " + s["revision_note"]) if s["revision_note"] else ""),
                                         fg=C["warn"] if s["revision_note"] else C["ok"])
            except ValueError as e:
                self.jd_status.configure(text=str(e), fg=C["bad"])
        else:
            self.jd_status.configure(text="That folder doesn't look like JDownloader 2 (no JDownloader.jar and Core.jar).", fg=C["warn"])

    def _next_jd(self):
        apps = self._chosen_apps()
        self.job = {"mode": "install", "apps": apps,
                    "autoload": ["master-control"] if self.autoload_mc.get() else [],
                    "start": ["master-control"] if self.start_mc.get() else [],
                    "jd_folder": self.jd_folder.get() if self.jd_copy.get() else ""}

    # -- 6. work ------------------------------------------------------------------
    def page_work(self):
        mode = self.job["mode"]
        name = self.installed.get(self.job.get("app"), {}).get("name", "")
        words = {"install": "Installing", "repair": "Repairing " + name, "uninstall": "Removing " + name,
                 "diagnostics": "Collecting diagnostics"}[mode]
        self.label(self.body, words, "title").pack(anchor="w")
        self.label(self.body, "Keep this window open and your PS5 on. This can take a few minutes.", "muted").pack(anchor="w", pady=(2, 12))
        self.bar = ttk.Progressbar(self.body, mode="determinate")
        self.bar.pack(fill="x")
        self.logbox = tk.Text(self.body, height=14, bg=C["panel"], fg=C["muted"], bd=0, highlightthickness=0, font=self.f_small, wrap="word")
        self.logbox.pack(fill="both", expand=True, pady=12)
        self.next_btn.configure(state="disabled", text="Next")
        self.back_btn.configure(state="disabled")
        job = dict(self.job, host=self.host.get().strip())
        self.run_bg(lambda: self._work(job), self._work_done)

    def _log(self, text):
        def add():
            if self.logbox.winfo_exists():
                self.logbox.insert("end", text + "\n")
                self.logbox.see("end")
        self.q.put(add)

    def _progress(self, done, total):
        self.q.put(lambda: self.bar.winfo_exists() and self.bar.configure(maximum=max(total, 1), value=done))

    def _work(self, job):
        with self.console(job["host"]) as c:
            if job["mode"] == "uninstall":
                installer.uninstall_app(c, job["app"], log=self._log)
                return {}
            if job["mode"] == "diagnostics":
                self._log("Collecting technical logs from the PS5 (no browsing data; personal details removed)…")
                path = diagnostics.collect(c, None, setup_version=config.SETUP_VERSION, log=self._log)
                self.diag_path = path
                self._log("Check the zip, then attach it to an issue at https://github.com/egomortal/omnibloom/issues")
                try:
                    if sys.platform == "win32":
                        os.startfile(os.path.dirname(path))   # show the Downloads folder
                except OSError:
                    pass
                return {}
            if job["mode"] == "repair":
                installer.repair_app(c, self.catalog, job["app"], log=self._log, progress=self._progress)
                return {}
            receipts = installer.install(c, self.catalog, job["apps"], autoload=job["autoload"], start=job["start"],
                                         log=self._log, progress=self._progress)
            done = int(time.time()) + 1
            if job.get("jd_folder"):
                try:
                    release.load_engine(self.catalog, log=self._log)
                    out = jd.setup_jdownloader(c, self.catalog, job["jd_folder"], log=self._log, progress=self._progress)
                    receipts["_jd"] = {"ok": True, "install_id": out["acceptance"]["install_id"]}
                except Exception as e:   # FTP errors (ftplib.error_perm/error_reply) aren't IOError: the apps are installed either way
                    self._log("JDownloader 2 wasn't switched on: %s" % e)
                    self._log("Everything else is installed. yt-dlp downloads work right away.")
                    receipts["_jd"] = {"ok": False, "why": str(e)}
            if config.HUB_ID in receipts:   # what Bloom Core makes of the cards (it rewrites its status every ~10 s)
                self._log("Asking %s to confirm…" % config.HUB_NAME)
                want = [a for a, r in receipts.items() if not a.startswith("_") and installer.writes_card(a, r.get("card"))]
                status = installer.read_status(c, since=done, want=want, timeout=25)
                issues = installer.explain_status(status, app_ids=set(want))
                receipts["_status"] = issues
                for line in issues:
                    self._log("  " + line)
                if status and not issues:
                    self._log("%s confirmed every app." % config.HUB_NAME)
            return receipts

    def _work_done(self, result, err):
        if err:
            self._log("Stopped: %s" % err)
            self._log("Nothing that was already on your PS5 was lost. Go Back to try again, or use Repair.")
            self.back_btn.configure(state="normal")
            return
        self.result = result or {}
        self.next_btn.configure(state="normal")

    # -- 7. done ------------------------------------------------------------------
    def page_done(self):
        self.next_btn.configure(text="Close")
        self.back_btn.configure(state="disabled")
        mode = self.job["mode"]
        if mode == "diagnostics":
            self.label(self.body, "Diagnostics saved", "title").pack(anchor="w")
            self.label(self.body, getattr(self, "diag_path", ""), "small").pack(anchor="w", pady=(2, 8))
            self.label(self.body, "It holds technical logs from your PS5 with personal details removed (web addresses, site "
                                  "names, IP and e-mail addresses, passwords). Nothing was sent anywhere. Open it to check, "
                                  "then attach it to an issue at github.com/egomortal/omnibloom/issues.", wrap=640).pack(anchor="w")
            return
        if mode == "uninstall":
            self.label(self.body, "Removed", "title").pack(anchor="w")
            self.label(self.body, "Its earlier files were put back. Your other apps and your own data are still there.").pack(anchor="w", pady=8)
            return
        self.label(self.body, "All set" if mode == "install" else "Repaired", "title").pack(anchor="w")
        p = self.panel(self.body)
        p.pack(fill="x", pady=12)
        if "omni" in self.result:
            self.label(p, "Open Omni from your PS5's home screen (the tile is called Omni). It can take up to 15 seconds "
                          "to appear.", bg=C["panel"]).pack(anchor="w", pady=2)
        mc = self.result.get("master-control")
        if mc and mc.get("port"):
            self.label(p, "Master Control's menu: http://%s:%d/  (also from Omni)" % (self.host.get(), mc["port"]),
                       bg=C["panel"]).pack(anchor="w", pady=2)
        if config.HUB_ID in self.result:
            self.label(p, "%s is running and starts with your PS5." % config.HUB_NAME, bg=C["panel"]).pack(anchor="w", pady=2)
        for line in self.result.get("_status") or []:
            self.label(p, line, "small", fg=C["warn"], bg=C["panel"]).pack(anchor="w", pady=1)
        jdr = self.result.get("_jd")
        if jdr:
            self.label(p, "JDownloader 2 is on. Use it from Media downloads in Omni." if jdr["ok"] else
                       "JDownloader 2 is off: %s" % jdr["why"], "small" if not jdr["ok"] else "body",
                       fg=C["ok"] if jdr["ok"] else C["warn"], bg=C["panel"]).pack(anchor="w", pady=2)
        if "omni" in self.result:
            self._shortcut_panel(self.body)
        self.label(self.body, "Run Omnibloom Setup again any time to add, update, repair or remove apps.", "small").pack(anchor="w")

    # -- storage on the PS5 (from the check page; storage.py) ---------------------------
    def page_storage(self):
        from . import storage
        note, box = self._sub_page("Storage on the PS5",
                                   "Reading what Omni uses on the PS5 (nothing is changed)…")
        host = self.host.get().strip()

        def work():
            with self.console(host) as c:
                return storage.scan(c)

        def ready(rep, err):
            if not box.winfo_exists():
                return
            if err:
                note.configure(text="Couldn't read the PS5: %s\nNothing was changed." % err, fg=C["bad"])
                return
            free = ("Free on the PS5: %s." % storage.size_text(rep["free"])) if rep["free"] is not None else rep["free_note"]
            note.configure(text="Omni and its parts use %s%s.\n%s" % (
                storage.size_text(rep["total"]), " (at least: the listing stopped early)" if rep["truncated"] else "",
                free), fg=C["text"], wraplength=640, justify="left")
            table = tk.Frame(box, bg=C["ground"])
            table.pack(fill="x")
            largest = max([r["bytes"] for r in rep["rows"]] or [0])
            for i, r in enumerate(rep["rows"]):
                tk.Label(table, text=r["name"], font=self.f_body, fg=C["text"], bg=C["ground"], anchor="w").grid(
                    row=i, column=0, sticky="w", padx=(0, 8))
                cv = tk.Canvas(table, width=160, height=10, bg=C["panel"], highlightthickness=0)
                if largest and r["bytes"]:
                    cv.create_rectangle(0, 0, max(2, int(160 * r["bytes"] / float(largest))), 10, width=0,
                                        fill=C["bad"] if r["id"] == "unknown" else C["accent"])
                cv.grid(row=i, column=1, padx=4)
                tk.Label(table, text=storage.size_text(r["bytes"]), font=self.f_body, fg=C["text"], bg=C["ground"],
                         width=9, anchor="e").grid(row=i, column=2)
                detail = storage.types_text(rep["types"]) if r["id"] == "dl-saved" and rep["types"] else r["note"]
                tk.Label(table, text=detail, font=self.f_small, fg=C["muted"], bg=C["ground"], anchor="w",
                         wraplength=300, justify="left").grid(row=i, column=3, sticky="w", padx=(8, 0))
            if rep["unknown_count"]:
                self.label(box, "Not recognised, left alone: " + ", ".join(rep["unknown"][:5]) +
                           (" and %d more" % (rep["unknown_count"] - 5) if rep["unknown_count"] > 5 else ""),
                           "small", wrap=640).pack(anchor="w", pady=(6, 0))
            acts = tk.Frame(box, bg=C["ground"])
            acts.pack(fill="x", pady=(10, 0))
            self.label(acts, "Clean up (each asks first and lists every file):", "small").pack(anchor="w")
            row = tk.Frame(acts, bg=C["ground"])
            row.pack(fill="x", pady=(4, 0))
            any_action = False
            for a in storage.ACTIONS:
                items = storage.candidates(rep, a["id"])
                if not items:
                    continue
                any_action = True
                text = "%s (%s)…" % (a["name"], storage.size_text(sum(i["size"] for i in items)))
                ttk.Button(row, text=text, style="Ghost.TButton",
                           command=lambda a=a, items=items: start(a["id"], items)).pack(side="left", padx=(0, 8))
            if not any_action:
                self.label(row, "Nothing to clean up.", "small").pack(anchor="w")

        def start(action, items):
            head, lines = storage.confirmation(action, items)
            if not self._storage_confirm(head, lines):
                return
            for w in box.winfo_children():
                w.destroy()
            note.configure(text="Deleting on the PS5…", fg=C["muted"])

            def go():
                with self.console(host) as c:
                    return storage.clean(c, action, items)

            self.run_bg(go, done)

        def done(r, err):
            if not box.winfo_exists():
                return
            if err:
                note.configure(text="The clean-up stopped: %s" % err, fg=C["bad"])
            else:
                note.configure(text="Deleted %d file%s (%s)%s. Reading the PS5 again…" % (
                    r["deleted"], "" if r["deleted"] == 1 else "s", storage.size_text(r["bytes"]),
                    "; %d left alone (changed since the list was made)" % r["skipped"] if r["skipped"] else ""),
                    fg=C["text"])
            self.run_bg(work, ready)

        self.run_bg(work, ready)

    def _storage_confirm(self, head, lines):   # tests replace this
        win = tk.Toplevel(self.root)
        win.title(config.APP_NAME)
        win.configure(bg=C["ground"])
        win.transient(self.root)
        tk.Label(win, text=head, font=self.f_body, fg=C["text"], bg=C["ground"], wraplength=560, justify="left").pack(
            anchor="w", padx=14, pady=(12, 6))
        frame = tk.Frame(win, bg=C["ground"])
        frame.pack(fill="both", expand=True, padx=14)
        text = tk.Text(frame, width=86, height=min(16, max(4, len(lines))), bg=C["panel"], fg=C["text"], bd=0,
                       font=self.f_small)
        sb = ttk.Scrollbar(frame, command=text.yview)
        text.configure(yscrollcommand=sb.set)
        text.insert("end", "\n".join(lines))
        text.configure(state="disabled")
        text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        answer = {"ok": False}

        def yes():
            answer["ok"] = True
            win.destroy()

        btns = tk.Frame(win, bg=C["ground"])
        btns.pack(fill="x", padx=14, pady=12)
        ttk.Button(btns, text="Cancel", style="Ghost.TButton", command=win.destroy).pack(side="right")
        ttk.Button(btns, text="Delete %d file%s" % (len(lines), "" if len(lines) == 1 else "s"), style="Accent.TButton",
                   command=yes).pack(side="right", padx=8)
        win.grab_set()
        self.root.wait_window(win)
        return answer["ok"]

    # -- controller shortcuts (the same list as the README) ---------------------------
    # -- send a link to Omni (OMNI_PC_LINKS_V1, pclinks.py) ---------------------------------------------------------------
    def page_send_link(self):
        from . import pclinks
        note, box = self._sub_page(
            "Send a link to Omni", "Paste a web address (or up to %d, one per line), or drop a link on the box. Omni asks "
            "on the TV before it opens anything: \"Link from your PC\", Open or Dismiss." % pclinks.MAX_LINKS)
        self.pl_note = note
        self.next_btn.configure(text="Send", state="normal", command=self._pl_send)
        p = self.panel(box)
        p.pack(fill="x")
        self.label(p, "Web address", "head", bg=C["panel"]).pack(anchor="w")
        self.pl_text = tk.Text(p, height=4, bg=C["ground"], fg=C["text"], insertbackground=C["text"], bd=0,
                               highlightthickness=1, font=self.f_body, wrap="char", undo=True)
        self.pl_text.pack(fill="x", pady=(4, 6))
        self.pl_preview = self.label(p, "", "small", bg=C["panel"], wrap=640)
        self.pl_preview.pack(anchor="w")
        row = tk.Frame(p, bg=C["panel"])
        row.pack(fill="x", pady=(8, 2))
        ttk.Button(row, text="Paste", style="Small.TButton", command=self._pl_paste).pack(side="left")
        self.label(row, "Code (optional):", "small", bg=C["panel"]).pack(side="left", padx=(16, 6))
        self.pl_code = tk.StringVar(value="")
        ttk.Entry(row, textvariable=self.pl_code, width=9).pack(side="left")
        self.label(box, "Without a code the link goes into Omni's inbox over FTP and Omni asks about it while it is on "
                        "screen (within about 5 seconds). With the 6-digit code from Omni's Browser settings, \"Send "
                        "links from your phone\", it opens at once. Only http:// and https:// links, without a user name "
                        "or password.", "small", wrap=640).pack(anchor="w", pady=(10, 0))
        self.pl_text.bind("<<Modified>>", self._pl_changed)
        self._pl_enable_drop(self.pl_text)
        try:   # a link already on the clipboard is offered (not sent)
            clip = self.root.clipboard_get()
        except tk.TclError:
            clip = ""
        try:
            if clip and len(clip) <= 4 * pclinks.MAX_URL and pclinks.parse_input(clip)[0]:
                self.pl_text.insert("1.0", clip.strip())
        except pclinks.SendError:
            pass
        self._pl_changed()

    def _pl_enable_drop(self, widget):
        """Dropping a link (or a .url shortcut) on the box: needs tkinterdnd2's Tk; without it, Paste does the job."""
        if not hasattr(widget, "drop_target_register"):
            return False
        try:
            widget.drop_target_register("DND_Text", "DND_Files")
        except tk.TclError:
            return False

        def dropped(event):
            data = event.data or ""
            if os.path.isfile(data.strip("{}")) and data.strip("{}").lower().endswith(".url"):
                try:
                    with open(data.strip("{}"), encoding="utf-8", errors="replace") as f:
                        data = f.read(8192)
                except OSError:
                    return event.action
            self._pl_set(data)
            return event.action
        widget.dnd_bind("<<Drop>>", dropped)
        return True

    def _pl_set(self, text):
        self.pl_text.delete("1.0", "end")
        self.pl_text.insert("1.0", (text or "").strip())
        self._pl_changed()

    def _pl_paste(self):
        try:
            self._pl_set(self.root.clipboard_get())
        except tk.TclError:
            self.pl_note.configure(text="The clipboard has no text.", fg=C["bad"])

    def _pl_changed(self, _event=None):
        from . import pclinks
        if not self.pl_text.winfo_exists():
            return
        self.pl_text.edit_modified(False)
        raw = self.pl_text.get("1.0", "end")
        try:
            links, bad = pclinks.parse_input(raw)
        except pclinks.SendError as e:
            self.pl_preview.configure(text=str(e), fg=C["bad"])
            return
        if not raw.strip():
            text, color = "", C["muted"]
        elif not links:
            text, color = "That isn't a web address Omni can open.", C["bad"]
        else:
            sites = ", ".join(pclinks.site(u) for u in links[:4]) + (", …" if len(links) > 4 else "")
            text = "%d link%s: %s" % (len(links), "" if len(links) == 1 else "s", sites)
            text += ("  (%d line%s skipped: not a web address)" % (bad, "" if bad == 1 else "s")) if bad else ""
            color = C["muted"]
        self.pl_preview.configure(text=text, fg=color)

    def _pl_send(self):
        from . import pclinks
        host = self.host.get().strip()
        try:
            links, _bad = pclinks.parse_input(self.pl_text.get("1.0", "end"))
        except pclinks.SendError as e:
            self.pl_note.configure(text=str(e), fg=C["bad"])
            return
        if not links:
            self.pl_note.configure(text="Paste a web address first (https://…).", fg=C["bad"])
            return
        if not host:
            self.pl_note.configure(text="Find your PS5 first (Back, then Find).", fg=C["bad"])
            return
        code = self.pl_code.get().strip()
        self.next_btn.configure(state="disabled")
        self.pl_note.configure(text="Sending…", fg=C["muted"])

        def work():
            if code:
                return {"direct": pclinks.send_direct(host, links, code)}
            with self.console(host) as c:
                return pclinks.send_inbox(c, links)

        def done(r, err):
            if not self.pl_note.winfo_exists():
                return
            self.next_btn.configure(state="normal")
            if err:
                msg = str(err) if isinstance(err, pclinks.SendError) else "Couldn't reach the PS5: %s" % err
                self.pl_note.configure(text=msg + "\nNothing was sent.", fg=C["bad"])
                return
            n = r.get("direct") or r["links"]
            if "direct" in r:
                text = "Sent. Omni opens %s in a new tab." % ("it" if n == 1 else "them")
            else:
                text = ("Sent. Omni asks about %s on the TV (Open or Dismiss) while it is on screen."
                        % ("it" if n == 1 else "the %d links" % n))
                if r.get("waiting", 0) > 1:
                    text += " %d sends are waiting for Omni." % r["waiting"]
            self.pl_note.configure(text=text, fg=C["ok"])
            self.pl_text.delete("1.0", "end")
            self._pl_changed()
        self.run_bg(work, done)

    def _shortcut_panel(self, parent):
        p = self.panel(parent)
        p.pack(fill="x", pady=(0, 12))
        self.label(p, "Controller shortcuts in Omni (Xbox names in brackets)", "head", bg=C["panel"]).pack(anchor="w")
        grid = tk.Frame(p, bg=C["panel"])
        grid.pack(anchor="w", pady=(4, 0))
        for i, (ps, xb, what) in enumerate(shortcuts.KEY):
            self.label(grid, shortcuts.label(ps, xb), "small", fg=C["accent"], bg=C["panel"]).grid(row=i, column=0, sticky="w", padx=(0, 18))
            self.label(grid, what, "small", fg=C["text"], bg=C["panel"]).grid(row=i, column=1, sticky="w")
        ttk.Button(p, text="All controller shortcuts…", style="Alt.TButton",
                   command=self.show_shortcuts).pack(anchor="w", pady=(6, 2))

    def show_shortcuts(self):
        win = tk.Toplevel(self.root)
        win.title("Omni controller shortcuts")
        win.configure(bg=C["ground"])
        win.geometry("760x560")
        box = tk.Text(win, font=("Consolas", 10), bg=C["panel"], fg=C["text"], wrap="word", relief="flat",
                      padx=12, pady=10)
        bar = ttk.Scrollbar(win, command=box.yview)
        box.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        box.pack(fill="both", expand=True)
        box.insert("1.0", shortcuts.text())
        box.configure(state="disabled")


def main(test_ports=None):
    root = tk.Tk()
    SetupApp(root, test_ports=test_ports)
    root.mainloop()


if __name__ == "__main__":
    main()
