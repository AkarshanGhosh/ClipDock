(function () {
  "use strict";

  // version.js (written by release.py) defines window.CLIPDOCK_RELEASE.
  // The fallback keeps the page working if that file is missing.
  var R = window.CLIPDOCK_RELEASE || {
    latest: "1.0.0",
    released: "",
    size_bytes: 0,
    download: "downloads/ClipDock-latest.zip",
    releases: [],
  };

  var $ = function (s, ctx) { return (ctx || document).querySelector(s); };
  var $$ = function (s, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(s)); };

  function fmtSize(b) {
    if (!b) return "small download";
    return b < 1048576 ? Math.round(b / 1024) + " KB" : (b / 1048576).toFixed(1) + " MB";
  }
  function fmtDate(d) {
    if (!d) return "";
    var dt = new Date(d + "T00:00:00");
    return isNaN(dt) ? d : dt.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  }

  // ---------- version + download ----------
  $$(".ver").forEach(function (el) { el.textContent = R.latest; });
  $$(".size").forEach(function (el) { el.textContent = fmtSize(R.size_bytes); });
  $$(".released").forEach(function (el) { el.textContent = fmtDate(R.released); });
  var dl = R.download || "downloads/ClipDock-latest.zip";
  // cache-bust so visitors always get the newest file, not a cached older one
  var dlUrl = dl + (dl.indexOf("?") < 0 ? "?v=" + encodeURIComponent(R.latest) : "");
  $$("[data-download]").forEach(function (a) {
    a.setAttribute("href", dlUrl);
    a.setAttribute("download", "ClipDock-v" + R.latest + ".zip");
  });

  // ---------- changelog ----------
  var log = $("#log");
  if (log) {
    var rel = R.releases && R.releases.length ? R.releases : [{ version: R.latest, date: R.released, notes: ["Initial release"] }];
    log.innerHTML = rel.map(function (r, i) {
      var notes = (r.notes || []).map(function (n) { return "<li>" + esc(n) + "</li>"; }).join("");
      return '<div class="rel reveal"><h3>v' + esc(r.version) + (i === 0 ? ' <span class="tag">Latest</span>' : "") +
        '</h3><time>' + esc(fmtDate(r.date)) + "</time><ul>" + notes + "</ul></div>";
    }).join("");
  }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // ---------- nav shadow + cursor glow ----------
  var nav = $("nav");
  window.addEventListener("scroll", function () { nav.classList.toggle("scrolled", window.scrollY > 8); }, { passive: true });
  var glow = $(".glow");
  window.addEventListener("pointermove", function (e) {
    glow.style.setProperty("--mx", e.clientX + "px");
    glow.style.setProperty("--my", e.clientY + "px");
  }, { passive: true });

  // ---------- scroll reveal ----------
  var items = $$(".reveal");
  items.forEach(function (el, i) { if (!el.style.getPropertyValue("--d")) el.style.setProperty("--d", (i % 4) * 0.08 + "s"); });
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); } });
    }, { threshold: 0.12 });
    items.forEach(function (el) { io.observe(el); });
  } else {
    items.forEach(function (el) { el.classList.add("in"); });
  }

  // ---------- hero demo: click a card -> it "pastes" into the notepad ----------
  var cards = $$(".dk-card");
  var typed = $("#typed");
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var idx = 0, lines = [], busy = false;

  function typeInto(text, done) {
    var i = 0;
    var base = lines.join("\n") + (lines.length ? "\n" : "");
    (function step() {
      typed.textContent = base + text.slice(0, i);
      if (i++ < text.length) setTimeout(step, reduce ? 0 : 22);
      else done();
    })();
  }
  function cycle() {
    if (busy) return;
    busy = true;
    cards.forEach(function (c) { c.classList.remove("active"); });
    var c = cards[idx % cards.length];
    c.classList.add("active");
    var text = c.getAttribute("data-t");
    setTimeout(function () {
      typeInto(text, function () {
        lines.push(text);
        if (lines.length > 4) lines = [];
        idx++;
        busy = false;
        setTimeout(function () { c.classList.remove("active"); }, 700);
      });
    }, 650);
  }
  if (cards.length && typed) {
    cycle();
    setInterval(cycle, 3600);
  }

  // ---------- download toast ----------
  var toast = $("#toast"), tt;
  $$("[data-download]").forEach(function (a) {
    a.addEventListener("click", function () {
      toast.classList.add("show");
      clearTimeout(tt);
      tt = setTimeout(function () { toast.classList.remove("show"); }, 9000);
    });
  });
  $("#toast-close").addEventListener("click", function () { toast.classList.remove("show"); });
})();
