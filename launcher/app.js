(function () {
  'use strict';

  var grid = document.getElementById('grid');
  var hero = document.getElementById('hero');
  var ticker = document.getElementById('ticker');
  var wp = { a: document.querySelector('.wp.a'), b: document.querySelector('.wp.b'), cur: 'a' };
  var KEY = { LEFT: 37, UP: 38, RIGHT: 39, DOWN: 40, OK: 13, BACK: 461, RED: 403, GREEN: 404, YELLOW: 405, BLUE: 406 };
  var LAST_KEY = 'cmdLastApp';
  var apps = [], lastTile = null;

  function toast(m) { if (window.Info) Info.toast(m); }

  function luna(id, params, label) {
    if (window.webOS && webOS.service) {
      webOS.service.request('luna://com.webos.applicationManager', {
        method: 'launch',
        parameters: params ? { id: id, params: params } : { id: id },
        onFailure: function (e) { toast(label + ' failed: ' + ((e && e.errorText) || 'unknown error') + ' (check the app ID)'); }
      });
      return true;
    }
    toast('Not on a TV (webOSTV.js missing). Would open: ' + (params && params.target || id));
    return false;
  }

  function launch(app, tile) {
    try { localStorage.setItem(LAST_KEY, app.id); } catch (e) {}
    tile.classList.remove('press'); void tile.offsetWidth; tile.classList.add('press');
    toast('Opening ' + app.name + '…');
    luna(app.id, null, app.name);
  }

  function openNews() {
    var n = window.Info && Info.currentNews();
    if (!n || !n.link) { toast('No headline to open yet'); return; }
    toast('Opening article…');
    luna('com.webos.app.browser', { target: n.link }, 'Browser');
  }

  /* ---------- wallpaper: two pre-painted layers, crossfaded with opacity only ---------- */
  function tint(color) {
    var next = wp.cur === 'a' ? 'b' : 'a';
    wp[next].style.background =
      'radial-gradient(900px 700px at 12% 8%, ' + color + ', rgba(0,0,0,0) 70%),' +
      'radial-gradient(700px 600px at 55% 60%, ' + color + '33, rgba(0,0,0,0) 70%)';
    wp[next].classList.add('on'); wp[wp.cur].classList.remove('on'); wp.cur = next;
  }

  /* ---------- hero ---------- */
  var heroLayers = [], heroTimer = null, FADE_MS = 450;
  function setHero(app, tile) {
    var src = tile.querySelector('.art');
    var fresh = document.createElement('div');
    fresh.className = src.className; fresh.style.cssText = src.style.cssText; fresh.innerHTML = src.innerHTML;
    hero.insertBefore(fresh, hero.querySelector('.glass'));
    heroLayers.push(fresh);
    while (heroLayers.length > 3) { var o = heroLayers.shift(); if (o.parentNode) o.parentNode.removeChild(o); }
    clearTimeout(heroTimer);
    heroTimer = setTimeout(function () {
      while (heroLayers.length > 1) { var x = heroLayers.shift(); if (x.parentNode) x.parentNode.removeChild(x); }
    }, FADE_MS + 50);
    var name = hero.querySelector('.hero-name'), sub = hero.querySelector('.hero-sub');
    name.textContent = app.name; sub.textContent = app.subtitle || '';
    [name, sub].forEach(function (el) { el.classList.remove('fade'); void el.offsetWidth; el.classList.add('fade'); });
  }

  /* ---------- tiles ---------- */
  function build(app) {
    var b = document.createElement('button');
    b.className = 'tile'; b.type = 'button';
    b.setAttribute('role', 'menuitem');
    b.style.setProperty('--tile-color', app.color || '#6ea8ff');
    b.innerHTML =
      '<span class="glow"></span>' +
      '<span class="frame"><span class="art"></span><span class="glass"></span>' +
      '<span class="caption"><span class="name"></span><span class="sub"></span></span></span>';
    b.querySelector('.name').textContent = app.name;
    b.querySelector('.sub').textContent = app.subtitle || '';
    var art = b.querySelector('.art');
    if (app.art) {
      art.style.backgroundImage = 'url("' + app.art + '")';
    } else {
      art.className = 'art gen';
      art.innerHTML = '<span class="ring"></span><span class="mono"></span>';
      art.querySelector('.mono').textContent = app.name.charAt(0);
      if (app.logo) {
        var logo = document.createElement('img');
        logo.className = 'logo'; logo.alt = '';
        logo.onload = function () {
          art.className += ' has-logo';
          if (document.activeElement === b) setHero(app, b);   // refresh hero once the logo arrives
        };
        logo.onerror = function () { if (logo.parentNode) logo.parentNode.removeChild(logo); };
        logo.src = app.logo;
        art.appendChild(logo);
      }
    }
    b.addEventListener('click', function () { launch(app, b); });
    b.addEventListener('focus', function () {
      lastTile = b;
      tint(app.color || '#6ea8ff');
      setHero(app, b);
    });
    return b;
  }

  /* ---------- navigation ---------- */
  function tiles() { return Array.prototype.slice.call(grid.children); }
  function cols() {
    var list = tiles(), top = list[0].offsetTop, n = 0;
    while (n < list.length && list[n].offsetTop === top) n++;
    return n || 1;
  }
  function move(dir) {
    var el = document.activeElement;
    if (el === ticker) {
      if (dir === 'U') (lastTile || tiles()[0]).focus();
      else if (window.Info && (dir === 'L' || dir === 'R')) Info.stepNews(dir === 'L' ? -1 : 1);
      return;
    }
    var list = tiles(), i = list.indexOf(el);
    if (i < 0) { (lastTile || list[0]).focus(); return; }
    var c = cols();
    if (dir === 'L' && i % c === 0) return;
    if (dir === 'R' && ((i + 1) % c === 0 || i === list.length - 1)) return;
    var n = dir === 'L' ? i - 1 : dir === 'R' ? i + 1 : dir === 'U' ? i - c : i + c;
    if (dir === 'D' && n >= list.length) {
      // bottom row (or a gap below): go to the closest tile in the last row, else to the news ticker
      var lastRowStart = Math.floor((list.length - 1) / c) * c;
      if (i < lastRowStart) { list[list.length - 1].focus(); return; }
      if (!document.body.classList.contains('no-news')) ticker.focus();
      return;
    }
    if (n >= 0 && n < list.length) list[n].focus();
  }

  document.addEventListener('keydown', function (e) {
    if (window.Info && Info.activity()) { e.preventDefault(); return; }   // first press only wakes the screen
    var k = e.keyCode;
    if (k >= 37 && k <= 40) {
      move({ 37: 'L', 38: 'U', 39: 'R', 40: 'D' }[k]);
      if (window.Perf) Perf.sample();
    } else if (k === KEY.OK) {
      if (document.activeElement && document.activeElement.click) document.activeElement.click();
    } else if (k === KEY.BACK) {
      if (window.webOS && webOS.platformBack) webOS.platformBack();
    } else if (k === KEY.RED) {
      var m = Perf.cycle();
      toast('Performance: ' + { auto: 'Auto (adapts to your TV)', full: 'Full glass effects', lite: 'Lite (fastest)' }[m]);
    } else if (k === KEY.BLUE) {
      Info.showAmbient();
    } else if (k === KEY.YELLOW) {
      openNews();
    } else return;
    e.preventDefault();
  });
  document.addEventListener('mousemove', function () { if (window.Info) Info.activity(); });

  ticker.addEventListener('click', openNews);

  /* ---------- boot ---------- */
  fetch('apps.json')
    .then(function (r) { return r.json(); })
    .then(function (cfg) {
      apps = cfg.apps || [];
      var frag = document.createDocumentFragment();
      apps.forEach(function (a) { frag.appendChild(build(a)); });
      grid.appendChild(frag);
      if (window.Info) Info.init(cfg.settings);
      var last = null; try { last = localStorage.getItem(LAST_KEY); } catch (e) {}
      var idx = 0; apps.forEach(function (a, i) { if (a.id === last) idx = i; });
      if (tiles()[idx]) tiles()[idx].focus();
    })
    .catch(function (e) { toast('Could not load apps.json: ' + e); });
})();
