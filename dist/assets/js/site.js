/* =========================================================================
   Svarvāṇī Prakāśa · samskrtam.info — site behaviour
   No framework, no jQuery. Every interaction the original site offered is
   kept; each one is rebuilt to be keyboard-reachable, announced to screen
   readers, and remembered between visits.
   ========================================================================= */
(function () {
  "use strict";

  var $ = function (sel, ctx) { return (ctx || document).querySelector(sel); };
  var $$ = function (sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); };

  /* ---- tiny persistence helper (private browsing throws) --------------- */
  var store = {
    get: function (k, fallback) {
      try { var v = localStorage.getItem("svp:" + k); return v === null ? fallback : v; }
      catch (e) { return fallback; }
    },
    set: function (k, v) {
      try { localStorage.setItem("svp:" + k, v); } catch (e) { /* ignore */ }
    }
  };

  /* ===================================================================== */
  /* Theme                                                                  */
  /* ===================================================================== */
  function initTheme() {
    var root = document.documentElement;
    var btn = $("[data-theme-toggle]");
    var saved = store.get("theme", "");
    if (saved === "light" || saved === "dark") root.setAttribute("data-theme", saved);

    function current() {
      var explicit = root.getAttribute("data-theme");
      if (explicit) return explicit;
      return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    function paint() {
      if (!btn) return;
      var dark = current() === "dark";
      btn.setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
      btn.setAttribute("aria-pressed", String(dark));
    }
    if (btn) {
      btn.addEventListener("click", function () {
        var next = current() === "dark" ? "light" : "dark";
        root.setAttribute("data-theme", next);
        store.set("theme", next);
        paint();
      });
    }
    paint();
  }

  /* ===================================================================== */
  /* Mobile navigation                                                      */
  /* ===================================================================== */
  function initNav() {
    var toggle = $("[data-nav-toggle]");
    var nav = $("#site-nav");
    if (!toggle || !nav) return;

    function setOpen(open) {
      nav.setAttribute("data-open", String(open));
      toggle.setAttribute("aria-expanded", String(open));
    }
    toggle.addEventListener("click", function () {
      setOpen(nav.getAttribute("data-open") !== "true");
    });
    nav.addEventListener("click", function (e) {
      if (e.target.closest("a")) setOpen(false);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") setOpen(false);
    });
    window.addEventListener("resize", function () {
      if (window.innerWidth > 1020) setOpen(false);
    });
  }

  /* ===================================================================== */
  /* Reading preferences (text size) — the corpora are dense, readers need  */
  /* to be able to make them bigger.                                        */
  /* ===================================================================== */
  var SIZES = { s: 0.9, m: 1, l: 1.15, xl: 1.3 };

  function applyReadScale(key) {
    document.documentElement.style.setProperty("--read-scale", String(SIZES[key] || 1));
    $$("[data-size]").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-size") === key));
    });
  }

  function initPrefs() {
    applyReadScale(store.get("size", "m"));
    var btn = $("[data-prefs-toggle]");
    var panel = $("#prefs-panel");
    if (btn && panel) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        panel.hidden = !panel.hidden;
        btn.setAttribute("aria-expanded", String(!panel.hidden));
      });
      document.addEventListener("click", function (e) {
        if (!panel.hidden && !panel.contains(e.target) && e.target !== btn) {
          panel.hidden = true;
          btn.setAttribute("aria-expanded", "false");
        }
      });
      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && !panel.hidden) {
          panel.hidden = true;
          btn.setAttribute("aria-expanded", "false");
          btn.focus();
        }
      });
    }
    $$("[data-size]").forEach(function (b) {
      b.addEventListener("click", function () {
        var key = b.getAttribute("data-size");
        store.set("size", key);
        applyReadScale(key);
      });
    });
  }

  /* ===================================================================== */
  /* Script conversion (lipi.js) — Devanāgarī / Telugu / IAST for the whole   */
  /* page, replacing the CDN transliteration plugin the original site used.   */
  /* ===================================================================== */
  function initLipi() {
    if (!window.Lipi) return;
    var buttons = $$("[data-lipi-set]");
    if (!buttons.length) return;

    function paint(script) {
      buttons.forEach(function (b) {
        b.setAttribute("aria-pressed", String(b.getAttribute("data-lipi-set") === script));
      });
    }
    function set(script) {
      window.Lipi.apply(script);
      store.set("lipi", script);
      paint(script);
    }
    buttons.forEach(function (b) {
      b.addEventListener("click", function () { set(b.getAttribute("data-lipi-set")); });
    });

    var saved = store.get("lipi", "devanagari");
    paint(saved);
    if (saved !== "devanagari") {
      /* let first paint land before rewriting the document */
      requestAnimationFrame(function () { window.Lipi.apply(saved); });
    }
  }

  /* ===================================================================== */
  /* Layer toggles — the modern form of the original's on/off buttons.      */
  /* A "layer" is one register of a verse: मूलम् / पदविभागः / अन्वयः / …    */
  /* ===================================================================== */
  function initLayers() {
    var root = $("[data-layers]");
    if (!root) return;
    var key = "layers:" + (root.getAttribute("data-layers") || "default");
    var all = $$("[data-layer-toggle]", root).map(function (b) {
      return b.getAttribute("data-layer-toggle");
    });

    var saved = store.get(key, null);
    var on = saved === null ? all.slice() : saved.split(",").filter(Boolean);
    if (!on.length) on = all.slice();

    function paint() {
      $$("[data-layer-toggle]", root).forEach(function (b) {
        b.setAttribute("aria-pressed", String(on.indexOf(b.getAttribute("data-layer-toggle")) > -1));
      });
      $$(".layer[data-layer]").forEach(function (el) {
        el.hidden = on.indexOf(el.getAttribute("data-layer")) === -1;
      });
      store.set(key, on.join(","));
    }

    $$("[data-layer-toggle]", root).forEach(function (b) {
      b.addEventListener("click", function () {
        var name = b.getAttribute("data-layer-toggle");
        var i = on.indexOf(name);
        if (i > -1) on.splice(i, 1); else on.push(name);
        paint();
      });
    });

    var showAll = $("[data-layers-all]", root);
    if (showAll) {
      showAll.addEventListener("click", function () { on = all.slice(); paint(); });
    }
    var showNone = $("[data-layers-none]", root);
    if (showNone) {
      showNone.addEventListener("click", function () { on = ["moolam"]; paint(); });
    }
    paint();
  }

  /* per-verse overrides: a reader can open one extra register for a single
     verse without changing the page-wide setting */
  function initVerseTools() {
    $$("[data-verse-toggle]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var verse = btn.closest(".verse");
        var name = btn.getAttribute("data-verse-toggle");
        if (!verse) return;
        var row = $('.layer[data-layer="' + name + '"]', verse);
        if (!row) return;
        row.hidden = !row.hidden;
        btn.setAttribute("aria-pressed", String(!row.hidden));
      });
    });
  }

  /* ===================================================================== */
  /* Speaker filter (Gītā, Viṣṇusahasranāma)                                */
  /* ===================================================================== */
  function initSpeakers() {
    var root = $("[data-speakers]");
    if (!root) return;
    var all = $$("[data-speaker-toggle]", root).map(function (b) {
      return b.getAttribute("data-speaker-toggle");
    });
    var on = (store.get("speakers", all.join(",")) || "").split(",").filter(Boolean);
    if (!on.length) on = all.slice();

    function paint() {
      $$("[data-speaker-toggle]", root).forEach(function (b) {
        b.setAttribute("aria-pressed", String(on.indexOf(b.getAttribute("data-speaker-toggle")) > -1));
      });
      $$(".speech[data-speaker]").forEach(function (el) {
        el.hidden = on.indexOf(el.getAttribute("data-speaker")) === -1;
      });
      // hide a chapter heading whose speeches are all filtered out
      $$("[data-chapter]").forEach(function (ch) {
        var visible = $$(".speech", ch).some(function (s) { return !s.hidden; });
        var head = document.getElementById("head-" + ch.getAttribute("data-chapter"));
        if (head) head.hidden = !visible;
        ch.hidden = !visible;
      });
      store.set("speakers", on.join(","));
    }

    $$("[data-speaker-toggle]", root).forEach(function (b) {
      b.addEventListener("click", function () {
        var name = b.getAttribute("data-speaker-toggle");
        var i = on.indexOf(name);
        if (i > -1) on.splice(i, 1); else on.push(name);
        paint();
      });
    });
    paint();
  }

  /* ===================================================================== */
  /* Script switch for stotra cards (Devanāgarī / Telugu / IAST)            */
  /* ===================================================================== */
  function initScripts() {
    var root = $("[data-scripts]");
    if (!root) return;
    var all = $$("[data-script-toggle]", root).map(function (b) {
      return b.getAttribute("data-script-toggle");
    });
    var on = (store.get("scripts", all.join(",")) || "").split(",").filter(Boolean);
    if (!on.length) on = all.slice();

    function paint() {
      $$("[data-script-toggle]", root).forEach(function (b) {
        b.setAttribute("aria-pressed", String(on.indexOf(b.getAttribute("data-script-toggle")) > -1));
      });
      $$("[data-script]").forEach(function (el) {
        el.hidden = on.indexOf(el.getAttribute("data-script")) === -1;
      });
      store.set("scripts", on.join(","));
    }
    $$("[data-script-toggle]", root).forEach(function (b) {
      b.addEventListener("click", function () {
        var name = b.getAttribute("data-script-toggle");
        var i = on.indexOf(name);
        if (i > -1) on.splice(i, 1); else on.push(name);
        if (!on.length) on = all.slice();
        paint();
      });
    });
    paint();
  }

  /* ===================================================================== */
  /* Filter / search over any list of [data-search] items                   */
  /* ===================================================================== */
  function normalise(s) {
    return (s || "")
      .toLowerCase()
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "");
  }

  function initFilters() {
    $$("[data-filter-input]").forEach(function (input) {
      var scope = document.getElementById(input.getAttribute("data-filter-input"));
      if (!scope) return;
      var items = $$("[data-search]", scope);
      var counter = document.getElementById(input.getAttribute("data-filter-count") || "");
      var clear = input.parentElement && $(".field__clear", input.parentElement);

      /* A bare `data-search` means "search my own text". Building those
         haystacks costs a pass over the DOM, so it happens on the first
         keystroke rather than on page load — the corpora run to thousands
         of entries and most visits never type anything. */
      var haystacks = null;
      function index() {
        if (haystacks) return haystacks;
        haystacks = items.map(function (el) {
          var attr = el.getAttribute("data-search");
          return normalise(attr || el.textContent);
        });
        return haystacks;
      }

      function run() {
        var q = normalise(input.value.trim());
        var shown = 0;
        var hay = q ? index() : null;
        for (var i = 0; i < items.length; i++) {
          var hit = !q || hay[i].indexOf(q) > -1;
          items[i].hidden = !hit;
          if (hit) shown++;
        }
        if (counter) {
          counter.textContent = q
            ? shown + " of " + items.length + " match “" + input.value.trim() + "”"
            : items.length + " entries";
        }
        if (clear) clear.hidden = !input.value;
        var empty = $("[data-empty]", scope);
        if (empty) empty.hidden = shown !== 0;
      }

      var t;
      input.addEventListener("input", function () {
        clearTimeout(t);
        t = setTimeout(run, 110);
      });
      if (clear) {
        clear.addEventListener("click", function () {
          input.value = "";
          run();
          input.focus();
        });
      }
      run();
    });
  }

  /* ===================================================================== */
  /* Puzzle answers                                                         */
  /* ===================================================================== */
  function initPuzzles() {
    function toggle(btn) {
      var wrap = btn.closest(".qa");
      if (!wrap) return;
      var ans = $(".qa__a", wrap);
      var reveal = $(".qa__btn", wrap);
      if (!ans || !reveal) return;
      ans.hidden = !ans.hidden;
      reveal.setAttribute("aria-expanded", String(!ans.hidden));
    }
    $$(".qa__btn").forEach(function (b) {
      b.addEventListener("click", function () { toggle(b); });
    });
    $$(".qa__q").forEach(function (q) {
      q.addEventListener("click", function () { toggle(q); });
      q.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(q); }
      });
    });
    $$("[data-reveal-all]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var scope = btn.closest(".puzzle") || document;
        var open = btn.getAttribute("aria-pressed") !== "true";
        $$(".qa__a", scope).forEach(function (a) { a.hidden = !open; });
        $$(".qa__btn", scope).forEach(function (b) { b.setAttribute("aria-expanded", String(open)); });
        btn.setAttribute("aria-pressed", String(open));
        btn.textContent = open ? btn.getAttribute("data-label-hide") : btn.getAttribute("data-label-show");
      });
    });
  }

  /* ===================================================================== */
  /* Lazy YouTube facades — no third-party script until the reader asks     */
  /* ===================================================================== */
  function initVideos() {
    $$(".video--lazy img").forEach(function (img) {
      img.addEventListener("error", function () { img.style.display = "none"; });
      if (img.complete && img.naturalWidth === 0) img.style.display = "none";
    });
    $$(".video--lazy").forEach(function (el) {
      el.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); el.click(); }
      });
      el.addEventListener("click", function () {
        var id = el.getAttribute("data-yt");
        if (!id) return;
        var frame = document.createElement("iframe");
        frame.src = "https://www.youtube-nocookie.com/embed/" + id + "?autoplay=1&rel=0";
        frame.title = el.getAttribute("data-title") || "Video";
        frame.allow = "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture";
        frame.allowFullscreen = true;
        frame.loading = "lazy";
        el.replaceChildren(frame);
        el.classList.remove("video--lazy");
      });
    });
  }

  /* ===================================================================== */
  /* Reading progress + back to top                                        */
  /* ===================================================================== */
  function initProgress() {
    var bar = $(".progress");
    var top = $(".to-top");
    if (!bar && !top) return;
    var ticking = false;
    function update() {
      var h = document.documentElement.scrollHeight - window.innerHeight;
      var y = window.scrollY;
      if (bar) bar.style.width = (h > 0 ? Math.min(100, (y / h) * 100) : 0) + "%";
      if (top) top.setAttribute("data-visible", String(y > 700));
      ticking = false;
    }
    window.addEventListener("scroll", function () {
      if (!ticking) { ticking = true; requestAnimationFrame(update); }
    }, { passive: true });
    if (top) {
      top.addEventListener("click", function () {
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    }
    update();
  }

  /* ===================================================================== */
  /* Deep-link flash: /texts/hitopadesha/#v-1.42 highlights that verse      */
  /* ===================================================================== */
  function initHashFlash() {
    function flash() {
      var id = location.hash.slice(1);
      if (!id) return;
      var el = document.getElementById(id);
      if (!el) return;
      el.classList.add("is-flash");
      setTimeout(function () { el.classList.remove("is-flash"); }, 2400);
    }
    window.addEventListener("hashchange", flash);
    flash();
  }

  /* ===================================================================== */
  /* Copy a verse's permalink                                               */
  /* ===================================================================== */
  function initCopyLinks() {
    $$("[data-copy-link]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-copy-link");
        var url = location.origin + location.pathname + "#" + id;
        var done = function () {
          var was = btn.getAttribute("aria-label");
          btn.setAttribute("aria-label", "Link copied");
          btn.classList.add("is-copied");
          setTimeout(function () {
            btn.setAttribute("aria-label", was || "Copy link");
            btn.classList.remove("is-copied");
          }, 1600);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(url).then(done, function () { location.hash = id; });
        } else {
          location.hash = id;
        }
      });
    });
  }

  /* ===================================================================== */
  document.addEventListener("DOMContentLoaded", function () {
    initTheme();
    initNav();
    initPrefs();
    initLipi();
    initLayers();
    initVerseTools();
    initSpeakers();
    initScripts();
    initFilters();
    initPuzzles();
    initVideos();
    initProgress();
    initHashFlash();
    initCopyLinks();
  });
})();
