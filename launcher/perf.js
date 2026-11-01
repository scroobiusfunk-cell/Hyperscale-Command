// Performance mode: 'auto' (default), 'full' (all glass effects) or 'lite' (no backdrop filters).
// In auto, frame times are sampled after the first few key presses; if the TV can't keep up
// it switches to lite and remembers that.
var Perf = (function () {
  'use strict';
  var MODE_KEY = 'cmdPerfMode', AUTO_KEY = 'cmdAutoLite';
  var root = document.documentElement;
  var autoLite = false, windows = 0, results = [];

  function load(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function save(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }

  function mode() { return load(MODE_KEY) || 'auto'; }
  function isLite() { var m = mode(); return m === 'lite' || (m === 'auto' && autoLite); }

  function apply() {
    var lite = isLite();
    root.classList.toggle('lite', lite);
    root.classList.toggle('full', !lite);
  }

  // Called on each navigation key; measures ~450 ms of frames following it.
  function sample() {
    if (mode() !== 'auto' || autoLite || windows >= 4) return;
    windows++;
    var last = performance.now(), end = last + 450, deltas = [];
    function frame(t) {
      deltas.push(t - last); last = t;
      if (t < end) requestAnimationFrame(frame); else judge(deltas);
    }
    requestAnimationFrame(frame);
  }

  function judge(d) {
    if (d.length < 4) return;
    d.sort(function (a, b) { return a - b; });
    results.push(d[Math.floor(d.length * 0.9)]);       // 90th percentile frame time
    if (results.length < 3) return;
    var r = results.slice().sort(function (a, b) { return a - b; });
    if (r[1] > 28) {                                    // median of p90s worse than ~35 fps
      autoLite = true; save(AUTO_KEY, '1'); apply();
      if (window.Info) Info.toast('Switched to Lite mode for smoother motion (Red button to change)');
    }
  }

  function cycle() {
    var next = { auto: 'full', full: 'lite', lite: 'auto' }[mode()] || 'auto';
    save(MODE_KEY, next);
    if (next === 'auto') { autoLite = false; save(AUTO_KEY, ''); windows = 0; results = []; }
    apply();
    return next;
  }

  autoLite = load(AUTO_KEY) === '1';
  apply();
  return { sample: sample, cycle: cycle, mode: mode, isLite: isLite };
})();
