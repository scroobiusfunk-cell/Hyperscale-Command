(function () {
  'use strict';

  var grid = document.getElementById('grid');
  var status = document.getElementById('status');
  var clock = document.getElementById('clock');
  var COLS = 4;
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

  function move(delta) {
    var list = tiles();
    var i = list.indexOf(document.activeElement);
    if (i < 0) { list[0] && list[0].focus(); return; }
    var n = i + delta;
    if (n >= 0 && n < list.length) list[n].focus();
  }

  document.addEventListener('keydown', function (e) {
    switch (e.keyCode) {
      case 37: move(-1); break;           // left
      case 39: move(1); break;            // right
      case 38: move(-COLS); break;        // up
      case 40: move(COLS); break;         // down
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
        b.textContent = app.name;
        b.addEventListener('click', function () { launch(app); });
        grid.appendChild(b);
      });
      tiles()[0] && tiles()[0].focus();
    })
    .catch(function (e) { say('Could not load apps.json: ' + e); });
})();
