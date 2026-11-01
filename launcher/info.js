// Clock, weather (Open-Meteo, no API key), news (RSS), ambient idle screen and toasts.
// Everything is cached in localStorage so the screen fills instantly on boot, then refreshes.
var Info = (function () {
  'use strict';
  var cfg = {}, $ = function (s) { return document.querySelector(s); };
  var news = [], newsIdx = 0, newsTimer = null, idleTimer = null, ambientOn = false;

  function load(k) { try { return JSON.parse(localStorage.getItem(k)); } catch (e) { return null; } }
  function save(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }

  function get(url, asText) {
    var ctl = window.AbortController ? new AbortController() : null;
    var t = setTimeout(function () { if (ctl) ctl.abort(); }, 10000);
    return fetch((cfg.corsProxy || '') + (cfg.corsProxy ? encodeURIComponent(url) : url), ctl ? { signal: ctl.signal } : {})
      .then(function (r) { clearTimeout(t); if (!r.ok) throw new Error('HTTP ' + r.status); return asText ? r.text() : r.json(); });
  }
  function direct(url) {   // Open-Meteo sends CORS headers, so it never needs the proxy
    return fetch(url).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
  }

  /* ---------- toast ---------- */
  var toastTimer;
  function toast(msg, ms) {
    var el = $('#toast'); el.textContent = msg; el.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.remove('show'); }, ms || 3200);
  }

  /* ---------- clock ---------- */
  function tick() {
    var d = new Date();
    var time = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    var date = d.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long' });
    $('#clock').textContent = time; $('#date').textContent = date;
    $('.amb-clock').textContent = time; $('.amb-date').textContent = date;
  }

  /* ---------- weather ---------- */
  var ICON = {
    sun: '<circle cx="24" cy="24" r="8"/><path d="M24 6v5M24 37v5M6 24h5M37 24h5M11.3 11.3l3.5 3.5M33.2 33.2l3.5 3.5M11.3 36.7l3.5-3.5M33.2 14.8l3.5-3.5"/>',
    part: '<circle cx="17" cy="17" r="6"/><path d="M17 5v3M5 17h3M8.5 8.5l2 2M25.5 8.5l-2 2"/><path d="M18 38h16a7 7 0 0 0 0-14 9 9 0 0 0-17 2.5A5.8 5.8 0 0 0 18 38z"/>',
    cloud: '<path d="M14 36h20a8 8 0 0 0 0-16 11 11 0 0 0-21 3 6.6 6.6 0 0 0 1 13z"/>',
    rain: '<path d="M14 30h20a8 8 0 0 0 0-16 11 11 0 0 0-21 3 6.6 6.6 0 0 0 1 13z"/><path d="M17 35l-2 6M25 35l-2 6M33 35l-2 6"/>',
    snow: '<path d="M14 30h20a8 8 0 0 0 0-16 11 11 0 0 0-21 3 6.6 6.6 0 0 0 1 13z"/><path d="M16 37h.1M24 40h.1M32 37h.1M20 43h.1M28 43h.1"/>',
    storm: '<path d="M14 30h20a8 8 0 0 0 0-16 11 11 0 0 0-21 3 6.6 6.6 0 0 0 1 13z"/><path d="M25 32l-5 7h6l-4 7"/>',
    fog: '<path d="M10 18h28M6 25h36M10 32h28M14 39h20"/>'
  };
  function wmo(code) {
    if (code === 0) return ['sun', 'Clear'];
    if (code <= 2) return ['part', 'Partly cloudy'];
    if (code === 3) return ['cloud', 'Cloudy'];
    if (code === 45 || code === 48) return ['fog', 'Fog'];
    if ((code >= 71 && code <= 77) || code === 85 || code === 86) return ['snow', 'Snow'];
    if (code >= 95) return ['storm', 'Thunderstorms'];
    if (code >= 51) return ['rain', code >= 80 ? 'Showers' : 'Rain'];
    return ['cloud', ''];
  }
  function icon(name, size) {
    return '<svg class="wx-icon" width="' + size + '" height="' + size + '" viewBox="0 0 48 48" fill="none" stroke="currentColor" ' +
      'stroke-width="3" stroke-linecap="round" stroke-linejoin="round">' + ICON[name] + '</svg>';
  }
  function esc(s) { var d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }

  function renderWeather(w) {
    if (!w || !w.current) return;
    var c = wmo(w.current.code), deg = '°';
    $('#wx-mini').innerHTML = icon(c[0], 40) + '<span class="wx-temp">' + Math.round(w.current.temp) + deg + '</span>' +
      '<span class="wx-place">' + esc(w.place) + '</span>';
    var days = w.daily.map(function (d, i) {
      var k = wmo(d.code);
      var name = i === 0 ? 'Today' : new Date(d.date + 'T12:00').toLocaleDateString([], { weekday: 'short' });
      return '<div class="amb-day"><div class="amb-dname">' + esc(name) + '</div>' + icon(k[0], 56) +
        '<div class="amb-range"><b>' + Math.round(d.max) + deg + '</b> ' + Math.round(d.min) + deg + '</div></div>';
    }).join('');
    $('.amb-wx').innerHTML =
      '<div class="amb-now">' + icon(c[0], 120) + '<div><div class="amb-temp">' + Math.round(w.current.temp) + deg + '</div>' +
      '<div class="amb-cond">' + esc(c[1]) + ' · ' + esc(w.place) + '</div></div></div><div class="amb-days">' + days + '</div>';
  }

  function loadWeather() {
    var wc = cfg.weather || {};
    if (!wc.location && wc.lat == null) return;
    var where = (wc.lat != null && wc.lon != null)
      ? Promise.resolve({ lat: wc.lat, lon: wc.lon, name: wc.location || '' })
      : (load('cmdGeo') && load('cmdGeo').q === wc.location ? Promise.resolve(load('cmdGeo'))
        : direct('https://geocoding-api.open-meteo.com/v1/search?count=1&name=' + encodeURIComponent(wc.location))
          .then(function (g) {
            var r = g.results && g.results[0]; if (!r) throw new Error('location not found: ' + wc.location);
            var geo = { q: wc.location, lat: r.latitude, lon: r.longitude, name: r.name }; save('cmdGeo', geo); return geo;
          }));
    where.then(function (p) {
      var u = 'https://api.open-meteo.com/v1/forecast?latitude=' + p.lat + '&longitude=' + p.lon +
        '&current=temperature_2m,weather_code&daily=weather_code,temperature_2m_max,temperature_2m_min' +
        '&forecast_days=5&timezone=auto' + (wc.units === 'fahrenheit' ? '&temperature_unit=fahrenheit' : '');
      return direct(u).then(function (j) {
        var w = {
          place: p.name, at: Date.now(),
          current: { temp: j.current.temperature_2m, code: j.current.weather_code },
          daily: j.daily.time.map(function (t, i) {
            return { date: t, code: j.daily.weather_code[i], max: j.daily.temperature_2m_max[i], min: j.daily.temperature_2m_min[i] };
          })
        };
        save('cmdWeather', w); renderWeather(w);
      });
    }).catch(function (e) { console.warn('weather:', e.message); });
  }

  /* ---------- news ---------- */
  function parseFeed(xml, url) {
    var doc = new DOMParser().parseFromString(xml, 'text/xml');
    var src = (doc.querySelector('channel > title, feed > title') || {}).textContent || url.replace(/^https?:\/\/([^/]+).*/, '$1');
    var items = doc.querySelectorAll('item, entry');
    return Array.prototype.map.call(items, function (it) {
      var link = it.querySelector('link');
      var href = link ? (link.getAttribute('href') || link.textContent) : '';
      var date = it.querySelector('pubDate, updated, published');
      return {
        title: ((it.querySelector('title') || {}).textContent || '').trim(),
        link: (href || '').trim(),
        time: date ? Date.parse(date.textContent) || 0 : 0,
        source: src.replace(/\s+-\s+.*$/, '').trim()
      };
    }).filter(function (n) { return n.title; });
  }

  function loadNews() {
    var nc = cfg.news || {}, feeds = nc.feeds || [];
    if (!feeds.length) return;
    Promise.all(feeds.map(function (u) {
      return get(u, true).then(function (x) { return parseFeed(x, u); })
        .catch(function (e) { console.warn('news:', u, e.message); return []; });
    })).then(function (lists) {
      var all = [].concat.apply([], lists).sort(function (a, b) { return b.time - a.time; }).slice(0, nc.max || 20);
      if (!all.length) return;
      news = all; newsIdx = 0; save('cmdNews', all); showNews();
    });
  }

  function showNews() {
    if (!news.length) { document.body.classList.add('no-news'); return; }
    document.body.classList.remove('no-news');
    var n = news[newsIdx % news.length];
    [['.tk-text', n.title], ['.tk-src', n.source], ['.amb-headline', n.title], ['.amb-src', n.source]].forEach(function (p) {
      var el = $(p[0]); el.classList.remove('fade'); void el.offsetWidth; el.textContent = p[1]; el.classList.add('fade');
    });
  }

  function rotate() {
    clearInterval(newsTimer);
    newsTimer = setInterval(function () {
      if (document.hidden || !news.length) return;
      if (document.activeElement && document.activeElement.id === 'ticker') return; // don't move while reading
      newsIdx = (newsIdx + 1) % news.length; showNews();
    }, ((cfg.news || {}).rotateSeconds || 9) * 1000);
  }

  function currentNews() { return news.length ? news[newsIdx % news.length] : null; }
  function stepNews(d) { if (!news.length) return; newsIdx = (newsIdx + d + news.length) % news.length; showNews(); }

  /* ---------- ambient idle screen ---------- */
  function showAmbient() {
    if (ambientOn) return;
    ambientOn = true; document.documentElement.classList.add('ambient-on');
  }
  function hideAmbient() {
    if (!ambientOn) return false;
    ambientOn = false; document.documentElement.classList.remove('ambient-on');
    return true;
  }
  // Returns true if the key press was used to wake from ambient (caller should swallow it).
  function activity() {
    var woke = hideAmbient();
    clearTimeout(idleTimer);
    var s = cfg.idleSeconds == null ? 60 : cfg.idleSeconds;
    if (s > 0) idleTimer = setTimeout(showAmbient, s * 1000);
    return woke;
  }

  function init(settings) {
    cfg = settings || {};
    tick(); setInterval(tick, 10000);
    renderWeather(load('cmdWeather'));                 // instant from cache
    news = load('cmdNews') || []; showNews();
    var w = load('cmdWeather');
    setTimeout(loadWeather, w && Date.now() - w.at < 15 * 60000 ? 15 * 60000 - (Date.now() - w.at) : 300);
    setInterval(loadWeather, 15 * 60000);
    setTimeout(loadNews, 800); setInterval(loadNews, 10 * 60000);
    rotate();
    activity();
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden) { activity(); tick(); }
    });
  }

  return { init: init, toast: toast, activity: activity, showAmbient: showAmbient,
           currentNews: currentNews, stepNews: stepNews, _parseFeed: parseFeed };
})();
