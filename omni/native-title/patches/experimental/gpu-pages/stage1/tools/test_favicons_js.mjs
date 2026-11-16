// OMNI_FAVICONS_V1: the capture script (OmniFavicons::captureScript, written by test_favicons.cpp) run against a
// mocked page: <link> icons, an <img> that loads / fails / taints the canvas, CORS, timeouts.
//   node test_favicons_js.mjs <script.js>
import { readFileSync } from "node:fs";

const body = readFileSync(process.argv[2], "utf8");
const AsyncFunction = (async () => {}).constructor;
const realTimeout = setTimeout;
let failures = 0, checks = 0;
const check = (c, what) => { ++checks; if (!c) { ++failures; console.log("FAIL: " + what); } };

// page: { href, links: [{rel, href, sizes, type}], icons: {url: {ok, taint, corsOk, never, w, h}} }
async function run(page) {
  const loads = [];
  const u = new URL(page.href);
  globalThis.location = { href: page.href, hostname: u.hostname, origin: u.origin, protocol: u.protocol };
  globalThis.document = {
    querySelectorAll: () => page.links.map(l => ({
      href: new URL(l.href, page.href).href,
      getAttribute: k => (k === "rel" ? l.rel : k === "sizes" ? l.sizes : k === "type" ? l.type : null) ?? null,
    })),
    createElement: () => {
      const c = { width: 0, height: 0, drawn: null };
      c.getContext = () => ({ drawImage: (img, x, y, w, h) => { c.drawn = { img, x, y, w, h }; } });
      Object.setPrototypeOf(c, HTMLCanvasElement.prototype);
      return c;
    },
  };
  globalThis.HTMLCanvasElement = function () {};
  HTMLCanvasElement.prototype.toDataURL = function (type) {
    if (!this.drawn) return "data:,";
    if (this.drawn.img.tainted) { const e = new Error("SecurityError"); e.name = "SecurityError"; throw e; }
    return "data:" + type + ";base64,iVBORw0KGgo=" + "|" + this.width + "x" + this.height + "|" + this.drawn.w + "x" + this.drawn.h;
  };
  globalThis.Image = class {
    set src(v) {
      const info = page.icons[v] || { ok: false };
      const cors = this.crossOrigin === "anonymous";
      loads.push((cors ? "cors " : "") + v);
      if (info.never) return;
      realTimeout(() => {
        if (!info.ok || (cors && info.corsOk === false)) { this.onerror && this.onerror(); return; }
        this.naturalWidth = info.w || 32; this.naturalHeight = info.h || 32;
        this.tainted = !cors && !!info.taint;
        this.onload && this.onload();
      }, 1);
    }
  };
  globalThis.setTimeout = (f, ms) => realTimeout(f, Math.max(1, ms / 100));   // the script's timers, 100x faster
  const out = await new AsyncFunction(body)();
  globalThis.setTimeout = realTimeout;
  return { out, loads };
}

const A = "https://www.example.com/page";
// 1. the 32 px <link> icon (same origin) beats 16 px, touch and favicon.ico
{
  const r = await run({ href: A, links: [
    { rel: "icon", href: "/i16.png", sizes: "16x16" }, { rel: "apple-touch-icon", href: "/t.png" },
    { rel: "icon", href: "/i32.png", sizes: "32x32" }, { rel: "mask-icon", href: "/m.svg" } ],
    icons: { "https://www.example.com/i32.png": { ok: true } } });
  check(r.out.startsWith("omni-fav;www.example.com;png;data:image/png;base64,"), "1 answer " + r.out);
  check(r.out.endsWith("|32x32|32x32"), "1 canvas 32x32 " + r.out);
  check(r.loads[0] === "https://www.example.com/i32.png" && r.loads.length === 1, "1 loads " + r.loads);
}
// 2. a cross-origin icon without CORS fails -> /favicon.ico of the page's origin
{
  const r = await run({ href: A, links: [{ rel: "shortcut icon", href: "https://cdn.other.net/f.ico" }],
    icons: { "https://cdn.other.net/f.ico": { ok: true, corsOk: false }, "https://www.example.com/favicon.ico": { ok: true, w: 16, h: 16 } } });
  check(r.out.includes(";png;"), "2 answer " + r.out);
  check(r.loads.join(",") === "cors https://cdn.other.net/f.ico,https://www.example.com/favicon.ico", "2 loads " + r.loads);
  check(r.out.endsWith("|32x32|32x32"), "2 16px icon drawn at 32 " + r.out);
}
// 3. same-origin icon that redirected cross-origin (canvas tainted) -> retried with crossOrigin
{
  const r = await run({ href: A, links: [{ rel: "icon", href: "/f.png" }],
    icons: { "https://www.example.com/f.png": { ok: true, taint: true } } });
  check(r.out.includes(";png;"), "3 answer " + r.out);
  check(r.loads.join(",") === "https://www.example.com/f.png,cors https://www.example.com/f.png", "3 loads " + r.loads);
}
// 4. nothing loads -> none
{
  const r = await run({ href: A, links: [], icons: {} });
  check(r.out === "omni-fav;www.example.com;none;not loaded", "4 answer " + r.out);
}
// 5. tainted even with CORS -> none (tainted)
{
  const r = await run({ href: "https://a.test/", links: [], icons: { "https://a.test/favicon.ico": { ok: true, taint: true, corsOk: true } } });
  check(r.out === "omni-fav;a.test;png;data:image/png;base64,iVBORw0KGgo=|32x32|32x32", "5 cors retry clears taint " + r.out);
}
// 6. an image that never answers: the per-image step, then the overall timeout never blocks
{
  const r = await run({ href: A, links: [{ rel: "icon", href: "/a.png" }], icons: { "https://www.example.com/a.png": { never: true }, "https://www.example.com/favicon.ico": { never: true } } });
  check(r.out.startsWith("omni-fav;www.example.com;none;"), "6 answer " + r.out);
}
// 7. a wide icon is letterboxed, aspect kept
{
  const r = await run({ href: A, links: [{ rel: "icon", href: "/w.png", sizes: "any" }], icons: { "https://www.example.com/w.png": { ok: true, w: 64, h: 32 } } });
  check(r.out.endsWith("|32x32|32x16"), "7 aspect " + r.out);
}
// 8. data: icons and SVG rank first; javascript: hrefs are skipped
{
  const r = await run({ href: A, links: [{ rel: "icon", href: "javascript:alert(1)" }, { rel: "icon", href: "/x.png", sizes: "48x48" }, { rel: "icon", href: "/x.svg", type: "image/svg+xml" }],
    icons: { "https://www.example.com/x.svg": { ok: true } } });
  check(r.loads[0] === "https://www.example.com/x.svg" && !r.loads.some(l => l.includes("javascript")), "8 loads " + r.loads);
}
console.log(checks + " checks, " + failures + " failures");
process.exit(failures ? 1 : 0);
