// OMNI_YT_AUTOCONTINUE_V1: the "Continue watching?" page script against a fake DOM (node).
// node test_yt_autocontinue_js.mjs <tree>/engine/entry/OmniYtAutoContinue.h   (or the .js test_yt_autocontinue.cpp wrote)
import fs from 'node:fs';
import vm from 'node:vm';

const path = process.argv[2];
if (!path) { console.error('usage: node test_yt_autocontinue_js.mjs <OmniYtAutoContinue.h | script.js>'); process.exit(2); }
let src = fs.readFileSync(path, 'utf8');
if (path.endsWith('.h')) {
    const a = src.indexOf('R"JS('), b = src.indexOf(')JS"', a);
    if (a < 0 || b < 0) { console.error('no R"JS( ... )JS" script in ' + path); process.exit(2); }
    src = src.slice(a + 5, b);
}
new vm.Script(src);   // syntax

// --- a tiny fake DOM ----------------------------------------------------------------------------------------------
class El {
    constructor(tag, opts = {}) {
        this.tag = tag; this.id = opts.id || ''; this.cls = opts.cls || []; this.text = opts.text || '';
        this.children = []; this.parent = null; this.clicks = 0;
        this.visible = opts.visible !== false; this.hidden = false; this.attrs = opts.attrs || {};
        this.paused = opts.paused; this.ended = opts.ended || false; this.isConnected = true;
    }
    add(...kids) { for (const k of kids) { k.parent = this; this.children.push(k); } return this; }
    get textContent() { return this.text + this.children.map(c => ' ' + c.textContent).join(''); }
    getAttribute(n) { return n in this.attrs ? this.attrs[n] : null; }
    getBoundingClientRect() {
        for (let e = this; e; e = e.parent) if (!e.visible) return { width: 0, height: 0 };
        return { width: 100, height: 40 };
    }
    matches(sel) {
        return sel.split(',').map(s => s.trim()).some(s => {
            const m = /^([a-z0-9-]*)(#[\w-]+)?(\.[\w-]+)?$/.exec(s);
            if (!m) throw new Error('fake DOM: unsupported selector ' + s);
            if (m[1] && m[1] !== this.tag) return false;
            if (m[2] && this.id !== m[2].slice(1)) return false;
            if (m[3] && !this.cls.includes(m[3].slice(1))) return false;
            return true;
        });
    }
    all(sel) {
        const parts = sel.includes(',') ? [sel] : sel.trim().split(/\s+/);
        let set = [this];
        for (const p of parts) {
            const next = [];
            for (const base of set) { const walk = e => { for (const c of e.children) { if (c.matches(p)) next.push(c); walk(c); } }; walk(base); }
            set = [...new Set(next)];
        }
        return set;
    }
    querySelectorAll(sel) { return this.all(sel); }
    querySelector(sel) { return this.all(sel)[0] || null; }
    click() { this.clicks++; }
}
function page({ host = 'www.youtube.com', path = '/watch', top = true } = {}, body) {
    const doc = new El('#document').add(body);
    const win = {};
    win.top = top ? win : {};
    Object.assign(win, {
        window: win, document: doc, location: { hostname: host, pathname: path },
        getComputedStyle: e => ({ display: 'block', visibility: 'visible' }),
    });
    return win;
}
function run(win) { return vm.runInNewContext(src, win); }

// YouTube's dialog: tp-yt-paper-dialog > yt-confirm-dialog-renderer > #confirm-button (yt-button-renderer > button)
function ytDialog({ text = 'Video paused. Continue watching?', cancel = false, visible = true } = {}) {
    const btn = new El('button', { text: 'Yes' });
    const confirm = new El('yt-button-renderer', { id: 'confirm-button' }).add(btn);
    const r = new El('yt-confirm-dialog-renderer', { text }).add(confirm);
    if (cancel) r.add(new El('yt-button-renderer', { id: 'cancel-button' }).add(new El('button', { text: 'Cancel' })));
    const dlg = new El('tp-yt-paper-dialog', { visible }).add(r);
    return { dlg, btn };
}
function video(paused = true, ended = false) { return new El('video', { cls: ['html5-main-video'], paused, ended }); }

let fails = 0, n = 0;
function check(name, got, want) { n++; if (got !== want) { fails++; console.log('FAIL', name, 'got', JSON.stringify(got), 'want', JSON.stringify(want)); } }

{   // the classic dialog, video paused -> pressed
    const { dlg, btn } = ytDialog();
    const w = page({}, new El('body').add(video(true), new El('ytd-popup-container').add(dlg)));
    check('yt dialog answered', run(w), 'yt'); check('yt button clicked once', btn.clicks, 1);
}
{   // other language, but only "Yes" (no Cancel) -> pressed
    const { dlg, btn } = ytDialog({ text: 'Video pausiert. Weiter ansehen?' });
    const w = page({}, new El('body').add(video(true), dlg));
    check('no-cancel dialog answered', run(w), 'yt'); check('no-cancel clicked', btn.clicks, 1);
}
{   // a delete / remove confirmation (has Cancel, other words) -> never pressed
    const { dlg, btn } = ytDialog({ text: 'Remove from playlist?', cancel: true });
    const w = page({}, new El('body').add(video(true), dlg));
    check('other confirm left alone', run(w), ''); check('other confirm not clicked', btn.clicks, 0);
}
{   // the English wording with a Cancel button -> pressed (words match)
    const { dlg, btn } = ytDialog({ text: 'Video paused. Continue watching?', cancel: true });
    const w = page({}, new El('body').add(video(true), dlg));
    check('worded dialog with cancel answered', run(w), 'yt'); check('worded clicked', btn.clicks, 1);
}
{   // hidden (closed) dialog -> nothing
    const { dlg, btn } = ytDialog({ visible: false });
    const w = page({}, new El('body').add(video(true), dlg));
    check('hidden dialog', run(w), ''); check('hidden not clicked', btn.clicks, 0);
}
{   // aria-hidden renderer -> nothing
    const { dlg, btn } = ytDialog();
    dlg.children[0].attrs['aria-hidden'] = 'true';
    const w = page({}, new El('body').add(video(true), dlg));
    check('aria-hidden dialog', run(w), ''); check('aria-hidden not clicked', btn.clicks, 0);
}
{   // video still playing -> nothing (not the pause dialog)
    const { dlg, btn } = ytDialog();
    const w = page({}, new El('body').add(video(false), dlg));
    check('playing video', run(w), ''); check('playing not clicked', btn.clicks, 0);
}
{   // video ended -> nothing
    const { dlg, btn } = ytDialog();
    const w = page({}, new El('body').add(video(true, true), dlg));
    check('ended video', run(w), ''); check('ended not clicked', btn.clicks, 0);
}
{   // no video at all -> nothing
    const { dlg, btn } = ytDialog();
    const w = page({}, new El('body').add(dlg));
    check('no video', run(w), ''); check('no video not clicked', btn.clicks, 0);
}
{   // YouTube TV mode -> nothing, even with the dialog
    const { dlg, btn } = ytDialog();
    const w = page({ path: '/tv' }, new El('body').add(video(true), dlg));
    check('tv mode', run(w), ''); check('tv not clicked', btn.clicks, 0);
    const w2 = page({ path: '/tv/watch' }, new El('body').add(video(true), ytDialog().dlg));
    check('tv subpath', run(w2), '');
}
{   // not YouTube -> nothing
    const { dlg, btn } = ytDialog();
    const w = page({ host: 'evil-youtube.com' }, new El('body').add(video(true), dlg));
    check('other host', run(w), ''); check('other host not clicked', btn.clicks, 0);
}
{   // a frame (not the top window) -> nothing
    const { dlg, btn } = ytDialog();
    const w = page({ top: false }, new El('body').add(video(true), dlg));
    check('frame', run(w), ''); check('frame not clicked', btn.clicks, 0);
}
{   // nothing on screen -> ''
    const w = page({}, new El('body').add(video(false)));
    check('quiet page', run(w), '');
}
{   // YouTube Music: ytmusic-you-there-renderer with its button
    const b = new El('button', { text: 'Yes' });
    const r = new El('ytmusic-you-there-renderer', { text: 'Video paused. Continue watching?' }).add(new El('yt-button-renderer').add(b));
    const w = page({ host: 'music.youtube.com' }, new El('body').add(new El('ytmusic-popup-container').add(r)));
    check('music answered', run(w), 'music'); check('music clicked', b.clicks, 1);
    r.visible = false;
    check('music hidden', run(w), ''); check('music hidden not clicked again', b.clicks, 1);
}
{   // a page that throws inside (getComputedStyle broken) -> '' not an exception
    const { dlg } = ytDialog();
    const w = page({}, new El('body').add(video(true), dlg));
    w.getComputedStyle = () => { throw new Error('x'); };
    check('throwing page', run(w), '');
}
{   // the script defines nothing in the page
    const { dlg } = ytDialog();
    const w = page({}, new El('body').add(video(true), dlg));
    const before = Object.keys(w).sort().join(',');
    run(w);
    check('no globals', Object.keys(w).sort().join(','), before);
}
console.log(fails ? `${fails} of ${n} FAILED` : `all ${n} passed`);
process.exit(fails ? 1 : 0);
