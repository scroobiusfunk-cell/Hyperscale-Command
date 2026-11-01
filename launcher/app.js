(function () {
  'use strict';

  var grid = document.getElementById('grid');
  var status = document.getElementById('status');
  var clock = document.getElementById('clock');
  var BACK = 461; // webOS remote Back key

  function say(msg) { status.textContent = msg || ''; }

  function launch(app) {
    say('Launching ' + app.name + '…');
    if (window.webOS && webOS.service) {
      webOS.service.request('luna://com.webos.applicationManager', {
        method: 'launch',
        parameters: { id: app.id },
        onSuccess: function () { say(''); },
        onFailure: function (e) {
          say(app.name + ' failed: ' + (e && e.errorText || 'unknown error') + ' (check the app ID)');
        }
      });
    } else {
      say('webOSTV.js not loaded (running outside a TV?). Would launch: ' + app.id);
    }
  }

  function tiles() { return Array.prototype.slice.call(grid.children); }

  // Columns = tiles sharing the first tile's row (matches the CSS grid)
  function cols() {
    var list = tiles(), top = list[0].offsetTop, n = 0;
    while (n < list.length && list[n].offsetTop === top) n++;
    return n || 1;
  }

  function move(dir) {
    var list = tiles();
    var i = list.indexOf(document.activeElement);
    if (i < 0) { list[0] && list[0].focus(); return; }
    var c = cols();
    var n = dir === 'L' ? i - 1 : dir === 'R' ? i + 1 : dir === 'U' ? i - c : i + c;
    if (dir === 'L' && i % c === 0) return;       // don't wrap rows
    if (dir === 'R' && (i + 1) % c === 0) return;
    if (n >= 0 && n < list.length) list[n].focus();
  }

  document.addEventListener('keydown', function (e) {
    switch (e.keyCode) {
      case 37: move('L'); break;           // left
      case 39: move('R'); break;            // right
      case 38: move('U'); break;        // up
      case 40: move('D'); break;         // down
      case 13: if (document.activeElement.click) document.activeElement.click(); break;
      case BACK: if (window.webOS && webOS.platformBack) webOS.platformBack(); break;
      default: return;
    }
    e.preventDefault();
  });

  function tick() {
    var d = new Date();
    clock.textContent = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  tick(); setInterval(tick, 15000);

  fetch('apps.json')
    .then(function (r) { return r.json(); })
    .then(function (cfg) {
      cfg.apps.forEach(function (app) {
        var b = document.createElement('button');
        b.className = 'tile';
        b.setAttribute('role', 'menuitem');
        b.style.setProperty('--tile-color', app.color || '');
        b.innerHTML = '<span class="art"></span><span class="glass"></span>' +
                      '<span class="caption"><span class="name"></span><span class="sub"></span></span>';
        b.querySelector('.name').textContent = app.name;
        b.querySelector('.sub').textContent = app.subtitle || '';
        var art = b.querySelector('.art');
        if (app.art) {
          art.style.backgroundImage = 'url("' + app.art + '")';
        } else {
          art.className = 'art gen';
          art.innerHTML = '<span class="ring"></span><span class="mono"></span>';
          art.querySelector('.mono').textContent = app.name.charAt(0);
        }
        // Retint the wallpaper to the focused app, like tvOS
        b.addEventListener('focus', function () {
          document.body.style.setProperty('--accent', app.color || '#6ea8ff');
        });
        b.addEventListener('click', function () { launch(app); });
        grid.appendChild(b);
      });
      tiles()[0] && tiles()[0].focus();
    })
    .catch(function (e) { say('Could not load apps.json: ' + e); });
})();
