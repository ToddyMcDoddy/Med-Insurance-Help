// Shows chat answers with simple formatting (bold, bullets, numbered lists).
// Safe by design: it only builds text nodes, never HTML, so no links or images can appear.
(() => {
  const BULLET = /^\s*[*\-\u2022]\s+(.*)$/;
  const NUMBER = /^\s*\d+[.)]\s+(.*)$/;
  const HEADING = /^\s*#{1,6}\s+(.*)$/;

  function inline(parent, text) {
    text.split(/\*\*(.+?)\*\*/g).forEach((part, i) => {
      if (!part) return;
      if (i % 2 === 1) {
        const b = document.createElement("strong");
        b.textContent = part;
        parent.appendChild(b);
      } else {
        parent.appendChild(document.createTextNode(part.replace(/\*\*/g, "")));
      }
    });
  }

  function format(el) {
    el.dataset.f = "1";
    const lines = el.textContent.split(/\r?\n/);
    el.textContent = "";
    el.style.whiteSpace = "normal";
    let list = null;
    let listType = "";
    const closeList = () => {
      list = null;
      listType = "";
    };
    const addTo = (tag, text) => {
      if (!list || listType !== tag) {
        list = document.createElement(tag);
        list.style.margin = "0.3em 0 0.7em";
        list.style.paddingLeft = "1.3em";
        el.appendChild(list);
        listType = tag;
      }
      const li = document.createElement("li");
      li.style.margin = "0.25em 0";
      inline(li, text);
      list.appendChild(li);
    };
    lines.forEach((line) => {
      let m;
      if ((m = line.match(BULLET))) return addTo("ul", m[1]);
      if ((m = line.match(NUMBER))) return addTo("ol", m[1]);
      closeList();
      if (!line.trim()) return;
      const p = document.createElement("p");
      p.style.margin = "0 0 0.7em";
      if ((m = line.match(HEADING))) {
        const b = document.createElement("strong");
        b.textContent = m[1].replace(/\*\*/g, "");
        p.appendChild(b);
      } else {
        inline(p, line);
      }
      el.appendChild(p);
    });
  }

  function run() {
    document.querySelectorAll("#app .answer-text:not([data-f])").forEach(format);
  }
  const root = document.getElementById("app");
  if (root) new MutationObserver(run).observe(root, { childList: true, subtree: true });
  run();
})();
