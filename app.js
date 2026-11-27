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

  // ---------- GitHub links, terminal commands, checksum ----------
  var CFG = window.CLIPDOCK_CONFIG || {};
  var repo = CFG.repo || R.repo || "AkarshanGhosh/ClipDock";
  $$(".gh-releases").forEach(function (a) { a.href = "https://github.com/" + repo + "/releases"; });
  $$(".gh-discuss").forEach(function (a) { a.href = "https://github.com/" + repo + "/discussions"; });
  $$(".gh-issue").forEach(function (a) { a.href = "https://github.com/" + repo + "/issues/new"; });
  var setupUrl = /^https?:/.test(location.protocol)
    ? new URL("downloads/ClipDock-Setup.bat", location.href).href
    : "https://raw.githubusercontent.com/" + repo + "/main/downloads/ClipDock-Setup.bat";
  var cmdEl = $("#cmd-cmd"), psEl = $("#cmd-ps"), shaEl = $("#sha");
  if (cmdEl) cmdEl.textContent = 'curl -L -o "%TEMP%\\ClipDock-Setup.bat" ' + setupUrl + ' && "%TEMP%\\ClipDock-Setup.bat"';
  if (psEl) psEl.textContent = 'curl.exe -L -o "$env:TEMP\\ClipDock-Setup.bat" ' + setupUrl + '; & "$env:TEMP\\ClipDock-Setup.bat"';
  if (shaEl) shaEl.textContent = R.sha256 || "(published with the next release)";
  $$(".copy").forEach(function (b) {
    b.addEventListener("click", function () {
      var target = $(b.getAttribute("data-copy"));
      if (!target) return;
      var text = target.textContent;
      var done = function () { b.textContent = "Copied ✓"; b.classList.add("ok"); setTimeout(function () { b.textContent = "Copy"; b.classList.remove("ok"); }, 1600); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, fallback);
      else fallback();
      function fallback() {
        var ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select();
        try { document.execCommand("copy"); done(); } catch (e) {} document.body.removeChild(ta);
      }
    });
  });

  // ---------- feedback form (Web3Forms when a key is set, otherwise a pre-filled GitHub issue) ----------
  var form = $("#fb-form");
  if (form) {
    var type = "idea", sending = false;
    var typeNames = { idea: "Idea", bug: "Problem", love: "Love it", question: "Question" };
    var note = $("#fb-note"), send = $("#fb-send");
    $$(".chip", form).forEach(function (c) {
      c.addEventListener("click", function () {
        $$(".chip", form).forEach(function (x) { x.classList.remove("on"); });
        c.classList.add("on"); type = c.getAttribute("data-type");
      });
    });
    function say(msg, bad) { note.textContent = msg; note.className = "fb-note" + (bad ? " bad" : ""); }
    function lastSent() { try { return +localStorage.getItem("clipdock-fb") || 0; } catch (e) { return 0; } }
    function markSent() { try { localStorage.setItem("clipdock-fb", String(Date.now())); } catch (e) {} }
    $("#fb-again").addEventListener("click", function () {
      $("#fb-done").hidden = true; form.classList.remove("sent"); $("#fb-msg").value = ""; say("");
    });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (sending) return;
      var msg = $("#fb-msg").value.trim(), mail = $("#fb-mail").value.trim();
      if ($("#fb-hp").value) return;                                   // bots fill the hidden field
      if (msg.length < 5) { say("Please write a few words first.", true); $("#fb-msg").focus(); return; }
      if (mail && !/^\S+@\S+\.\S+$/.test(mail)) { say("That e-mail doesn't look right.", true); return; }
      if (Date.now() - lastSent() < 30000) { say("Thanks! Please wait a moment before sending another.", true); return; }
      var subject = "ClipDock feedback: " + typeNames[type];
      var body = msg + "\n\n— ClipDock v" + (R.latest || "?") + " · " + typeNames[type];
      if (CFG.feedbackKey) {
        sending = true; send.disabled = true; say("Sending…");
        fetch("https://api.web3forms.com/submit", {
          method: "POST", headers: { "Content-Type": "application/json", "Accept": "application/json" },
          body: JSON.stringify({ access_key: CFG.feedbackKey, subject: subject, from_name: "ClipDock website",
            name: mail || "Anonymous", email: mail || undefined, message: body, type: typeNames[type], version: R.latest })
        }).then(function (r) { return r.json(); }).then(function (j) {
          if (!j.success) throw new Error(j.message || "failed");
          markSent(); say(""); form.classList.add("sent"); $("#fb-done").hidden = false;
        }).catch(function () { say("Couldn't send right now. Please try again in a moment.", true); })
          .then(function () { sending = false; send.disabled = false; });
      } else if (CFG.feedbackEmail) {
        markSent(); location.href = "mailto:" + CFG.feedbackEmail + "?subject=" + encodeURIComponent(subject) + "&body=" + encodeURIComponent(body);
        say("Opening your e-mail app…");
      } else {
        markSent();
        var q = "title=" + encodeURIComponent(typeNames[type] + ": ") + "&body=" + encodeURIComponent(body) +
                "&labels=" + (type === "bug" ? "bug" : "enhancement");
        window.open("https://github.com/" + repo + "/issues/new?" + q, "_blank", "noopener");
        say("Opened a pre-filled GitHub issue (a free GitHub account is needed to post it).");
      }
    });
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
