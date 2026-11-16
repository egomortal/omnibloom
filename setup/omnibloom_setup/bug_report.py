"""Pre-filled bug report: the diagnostics bundle, redacted once more, plus GitHub issue text opened in the browser.

Nothing leaves the PC on its own. The flow is:
    report = BugReport(bundle, summary)   # bundle from diagnostics.gather(); everything is redacted again here
    report.review_text()                  # the exact text: issue title + body and every file in the zip
    report.confirm()                      # only after the user has read it (the review window's tick box)
    report.submit(zip_path)               # saves the zip here, then opens the "new issue" page with title/body
submit() refuses to do anything before confirm(). The zip is never uploaded: the user attaches it to the issue.

On top of redaction.Redactor (web addresses, IP/MAC/e-mail, tokens, home folders, user names) this pass also hides:
WSL home folders (/mnt/c/Users/<name>, \\\\wsl$\\<distro>\\home\\<name>), whole Authorization / Cookie header values,
PSN online/account ids and console serials/IDPS/PSID written as name=value, and every address on a line about a
private (incognito) tab.
"""
import re
import urllib.parse
import webbrowser

from . import config, diagnostics
from .redaction import Redactor, pc_user_names

# GitHub answers "414 URI too long" well above this; browsers and the Windows shell are happy below it.
MAX_URL = 7000
SUMMARY_MAX = 2000
TITLE_MAX = 120
ZIP_NOTE = ("**Please attach the diagnostics zip to this issue yourself** (drag it into this box). "
            "It was saved on your PC and nothing was uploaded.")

EXTRA_RULES = (
    "WSL home folders (/mnt/c/Users/<name>, \\\\wsl$\\<distro>\\home\\<name>) become <home>.",
    "Authorization, Proxy-Authorization and Cookie header values become <secret>.",
    "PSN online ids, account/user ids and console serial numbers, IDPS and PSID become <id>.",
    "Every web address and site name on a line about a private (incognito) tab becomes <private-tab>.",
)

_WSL_HOME = re.compile(r"(?i)(?<![\w.-])/mnt/[a-z]/(?:Users|Documents and Settings)/[^/\s\"'<>]+")
_BACKSLASH_HOME = re.compile(r"(?i)(?<![A-Za-z]:)\\(?:home|Users)\\[^\\\r\n\t\"'<>|?*:]+")
_HEADER = re.compile(r"(?im)\b((?:proxy-)?authorization|cookie|set-cookie|x-api-key|x-auth-token)(\s*[:=]\s*)(?!<secret>\s*$)"
                     r"[^\r\n]+")
_IDS = re.compile(
    r"(?i)\b(online[_-]?id|psn[_-]?(?:id|name|user)|np[_-]?id|account[_-]?id|user[_-]?id|serial(?:[_-]?(?:number|no))?|"
    r"console[_-]?(?:id|serial)|idps|open[_-]?psid|psid)(\"?\s*[=:]\s*\"?)(?!<)([^\s\",;&<>]+)")
_PRIVATE_LINE = re.compile(r"(?i)\b(private|incognito)\b")
_ANY_URL = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]{1,15}://\S*|<host-[0-9a-f]{6}>(?:/…)?")


def _extra(text):
    text = _WSL_HOME.sub("<home>", text)
    text = _BACKSLASH_HOME.sub(lambda m: m.group(0)[0] + "<home>", text)
    text = _HEADER.sub(lambda m: m.group(1) + m.group(2) + "<secret>", text)
    text = _IDS.sub(lambda m: m.group(1) + m.group(2) + "<id>", text)
    return "".join(_ANY_URL.sub("<private-tab>", line) if _PRIVATE_LINE.search(line) else line
                   for line in text.splitlines(True))


def strong_redact(text, red=None):
    """Redact text for a public bug report: the extra rules above, then the bundle Redactor, then the extras again."""
    red = red or Redactor(user_names=pc_user_names())
    return _extra(red.redact(_extra(text)))


def _versions_lines(versions):
    v = versions or {}
    lines = ["- Setup: %s" % (v.get("setup_version") or config.SETUP_VERSION)]
    for app_id, rec in sorted((v.get("installed_apps") or {}).items()):
        lines.append("- %s: %s" % (rec.get("name") or app_id, rec.get("version") or "?"))
    lines.append("- PS5 firmware: %s" % (v.get("firmware") or "not read by Setup (tested on %s)" % config.TESTED_FIRMWARE))
    return lines


def new_issue_url(title, body, repo=None, max_url=MAX_URL):
    """The GitHub "new issue" address with title and body filled in, the body cut so the whole URL fits max_url."""
    base = "https://github.com/%s/issues/new?" % (repo or config.GITHUB_REPO)

    def build(b):
        return base + urllib.parse.urlencode({"title": title[:TITLE_MAX], "body": b}, quote_via=urllib.parse.quote)
    url = build(body)
    if len(url) <= max_url:
        return url
    cut = "\n\n(cut to fit the address; the full text is in the zip)"
    lo, hi = 0, len(body)
    while lo < hi:                       # longest prefix of body whose URL still fits
        mid = (lo + hi + 1) // 2
        if len(build(body[:mid] + cut)) <= max_url:
            lo = mid
        else:
            hi = mid - 1
    return build(body[:lo] + cut)


