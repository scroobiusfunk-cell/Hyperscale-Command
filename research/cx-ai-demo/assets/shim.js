
<script>
(function () {
  var PROJECT = window.__cxProject || null;
  var HREF = window.__cxHref || '';
  function norm(href) {
    if (!href) return null;
    var raw = String(href);
    if (raw.charAt(0) === '#' || raw.indexOf('javascript:') === 0) return null;
    if (/^https?:/i.test(raw) && raw.indexOf(location.origin) !== 0) return null;
    var a = document.createElement('a');
    a.href = raw.replace(/^about:srcdoc/, '');
    var path = a.pathname + a.search;
    if (path.indexOf('project_id=') === -1 && PROJECT) {
      path += (path.indexOf('?') === -1 ? '?' : '&') + 'project_id=' + PROJECT;
    }
    return path;
  }
  window.__cxNav = function (href) {
    var path = norm(href);
    if (path) parent.__cxRoute(path);
    return false;
  };
  document.addEventListener('click', function (event) {
    var link = event.target.closest && event.target.closest('a[href]');
    if (!link) return;
    if (link.target === '_blank') { event.preventDefault(); parent.__cxNotice('Opens a PDF in the real app.'); return; }
    var path = norm(link.getAttribute('href'));
    if (!path) return;
    event.preventDefault();
    parent.__cxRoute(path);
  }, true);
  document.addEventListener('submit', function (event) {
    var form = event.target;
    var action = form.getAttribute('action') || '';
    event.preventDefault();
    if (action.indexOf('/select_project/') === 0) {
      parent.__cxRoute('/?project_id=' + action.split('/select_project/')[1]);
      return;
    }
    parent.__cxNotice('This demo is read-only - saving is disabled.');
  }, true);
  window.open = function (url) { parent.__cxNotice('Opens a PDF in the real app.'); return null; };
  var API = parent.__cxApi || {};
  var realFetch = window.fetch;
  window.fetch = function (input) {
    var url = typeof input === 'string' ? input : (input && input.url) || '';
    var key = url.split('?')[0];
    if (API.hasOwnProperty(key)) {
      return Promise.resolve(new Response(JSON.stringify(API[key]), {
        status: 200, headers: {'Content-Type': 'application/json'}
      }));
    }
    if (key.charAt(0) === '/') {
      parent.__cxNotice('This demo is read-only - saving is disabled.');
      return Promise.reject(new Error('demo'));
    }
    return realFetch.apply(this, arguments);
  };
})();
</script>
