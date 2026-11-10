"""The Omnibloom Setup window: a simple step-by-step guide for people who've never used FTP or payloads.

Steps: Welcome → Find your PS5 → Check → Choose apps → JDownloader 2 → Install → Done.
Or the one button on the Welcome page ("Install everything for me"): Setup waits for the PS5 and does every step
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

from . import checks, config, installer, jd, oneclick, ps5, release

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
        self.autoload_mc = tk.BooleanVar(value=False)
        self.start_mc = tk.BooleanVar(value=True)
        self.jd_folder = tk.StringVar()
        self.jd_copy = tk.BooleanVar(value=False)
        self.job = {"mode": "install"}
        self.result = {}
        self.oc_cancel = threading.Event()
        self.oc_running = False
        self.oc_result = None

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
        self.label(self.body, "Omnibloom Setup puts the Omnibloom apps on your PS5 over your home network: Omni, the web "
                              "browser, and Master Control for other controllers. Pick what you want; you can add, "
                              "update or remove apps any time.").pack(anchor="w", pady=(0, 14))
        p = self.panel(self.body)
        p.pack(fill="x")
        self.label(p, "Before you start", "head", bg=C["panel"]).pack(anchor="w")
        for line in ("Your PS5 is jailbroken and on the same network as this computer.",
                     "ShadowMountPlus and kstuff are loaded (Omnibloom needs both).",
                     "Your payload loader and FTP server are running (most jailbreak setups start them for you)."):
            self.label(p, "•  " + line, bg=C["panel"]).pack(anchor="w", pady=2)
        one = self.panel(self.body)
        one.pack(fill="x", pady=(14, 0))
        self.label(one, "The easy way", "head", bg=C["panel"]).pack(anchor="w")
        self.label(one, "Press the button and Setup does everything: it waits for your PS5 to come on, installs Bloom Core, "
                        "Omni, Downloads, USB file access and Master Control one at a time, checks each one, and tells you "
                        "what it's doing. If anything goes wrong it puts your PS5 back as it was.", "small",
                   bg=C["panel"]).pack(anchor="w", pady=(2, 8))
        row = tk.Frame(one, bg=C["panel"])
        row.pack(fill="x")
        ttk.Button(row, text="Install everything for me", style="Accent.TButton", command=self.page_oneclick).pack(side="left")
        if not self.host.get():
            self.host.set(oneclick._remembered_host() or "")
        self.label(row, "PS5 address (optional):", "small", bg=C["panel"], wrap=0).pack(side="left", padx=(16, 6))
        ttk.Entry(row, textvariable=self.host, width=16).pack(side="left")
        self.label(self.body, "Or press Next to pick apps yourself. Nothing is deleted from your PS5. Anything Setup "
                              "replaces is kept as a backup, and Uninstall puts it back.", "small").pack(anchor="w", pady=(14, 0))

    # -- the one button ------------------------------------------------------------
    def page_oneclick(self):
        self._clear()
        self.label(self.body, "Installing everything", "title").pack(anchor="w")
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
        self.logbox = tk.Text(self.body, height=8, bg=C["panel"], fg=C["muted"], bd=0, highlightthickness=0, font=self.f_small, wrap="word")
        self.logbox.pack(fill="both", expand=True, pady=(8, 4))
        self.oc_actions = tk.Frame(self.body, bg=C["ground"])
        self.oc_actions.pack(fill="x")
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
        oc = oneclick.OneClick(host=host, ftp_port=self.ports.get("ftp"), loader_port=self.ports.get("loader"),
                               websrv_port=self.ports.get("websrv"), catalog=self.catalog,
                               catalog_loader=lambda log: release.load_catalog(log=log),
                               report=lambda e: self.q.put(lambda: self._oc_event(e)), progress=self._progress,
                               cancel=self.oc_cancel, networks=nets, start_master_control=self.start_mc.get(),
                               autoload_master_control=self.autoload_mc.get())
        self.run_bg(oc.run, lambda result, err: self._oc_done(oc, result, err))

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
        else:
            ttk.Button(self.oc_actions, text="Try again", style="Accent.TButton", command=self.page_oneclick).pack(side="left", pady=4)

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
        self.run_bg(lambda: ps5.scan(nets, progress=prog, ftp_port=self.ports.get("ftp"), loader_port=self.ports.get("loader")),
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
            note = "ready" if f["loader"] else "FTP only: the payload loader isn't running"
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
            return checks.run_checks(c)

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
        words = {"install": "Installing", "repair": "Repairing " + name, "uninstall": "Removing " + name}[mode]
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
                except (jd.CheckFailed, release.ReleaseError, ValueError, IOError) as e:
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
        self.label(self.body, "Run Omnibloom Setup again any time to add, update, repair or remove apps.", "small").pack(anchor="w")


def main(test_ports=None):
    root = tk.Tk()
    SetupApp(root, test_ports=test_ports)
    root.mainloop()


if __name__ == "__main__":
    main()
