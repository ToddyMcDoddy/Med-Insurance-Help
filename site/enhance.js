// Small add-on for the Unsurance front end (loaded after the app).
// 1) Makes long waits obvious and warns before a refresh would lose work.
// 2) Cost estimate: picks "copay vs coinsurance" and the copay type for the user.
(() => {
  let services = null;
  const norm = (s) =>
    String(s || "").toLowerCase().replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim();

  async function loadServices() {
    if (services) return services;
    try {
      const r = await fetch("/api/services");
      services = r.ok ? (await r.json()).services || [] : [];
    } catch {
      services = [];
    }
    return services;
  }

  function match(text) {
    const t = norm(text);
    if (!t) return null;
    let loose = null;
    for (const s of services || []) {
      const names = [s.service_name, ...(s.aliases || [])].map(norm).filter(Boolean);
      if (names.includes(t)) return s;
      if (!loose && names.some((n) => n.includes(t) || t.includes(n))) loose = s;
    }
    return loose;
  }

  function enhanceCost(form) {
    const svc = form.querySelector('input[name="service"]');
    const amt = form.querySelector('input[name="allowed_amount"]');
    const kind = form.querySelector('select[name="kind"]');
    const copay = form.querySelector('select[name="copay_type"]');
    if (!svc || !amt || !kind || !copay || svc.readOnly) return; // preview mode: leave alone

    // Hide the insurance jargon; we choose these for the user.
    const kindLabel = kind.closest("label");
    const copayLabel = form.querySelector("#copay-label");
    if (kindLabel) kindLabel.style.display = "none";
    if (copayLabel) copayLabel.style.display = "none";

    // Suggestions while typing.
    const list = document.createElement("datalist");
    list.id = "svc-list";
    (services || []).forEach((s) => {
      const o = document.createElement("option");
      o.value = s.service_name;
      list.appendChild(o);
    });
    svc.setAttribute("list", "svc-list");
    svc.setAttribute("placeholder", "Start typing: MRI, ER visit, blood test…");
    const svcLabel = svc.closest("label");
    svcLabel.appendChild(list);

    const amtLabel = amt.closest("label");
    if (amtLabel && amtLabel.firstChild && amtLabel.firstChild.nodeType === 3) {
      amtLabel.firstChild.nodeValue = "Typical cost ($). Change it if you know your actual price";
    }

    const hint = document.createElement("p");
    hint.className = "fine";
    hint.setAttribute("aria-live", "polite");
    svcLabel.after(hint);

    let userEditedAmount = false;
    amt.addEventListener("input", () => {
      userEditedAmount = true;
    });

    const apply = () => {
      const s = match(svc.value);
      if (s) {
        const isCopay = s.kind === "copay";
        kind.value = isCopay ? "copay" : "coinsurance";
        copay.value = s.copay_type || "primary_care";
        if (!userEditedAmount || !amt.value) {
          amt.value = s.illustrative_allowed_amount;
          userEditedAmount = false;
        }
        hint.textContent =
          s.service_name +
          ": " +
          (isCopay
            ? "your plan charges a flat copay for this, and your deductible does not apply."
            : "you pay your deductible first, then a percentage (coinsurance) of the rest.") +
          " The price shown is a typical demo amount.";
      } else {
        kind.value = "coinsurance";
        if (!userEditedAmount) amt.value = "";
        hint.textContent = svc.value.trim()
          ? "We don't have a typical price for this one. Enter the amount from your bill or insurer. We'll treat it as deductible plus a percentage (coinsurance). Not sure? Ask in Chat."
          : "";
      }
    };
    svc.addEventListener("input", apply);
    svc.addEventListener("change", apply);
    apply();
  }

  async function run() {
    const root = document.getElementById("app");
    if (!root) return;
    root.querySelectorAll(".loading:not([data-n])").forEach((el) => {
      el.dataset.n = "1";
      el.style.position = "sticky";
      el.style.top = "8px";
      el.style.zIndex = "20";
      const note = document.createElement("span");
      note.style.display = "block";
      note.textContent = "This can take up to 2 minutes. Please keep this page open and don't refresh.";
      el.appendChild(note);
    });
    const form = root.querySelector("#estimate-form");
    if (form && !form.dataset.e) {
      form.dataset.e = "1";
      await loadServices();
      if (form.isConnected) enhanceCost(form);
    }
  }

  const root = document.getElementById("app");
  if (root) new MutationObserver(run).observe(root, { childList: true, subtree: true });
  run();

  // Warn before a refresh or close while the app is working.
  window.addEventListener("beforeunload", (e) => {
    if (document.querySelector("#app .loading")) {
      e.preventDefault();
      e.returnValue = "";
    }
  });
})();
