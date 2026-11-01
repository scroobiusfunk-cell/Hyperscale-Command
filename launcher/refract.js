// Edge refraction for the focused tile's caption (liquid-glass technique):
// bake a displacement map on a canvas -> feImage -> feDisplacementMap -> feGaussianBlur,
// and point backdrop-filter at it. Chromium only; elsewhere the plain blur stays.
(function () {
  'use strict';
  var ua = navigator.userAgent;
  var chromium = /Chrome\/|Web0S|WebAppManager/.test(ua) && !/Edge?\/|Firefox\//.test(ua);
  if (!chromium) return;
  try { if (JSON.parse(localStorage.getItem('noRefraction'))) return; } catch (e) {}

  var ns = 'http://www.w3.org/2000/svg', xl = 'http://www.w3.org/1999/xlink';
  var svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('width', '0'); svg.setAttribute('height', '0');
  svg.style.cssText = 'position:absolute;pointer-events:none';
  document.body.appendChild(svg);

  // Bake a W x H displacement map: neutral in the middle, pushing inward within EDGE px of each side.
  function bakeMap(W, H, EDGE) {
    var c = document.createElement('canvas'); c.width = W; c.height = H;
    var g = c.getContext('2d'), img = g.createImageData(W, H);
    for (var y = 0; y < H; y++) for (var x = 0; x < W; x++) {
      var dx = Math.min(x, W - 1 - x), dy = Math.min(y, H - 1 - y);
      var tx = Math.pow(Math.max(0, 1 - dx / EDGE), 2) * (x < W / 2 ? 1 : -1);
      var ty = Math.pow(Math.max(0, 1 - dy / EDGE), 2) * (y < H / 2 ? 1 : -1);
      var i = (y * W + x) * 4;
      img.data[i]     = Math.round(127.5 + 127.5 * tx);   // neutral rounds to 128 (tiny bias, acceptable)
      img.data[i + 1] = Math.round(127.5 + 127.5 * ty);
      img.data[i + 2] = 128; img.data[i + 3] = 255;
    }
    g.putImageData(img, 0, 0);
    return c.toDataURL('image/png');
  }

  // One filter per element size: #id must match the element's pixel size.
  function addFilter(id, W, H, EDGE, SCALE, BLUR) {
    var f = document.createElementNS(ns, 'filter');
    f.setAttribute('id', id); f.setAttribute('filterUnits', 'userSpaceOnUse');
    f.setAttribute('primitiveUnits', 'userSpaceOnUse');
    f.setAttribute('x', '0'); f.setAttribute('y', '0'); f.setAttribute('width', W); f.setAttribute('height', H);
    f.setAttribute('color-interpolation-filters', 'sRGB');
    f.innerHTML =
      '<feImage x="0" y="0" width="' + W + '" height="' + H + '" result="map" preserveAspectRatio="none"/>' +
      '<feDisplacementMap in="SourceGraphic" in2="map" scale="' + SCALE + '" xChannelSelector="R" yChannelSelector="G" result="bent"/>' +
      '<feGaussianBlur in="bent" stdDeviation="' + BLUR + '"/>';
    svg.appendChild(f);
    var url = bakeMap(W, H, EDGE), fi = f.firstChild;
    fi.setAttribute('href', url); fi.setAttributeNS(xl, 'xlink:href', url);
  }

  addFilter('lg-caption', 316, 60, 26, 56, 3);     // tile caption (focused tile only)
  addFilter('lg-hero', 620, 250, 44, 90, 3);       // hero title panel (always the focused app)

  document.documentElement.className += ' refract';
})();