class NotConfirmed(RuntimeError):
    pass


class BugReport:
    def __init__(self, bundle, summary="", title="", user_names=(), repo=None):
        red = Redactor(user_names=list(user_names) + pc_user_names())
        self.repo = repo or config.GITHUB_REPO
        self.summary = strong_redact((summary or "").strip()[:SUMMARY_MAX], red)
        self.title = strong_redact((title or "").strip() or self._default_title(), red)[:TITLE_MAX]
        entries = [dict(e, text=strong_redact(e["text"], red)) for e in bundle["entries"]]
        for e in entries:
            e["bytes"] = len(e["text"].encode("utf-8"))
        removed = dict(bundle.get("removed") or {})
        for k, n in red.counts.items():
            removed[k] = removed.get(k, 0) + n
        self.bundle = dict(bundle, entries=entries, removed=dict(sorted(removed.items())))
        self.body = self._body()
        self.confirmed = False
        self.saved_to = None
        self.url = None

    def _default_title(self):
        first = (self.summary or "").splitlines()[0] if self.summary else ""
        return "Bug: " + (first[:80] if first else "(describe the problem)")

    def _body(self):
        b = self.bundle
        lines = ["### What happened", self.summary or "(describe the problem and the steps to repeat it)", "",
                 "### Versions"] + _versions_lines(b.get("versions")) + [
                 "", "### Diagnostics", ZIP_NOTE,
                 "Files: %d. Personal details removed: %s." % (
                     len(b["entries"]), ", ".join("%d %s" % (n, w) for w, n in b["removed"].items()) or "none found"),
                 "", "_Made by %s %s; the user reviewed this text before opening this page._" % (
                     config.APP_NAME, b.get("setup_version") or config.SETUP_VERSION)]
        return "\n".join(lines)

    def issue_url(self):
        return new_issue_url(self.title, self.body, repo=self.repo)

    def review_text(self):
        """Exactly what the user is shown: the issue as it will be filled in, then every file of the zip."""
        out = ["===== GitHub issue (opened in your browser; you press Submit there) =====",
               "Title: " + self.title, "", self.body, "",
               "===== Diagnostics zip (saved on this PC; you attach it yourself) ====="]
        for e in self.bundle["entries"]:
            out += ["", "== %s ==" % e["name"], e["text"].rstrip("\n")]
        return "\n".join(out) + "\n"

    def confirm(self):
        self.confirmed = True

    def submit(self, zip_path, opener=webbrowser.open, saver=diagnostics.save):
        """Save the zip and open the pre-filled issue page. Refuses before confirm(); never uploads anything."""
        if not self.confirmed:
            raise NotConfirmed("The report has to be reviewed and confirmed first.")
        self.saved_to = saver(self.bundle, zip_path)
        self.url = self.issue_url()
        opener(self.url)
        return self.saved_to, self.url


def review_window(parent, report, zip_path, on_done=lambda path, url: None, opener=webbrowser.open):
    """A read-only window with the exact text. Its button stays off until the user ticks "I have read it"."""
    import tkinter as tk
    from tkinter import messagebox
    win = tk.Toplevel(parent)
    win.title("Report a bug: check what will be shared")
    win.geometry("860x620")
    tk.Label(win, justify="left", wraplength=820, anchor="w",
             text="This is everything that will leave your PC, after redaction. The zip is saved here; the browser "
                  "opens GitHub's new-issue page with the text filled in. Nothing is uploaded: you attach the zip "
                  "and press Submit on GitHub yourself.").pack(fill="x", padx=12, pady=(10, 6))
    frame = tk.Frame(win)
    frame.pack(fill="both", expand=True, padx=12)
    box = tk.Text(frame, wrap="none", font=("Consolas", 9))
    sb = tk.Scrollbar(frame, command=box.yview)
    box.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    box.pack(side="left", fill="both", expand=True)
    box.insert("1.0", report.review_text())
    box.configure(state="disabled")
    row = tk.Frame(win)
    row.pack(fill="x", padx=12, pady=10)
    ok = tk.BooleanVar(value=False)
    go = tk.Button(row, text="Save zip and open GitHub", state="disabled")

    def tick():
        go.configure(state="normal" if ok.get() else "disabled")

    def send():
        if not ok.get():
            return
        report.confirm()
        try:
            path, url = report.submit(zip_path, opener=opener)
        except OSError as e:
            messagebox.showerror(config.APP_NAME, "Couldn't save the bundle: %s" % e, parent=win)
            return
        win.destroy()
        on_done(path, url)

    tk.Checkbutton(row, text="I have read it and nothing personal is left", variable=ok, command=tick).pack(side="left")
    go.configure(command=send)
    tk.Button(row, text="Cancel", command=win.destroy).pack(side="right")
    go.pack(side="right", padx=8)
    return win
