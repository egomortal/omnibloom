// Verify that a stalled request cannot become a passing rejection test.
// Run with Node; no network or console is required.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, 'media-security.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

(async () => {
    for (const outcome of ['loaded', 'error', 'timeout']) {
        let video, timeout, cleared = false;
        const context = vm.createContext({
            window: {}, console: {log() {}}, addEventListener() {},
            document: {createElement() {video = {}; return video;}, body: {append() {}}},
            setTimeout(callback) {timeout = callback; return 1;},
            clearTimeout(id) {assert.equal(id, 1); cleared = true;},
        });
        vm.runInContext(script, context);
        const pending = vm.runInContext("load('/synthetic',true)", context);
        assert.equal(video.crossOrigin, 'anonymous');
        if (outcome === 'loaded') video.onloadeddata();
        else if (outcome === 'error') video.onerror();
        else timeout();
        const result = await pending;
        assert.equal(result.outcome, outcome);
        assert.equal(result.loaded, outcome === 'loaded');
        assert.equal(result.outcome === 'error', outcome === 'error');
        assert.equal(video.onloadeddata, null);
        assert.equal(video.onerror, null);
        assert.ok(cleared);
    }
    assert.doesNotMatch(script, /!result\.loaded/);
    console.log('PASS: loaded, error and timeout remain distinct; handlers and timer cleaned');
})().catch(error => {console.error(error); process.exitCode = 1;});
