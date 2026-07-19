"use strict";
// Minimal, dependency-free dashboard client. Polls the read-only REST API
// and renders it; control buttons POST with the locally-stored API key.
// No framework, no CDN — works offline on Railway/Docker/laptop alike.

var POLL_MS = 5000;
var $ = function (id) { return document.getElementById(id); };

var apikeyInput = $("apikey");
apikeyInput.value = localStorage.getItem("turtle_api_key") || "";
apikeyInput.addEventListener("change", function () {
  localStorage.setItem("turtle_api_key", apikeyInput.value.trim());
});

function headers() {
  var h = { "Content-Type": "application/json" };
  var k = (apikeyInput.value || "").trim();
  if (k) { h["X-API-Key"] = k; }
  return h;
}

function setConn(text, cls) {
  var el = $("conn");
  el.textContent = text;
  el.className = "pill " + cls;
}

function setKill(active) {
  var el = $("kill");
  el.textContent = active ? "ACTIVE" : "off";
  el.style.color = active ? "var(--danger)" : "var(--ok)";
}

function fmt(v) { return (v === null || v === undefined) ? "—" : v; }

async function refresh() {
  try {
    var [statusRes, reportsRes] = await Promise.all([
      fetch("/status"), fetch("/reports")
    ]);
    if (!statusRes.ok) throw new Error("status " + statusRes.status);
    var s = await statusRes.json();
    var r = reportsRes.ok ? await reportsRes.json() : {};

    $("engine").textContent = s.is_started ? "started" : "stopped";
    $("state").textContent = fmt(s.current_state);
    setKill(!!s.kill_switch_active);
    $("cycles").textContent = fmt(s.cycles_run);
    $("orders").textContent = fmt(s.open_order_count);
    $("positions").textContent = fmt(s.position_count);

    var p = s.portfolio || {};
    $("equity").textContent = fmt(p.equity);
    $("cash").textContent = fmt(p.available_cash);
    $("margin").textContent = fmt(p.used_margin);
    $("exposure").textContent = fmt(p.exposure);
    $("upnl").textContent = fmt(p.unrealized_pnl);
    $("heat").textContent = fmt(p.heat);

    $("recon").textContent = r.reconciliation || "—";
    $("reports").textContent = [r.portfolio, r.cycle, r.risk].filter(Boolean).join("\n\n") || "—";

    $("updated").textContent = "updated " + new Date().toLocaleTimeString();
    if (s.emergency_stopped) { setConn("EMERGENCY STOPPED", "pill-danger"); }
    else if (s.kill_switch_active) { setConn("kill switch", "pill-warn"); }
    else { setConn("live", "pill-ok"); }
  } catch (e) {
    setConn("offline", "pill-danger");
  }
}

async function post(path, confirmMsg) {
  if (confirmMsg && !window.confirm(confirmMsg)) return;
  var msg = $("actionmsg");
  msg.textContent = "working…";
  try {
    var res = await fetch(path, { method: "POST", headers: headers() });
    var body = await res.json().catch(function () { return {}; });
    if (res.status === 401) { msg.textContent = "Unauthorized — check API key."; return; }
    if (!res.ok) { msg.textContent = "Error " + res.status; return; }
    msg.textContent = "OK: " + JSON.stringify(body);
    refresh();
  } catch (e) {
    msg.textContent = "Request failed.";
  }
}

$("btn-cycle").addEventListener("click", function () { post("/cycle/run", null); });
$("btn-stop").addEventListener("click", function () {
  post("/control/emergency-stop", "Emergency stop revokes all signing. Continue?");
});

refresh();
setInterval(refresh, POLL_MS);
