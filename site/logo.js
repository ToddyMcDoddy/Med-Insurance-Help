(function () {
  'use strict';
  var html = document.documentElement;
  var app = document.getElementById('app');
  if (!app) return;

  var css = document.createElement('style');
  css.textContent =
    '.brandmark.ua-has-logo{width:46px;height:46px;background:transparent;border-radius:0;display:block}' +
    '.brandmark.ua-has-logo img{display:block;width:100%;height:100%;object-fit:contain}' +
    'html.ua11y-colorblind .brand-period{color:#2f6f9f}';
  document.head.appendChild(css);

  function wanted() {
    return html.classList.contains('ua11y-colorblind') ? './logo-colorblind.png' : './logo.png';
  }

  function place() {
    var marks = app.querySelectorAll('.brandmark');
    for (var i = 0; i < marks.length; i++) {
      var mark = marks[i];
      var img = mark.querySelector('img.ua-logo');
      if (!img) {
        mark.textContent = '';
        img = document.createElement('img');
        img.className = 'ua-logo';
        img.alt = '';
        img.width = 46;
        img.height = 46;
        img.decoding = 'async';
        mark.appendChild(img);
        mark.classList.add('ua-has-logo');
      }
      var src = wanted();
      if (img.getAttribute('src') !== src) img.setAttribute('src', src);
    }
  }

  var queued = false;
  function schedule() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(function () { queued = false; place(); });
  }

  new MutationObserver(schedule).observe(app, { childList: true, subtree: true });
  new MutationObserver(schedule).observe(html, { attributes: true, attributeFilter: ['class'] });
  schedule();
})();
