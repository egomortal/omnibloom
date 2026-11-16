// OMNI_COUCH_TIMER_V1: writes omni/pages/bundle-clean4/timer/beep.wav, the Couch timer's chime: two short 880 Hz sine
// beeps and a pause (the page loops it). Generated here from a formula, so it carries no third-party licence.
// node tools/gen_timer_beep.cjs   (tools/test_timer_page.cjs checks the bundled file still matches this output)
'use strict';
const fs = require('fs');
const path = require('path');

const RATE = 16000, FREQ = 880, AMP = 0.45, FADE = 0.008;
// [start s, length s] of each beep inside one loop of LOOP seconds
const BEEPS = [[0, 0.18], [0.28, 0.18]], LOOP = 1.0;

function makeWav() {
  const n = Math.round(RATE * LOOP), data = Buffer.alloc(n * 2);
  for (let i = 0; i < n; i++) {
    const t = i / RATE;
    let v = 0;
    for (const [s, len] of BEEPS) {
      if (t < s || t >= s + len) continue;
      const env = Math.min(1, (t - s) / FADE, (s + len - t) / FADE);
      v = Math.sin(2 * Math.PI * FREQ * (t - s)) * AMP * env;
    }
    data.writeInt16LE(Math.round(v * 32767), i * 2);
  }
  const h = Buffer.alloc(44);
  h.write('RIFF', 0); h.writeUInt32LE(36 + data.length, 4); h.write('WAVE', 8);
  h.write('fmt ', 12); h.writeUInt32LE(16, 16); h.writeUInt16LE(1, 20); h.writeUInt16LE(1, 22);
  h.writeUInt32LE(RATE, 24); h.writeUInt32LE(RATE * 2, 28); h.writeUInt16LE(2, 32); h.writeUInt16LE(16, 34);
  h.write('data', 36); h.writeUInt32LE(data.length, 40);
  return Buffer.concat([h, data]);
}

const OUT = path.join(__dirname, '..', 'omni', 'pages', 'bundle-clean4', 'timer', 'beep.wav');
module.exports = { makeWav, OUT, RATE, FREQ, LOOP };
if (require.main === module) { fs.writeFileSync(OUT, makeWav()); console.log('wrote ' + OUT); }
