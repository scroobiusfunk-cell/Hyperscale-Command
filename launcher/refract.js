// Edge refraction for the focused tile's caption (liquid-glass technique):
// bake a displacement map on a canvas -> feImage -> feDisplacementMap -> feGaussianBlur,
// and point backdrop-filter at it. Chromium only; elsewhere the plain blur stays.
(function () {
  'use strict';
  var ua = navigator.userAgent;
  var chromium = /Chrome\/|Web0S|WebAppManager/.test(ua) && !/Edge?\/|Firefox\//.test(ua);
  if (!chromium) return;
  try { if (JSON.parse(localStorage.getItem('noRefraction'))) return; } catch (e) {}

  var W = 316, H = 60, EDGE = 26, SCALE = 56;

  function bakeMap() {
    var c = document.createElement('canvas'); c.width = W; c.height = H;
    var g = c.getContext('2d'), img = g.createImageData(W, H);
    for (var y = 0; y < H; y++) for (var x = 0; x < W; x++) {
      var dx = Math.min(x, W - 1 - x), dy = Math.min(y, H - 1 - y);
      var tx = Math.pow(Math.max(0, 1 - dx / EDGE), 2) * (x < W / 2 ? 1 : -1);
      var ty = Math.pow(Math.max(0, 1 - dy / EDGE), 2) * (y < H / 2 ? 1 : -1);
      var i = (y * W + x) * 4;
      img.data[i]     = Math.round(127.5 + 127.5 * tx);   // neutral is 127.5, not 128 (rounds to 128: see SCALE bias note)
      img.data[i + 1] = Math.round(127.5 + 127.5 * ty);
      img.data[i + 2] = 128; img.data[i + 3] = 255;
    }
    g.putImageData(img, 0, 0);
    return c.toDataURL('image/png');
  }

  var ns = 'http://www.w3.org/2000/svg', xl = 'http://www.w3.org/1999/xlink';
  var svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('width', '0'); svg.setAttribute('height', '0');
  svg.style.cssText = 'position:absolute;pointer-events:none';
  svg.innerHTML =
    '<filter id="lg-caption" filterUnits="userSpaceOnUse" primitiveUnits="userSpaceOnUse" ' +
    'x="0" y="0" width="' + W + '" height="' + H + '" color-interpolation-filters="sRGB">' +
    '<feImage id="lg-map" x="0" y="0" width="' + W + '" height="' + H + '" result="map" preserveAspectRatio="none"/>' +
    '<feDisplacementMap in="SourceGraphic" in2="map" scale="' + SCALE + '" xChannelSelector="R" yChannelSelector="G" result="bent"/>' +
    '<feGaussianBlur in="bent" stdDeviation="3"/></filter>';
  document.body.appendChild(svg);
  var url = bakeMap(), fi = svg.querySelector('#lg-map');
  fi.setAttribute('href', url); fi.setAttributeNS(xl, 'xlink:href', url);

  document.documentElement.className += ' refract';
})();
