(function () {
  'use strict';
  var html = document.documentElement;
  var app = document.getElementById('app');
  if (!app) return;

  var css = document.createElement('style');
  css.textContent =
    '.hero.ua-has-logo{position:relative}' +
    '.ua-logo{position:absolute;right:3%;top:50%;transform:translateY(-50%);width:min(28%,300px);height:auto;pointer-events:none;z-index:1}' +
    '.hero.ua-has-logo .art-spark{display:none}' +
    '@media (max-width:1000px){.ua-logo{position:static;transform:none;display:block;margin:20px auto 0;width:min(70%,280px)}}';
  document.head.appendChild(css);

  function wanted() {
    return html.classList.contains('ua11y-colorblind') ? './logo-colorblind.png' : './logo.png';
  }

  function place() {
    var hero = app.querySelector('.hero');
    if (!hero) return;
    var img = hero.querySelector('img.ua-logo');
    if (!img) {
      img = document.createElement('img');
      img.className = 'ua-logo';
      img.alt = 'unsurance logo: a smiling blue figure with raised arms, a lightbulb above its head and a heart, with the words from unsure to insured';
      img.width = 760;
      img.height = 755;
      img.decoding = 'async';
      hero.appendChild(img);
      hero.classList.add('ua-has-logo');
    }
    var src = wanted();
    if (img.getAttribute('src') !== src) img.setAttribute('src', src);
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
