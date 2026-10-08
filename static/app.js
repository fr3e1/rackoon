"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const state = { servers: [], scripts: [], stats: {}, filter: "" };
const ADHOC = "__adhoc__";

// --- helpers ------------------------------------------------------------------

async function api(path, opts = {}) {
  const init = { ...opts, headers: { ...(opts.headers || {}) } };
  if (opts.json !== undefined) {
    init.body = JSON.stringify(opts.json);
    init.headers["Content-Type"] = "application/json";
  }
  const res = await fetch(path, init);
  if (res.status === 401 && !path.startsWith("/api/auth/")) {
    showLogin();
    throw new Error("Not logged in");
  }
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : await res.text();
  if (!res.ok) throw new Error(data?.detail || res.statusText);
  return data;
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) node.setAttribute(k, v);
  }
  for (const c of children.flat()) if (c != null) node.append(c);
  return node;
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), 3000);
}

function confirmBox(text) {
  const dlg = $("#confirm-dialog");
  $("#confirm-text").textContent = text;
  dlg.showModal();
  return new Promise((resolve) => {
    dlg.onclick = (e) => {
      const answer = e.target.dataset.answer;
      if (!answer) return;
      dlg.close();
      resolve(answer === "yes");
    };
  });
}

const fmtBytes = (n) => {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${units[i]}`;
};
const fmtUptime = (s) => {
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  return d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m`;
};
const fmtTime = (ts) => new Date(ts * 1000).toLocaleString();

// --- theme ----------------------------------------------------------------------

const themePicker = $("#theme-picker");
themePicker.value = document.documentElement.dataset.theme || "";
themePicker.addEventListener("change", () => {
  const theme = themePicker.value;
  if (theme) document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
  try { theme ? localStorage.setItem("rackoon-theme", theme) : localStorage.removeItem("rackoon-theme"); } catch {}
});

$$("dialog [data-close]").forEach((b) => b.addEventListener("click", () => b.closest("dialog").close()));

// --- auth ---------------------------------------------------------------------

let setupMode = false;

async function boot() {
  const s = await api("/api/auth/state");
  if (s.logged_in) return showApp();
  setupMode = s.setup_required;
  showLogin();
}

function showLogin() {
  $("#app-view").hidden = true;
  $("#login-view").hidden = false;
  $("#login-confirm").hidden = !setupMode;
  $("#login-confirm").required = setupMode;
  $("#login-btn").textContent = setupMode ? "Set password" : "Log in";
  $("#login-hint").textContent = setupMode ? "First run: choose a password to guard the rack." : "";
  $("#login-password").focus();
}

$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const password = $("#login-password").value;
  $("#login-error").textContent = "";
  try {
    if (setupMode) {
      if (password !== $("#login-confirm").value) throw new Error("Passwords don't match");
      await api("/api/auth/setup", { method: "POST", json: { password } });
    } else {
      await api("/api/auth/login", { method: "POST", json: { password } });
    }
    $("#login-form").reset();
    showApp();
  } catch (err) {
    $("#login-error").textContent = err.message;
  }
});

async function showApp() {
  $("#login-view").hidden = true;
  $("#app-view").hidden = false;
  await Promise.all([loadServers(), loadScripts()]);
  switchTab(location.hash.slice(1) || "servers");
}

// --- tabs ---------------------------------------------------------------------

function switchTab(name) {
  if (!$(`#tab-${name}`)) name = "servers";
  $$("nav button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab").forEach((t) => (t.hidden = t.id !== `tab-${name}`));
  history.replaceState(null, "", `#${name}`);
  if (name === "history") loadHistory();
  if (name === "settings") loadSettings();
  if (name === "run") renderRunForm();
}
$$("nav button").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));

// --- servers ------------------------------------------------------------------

async function loadServers() {
  state.servers = await api("/api/servers");
  renderServers();
}

function renderServers() {
  const list = $("#server-list");
  list.replaceChildren();
  if (!state.servers.length) {
    list.append(el("p", { class: "muted" }, "No servers yet. Add one to get started."));
    return;
  }
  const visible = state.servers.filter(matchesFilter);
  for (const s of visible) list.append(serverCard(s));
  if (!visible.length) list.append(el("p", { class: "muted" }, "No servers match the filter."));
}

function matchesFilter(s) {
  const q = state.filter.trim().toLowerCase();
  if (!q) return true;
  return [s.name, s.host, s.username, ...(s.tags || [])].some((v) => v && v.toLowerCase().includes(q));
}

$("#server-filter").addEventListener("input", (e) => {
  state.filter = e.target.value;
  renderServers();
});

function serverCard(s) {
  const online = s.status?.online;
  const dotClass = s.status ? (online ? "dot on" : "dot off") : "dot";
  const title = s.status ? `${online ? "Online" : "Offline"} · checked ${fmtTime(s.status.checked)}` : "Not checked yet";
  return el("div", { class: "card server" },
    el("div", { class: "server-head" },
      el("span", { class: dotClass, title }),
      el("strong", {}, s.name)),
    el("div", { class: "muted" }, `${s.username ? s.username + "@" : ""}${s.host}:${s.port}`),
    (s.tags || []).length ? el("div", { class: "tags" }, s.tags.map((t) => el("span", {
      class: "tag clickable", title: "Filter by this tag",
      onclick: () => { state.filter = $("#server-filter").value = t; renderServers(); },
    }, t))) : null,
    statsView(s.id),
    el("div", { class: "actions" },
      el("button", { class: "small", onclick: () => loadStats(s.id) }, "Stats"),
      el("button", { class: "small ghost", onclick: () => openDetails(s) }, "Details"),
      s.mac ? el("button", { class: "small ghost", onclick: () => wake(s), title: `Send Wake-on-LAN to ${s.mac}` }, "Wake") : null,
      el("button", { class: "small ghost", onclick: () => { switchTab("run"); selectRunServer(s.id); } }, "Run script"),
      el("button", { class: "small ghost", onclick: () => openServerDialog(s) }, "Edit"),
      el("button", { class: "small ghost danger", onclick: () => deleteServer(s) }, "Delete")),
  );
}

function statsView(id) {
  const st = state.stats[id];
  if (!st) return null;
  if (st.loading) return el("div", { class: "muted" }, "Loading stats…");
  if (st.error) return el("div", { class: "error" }, st.error);
  const bar = (label, pct, detail) => {
    const cls = pct > 90 ? "crit" : pct > 75 ? "hot" : "";
    return el("div", {},
      el("div", { class: "stat-row" }, el("span", {}, label), el("span", {}, detail)),
      el("div", { class: "bar" }, el("div", { class: cls, style: `width:${Math.min(100, pct)}%` })));
  };
  const d = st.data;
  const memPct = (100 * d.mem_used) / d.mem_total;
  const diskPct = (100 * d.disk_used) / d.disk_total;
  return el("div", { class: "stats" },
    d.os ? el("div", { class: "muted" }, `${d.hostname} · ${d.os}`) : null,
    bar("CPU", d.cpu, `${d.cpu}% · ${d.cores} cores`),
    bar("Memory", memPct, `${fmtBytes(d.mem_used)} / ${fmtBytes(d.mem_total)}`),
    bar("Disk /", diskPct, `${fmtBytes(d.disk_used)} / ${fmtBytes(d.disk_total)}`),
    el("div", { class: "stat-row" }, el("span", {}, `Up ${fmtUptime(d.uptime)}`), el("span", {}, `Load ${d.load}`)),
  );
}

async function loadStats(id) {
  state.stats[id] = { loading: true };
  renderServers();
  try {
    state.stats[id] = { data: await api(`/api/servers/${id}/stats`) };
  } catch (err) {
    state.stats[id] = { error: err.message };
  }
  renderServers();
}

async function wake(s) {
  try {
    await api(`/api/servers/${s.id}/wake`, { method: "POST" });
    toast(`Wake-on-LAN packet sent to ${s.name}`);
  } catch (err) {
    toast(err.message);
  }
}

let detailsServer = null;

async function openDetails(s) {
  detailsServer = s;
  $("#details-title").textContent = `${s.name} (${s.host})`;
  $("#details-dialog").showModal();
  const body = $("#details-body");
  body.replaceChildren(el("p", { class: "muted" }, "Collecting machine details…"));
  try {
    const sections = await api(`/api/servers/${s.id}/details`);
    if (detailsServer !== s) return; // dialog was reopened for another server
    body.replaceChildren(...sections.map((sec) =>
      el("div", { class: "card" }, el("h3", {}, sec.title), el("pre", {}, sec.body))));
  } catch (err) {
    body.replaceChildren(el("p", { class: "error" }, err.message));
  }
}
$("#details-refresh").addEventListener("click", () => detailsServer && openDetails(detailsServer));

$("#all-stats").addEventListener("click", () => {
  for (const s of state.servers.filter(matchesFilter)) if (s.status?.online !== false) loadStats(s.id);
});

function openServerDialog(server = null) {
  const form = $("#server-form");
  form.reset();
  form.dataset.id = server?.id || "";
  $("#server-dialog-title").textContent = server ? `Edit ${server.name}` : "Add server";
  $("#server-error").textContent = "";
  if (server) {
    for (const k of ["name", "host", "port", "username", "auth", "key_path", "mac"]) form.elements[k].value = server[k] ?? "";
    form.elements.sudo_mode.value = server.sudo_mode || "none";
    form.elements.sudo_password.placeholder = server.has_sudo_password ? "(unchanged)" : "";
    form.elements.tags.value = (server.tags || []).join(", ");
    form.elements.password.placeholder = server.has_password ? "(unchanged)" : "";
    form.elements.key_data.placeholder = server.has_key_data ? "(unchanged)" : "-----BEGIN OPENSSH PRIVATE KEY-----";
  }
  updateAuthFields();
  $("#server-dialog").showModal();
}

function updateAuthFields() {
  const method = $("#server-form").elements.auth.value;
  $$("#server-form [data-auth]").forEach((l) => (l.hidden = !l.dataset.auth.split(" ").includes(method)));
  const sudo = $("#server-form").elements.sudo_mode.value;
  $$("#server-form [data-sudo]").forEach((l) => (l.hidden = l.dataset.sudo !== sudo || (sudo === "ssh" && method === "password")));
}
$("#server-form").elements.auth.addEventListener("change", updateAuthFields);
$("#server-form").elements.sudo_mode.addEventListener("change", updateAuthFields);

$("#server-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const data = Object.fromEntries(new FormData(form));
  data.port = Number(data.port) || 22;
  data.tags = data.tags.split(",").map((t) => t.trim()).filter(Boolean);
  try {
    const id = form.dataset.id;
    await api(id ? `/api/servers/${id}` : "/api/servers", { method: id ? "PUT" : "POST", json: data });
    $("#server-dialog").close();
    await loadServers();
    setTimeout(loadServers, 3500); // pick up the fresh status check
  } catch (err) {
    $("#server-error").textContent = err.message;
  }
});

async function deleteServer(s) {
  if (!(await confirmBox(`Delete server "${s.name}"?`))) return;
  await api(`/api/servers/${s.id}`, { method: "DELETE" });
  delete state.stats[s.id];
  loadServers();
}

$("#add-server").addEventListener("click", () => openServerDialog());
$("#refresh-status").addEventListener("click", async (e) => {
  e.target.disabled = true;
  try {
    await api("/api/status/refresh", { method: "POST" });
    await loadServers();
  } finally {
    e.target.disabled = false;
  }
});
// Keep the status dots current while the page is open.
setInterval(() => { if (!$("#app-view").hidden && !$("#tab-servers").hidden) loadServers().catch(() => {}); }, 15000);

// --- scripts ------------------------------------------------------------------

async function loadScripts() {
  state.scripts = await api("/api/scripts");
  renderScripts();
}

function renderScripts() {
  const list = $("#script-list");
  list.replaceChildren();
  if (!state.scripts.length) {
    list.append(el("p", { class: "muted" }, "No scripts yet. Create one with the button above."));
    return;
  }
  for (const s of state.scripts) {
    list.append(el("div", { class: "card script" },
      el("div", { class: "info" },
        el("strong", {}, s.name),
        s.description ? el("div", { class: "muted" }, s.description) : null,
        el("pre", {}, s.body)),
      el("div", { class: "actions" },
        el("button", { class: "small", onclick: () => { switchTab("run"); $("#run-script").value = s.id; } }, "Run"),
        el("button", { class: "small ghost", onclick: () => openScriptDialog(s) }, "Edit"),
        el("button", { class: "small ghost danger", onclick: () => deleteScript(s) }, "Delete"))));
  }
}

function openScriptDialog(script = null) {
  const form = $("#script-form");
  form.reset();
  form.dataset.id = script?.id || "";
  $("#script-dialog-title").textContent = script ? `Edit ${script.name}` : "New script";
  $("#script-error").textContent = "";
  if (script) for (const k of ["name", "description", "body"]) form.elements[k].value = script[k] ?? "";
  $("#script-dialog").showModal();
}

// Tab inserts two spaces in the script editor instead of leaving the field.
$("#script-form").elements.body.addEventListener("keydown", (e) => {
  if (e.key !== "Tab") return;
  e.preventDefault();
  e.target.setRangeText("  ", e.target.selectionStart, e.target.selectionEnd, "end");
});

$("#script-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const data = Object.fromEntries(new FormData(form));
  try {
    const id = form.dataset.id;
    await api(id ? `/api/scripts/${id}` : "/api/scripts", { method: id ? "PUT" : "POST", json: data });
    $("#script-dialog").close();
    loadScripts();
  } catch (err) {
    $("#script-error").textContent = err.message;
  }
});

async function deleteScript(s) {
  if (!(await confirmBox(`Delete script "${s.name}"?`))) return;
  await api(`/api/scripts/${s.id}`, { method: "DELETE" });
  loadScripts();
}

$("#add-script").addEventListener("click", () => openScriptDialog());

let library = null;

$("#open-library").addEventListener("click", async () => {
  $("#library-dialog").showModal();
  const body = $("#library-body");
  try {
    library ??= await api("/api/library");
  } catch (err) {
    body.replaceChildren(el("p", { class: "error" }, err.message));
    return;
  }
  body.replaceChildren();
  let category = null;
  for (const item of library) {
    if (item.category !== category) body.append(el("h4", {}, (category = item.category)));
    const added = state.scripts.some((s) => s.name === item.name);
    const btn = el("button", { class: "small" + (added ? " ghost" : "") }, added ? "Add again" : "Add");
    btn.addEventListener("click", async () => {
      const { name, description, body: scriptBody } = item;
      await api("/api/scripts", { method: "POST", json: { name, description, body: scriptBody } });
      await loadScripts();
      btn.textContent = "Added ✓";
      btn.className = "small ghost";
    });
    body.append(el("div", { class: "library-item" },
      el("div", { class: "info" }, el("strong", {}, item.name), el("div", { class: "muted" }, item.description)),
      btn));
  }
});

// --- run ----------------------------------------------------------------------

function renderRunForm() {
  const sel = $("#run-script");
  const current = sel.value;
  sel.replaceChildren(
    ...state.scripts.map((s) => el("option", { value: s.id }, s.name)),
    el("option", { value: ADHOC }, "— Ad-hoc command —"));
  if (current) sel.value = current;
  updateRunMode();

  const box = $("#run-servers");
  const checked = new Set($$("input:checked", box).map((i) => i.value));
  box.replaceChildren(...state.servers.map((s) =>
    el("label", {},
      el("input", { type: "checkbox", value: s.id, checked: checked.has(s.id) }),
      el("span", { class: s.status ? (s.status.online ? "dot on" : "dot off") : "dot" }),
      s.name)));
  if (!state.servers.length) box.append(el("span", { class: "muted" }, "Add a server first."));
  renderSudoPrompts();
}

// One password field per selected server whose sudo mode is "ask". The
// values are only sent with the run and cleared afterwards.
function renderSudoPrompts() {
  const box = $("#run-sudo");
  const typed = Object.fromEntries($$("input", box).map((i) => [i.name, i.value]));
  const ask = $$("#run-servers input:checked")
    .map((i) => state.servers.find((s) => s.id === i.value))
    .filter((s) => s?.sudo_mode === "ask");
  box.replaceChildren(
    el("div", { class: "muted" }, "Sudo passwords (used for this run only, never saved)"),
    ...ask.map((s) => el("label", {},
      el("span", {}, s.name),
      el("input", { type: "password", name: s.id, autocomplete: "off", value: typed[s.id] ?? "" }))));
  box.hidden = !ask.length;
}
$("#run-servers").addEventListener("change", renderSudoPrompts);

function updateRunMode() {
  $("#run-command-wrap").hidden = $("#run-script").value !== ADHOC;
}
$("#run-script").addEventListener("change", updateRunMode);

function selectRunServer(id) {
  $$("#run-servers input").forEach((i) => (i.checked = i.value === id));
  renderSudoPrompts();
}

$("#run-select-all").addEventListener("click", () => {
  const boxes = $$("#run-servers input");
  const all = boxes.every((b) => b.checked);
  boxes.forEach((b) => (b.checked = !all));
  renderSudoPrompts();
});

$("#run-btn").addEventListener("click", () => {
  const scriptId = $("#run-script").value;
  const command = scriptId === ADHOC ? $("#run-command").value : "";
  const serverIds = $$("#run-servers input:checked").map((i) => i.value);
  if (scriptId === ADHOC && !command.trim()) return toast("Type a command first");
  if (!serverIds.length) return toast("Select at least one server");
  const sudoInputs = $$("#run-sudo input");
  const sudoPasswords = Object.fromEntries(sudoInputs.filter((i) => i.value).map((i) => [i.name, i.value]));
  sudoInputs.forEach((i) => (i.value = ""));

  const out = $("#run-output");
  out.replaceChildren();
  const panes = {};
  for (const id of serverIds) {
    const server = state.servers.find((s) => s.id === id);
    const badge = el("span", { class: "badge running" }, "connecting");
    const term = el("pre", { class: "terminal" });
    out.append(el("div", { class: "run-pane" }, el("div", { class: "run-pane-head" }, el("strong", {}, server.name), badge), term));
    panes[id] = { badge, term };
  }

  const btn = $("#run-btn");
  const stop = $("#stop-btn");
  btn.disabled = true;
  stop.hidden = false;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/run`);
  ws.onopen = () => ws.send(JSON.stringify({
    script_id: command ? null : scriptId, command, server_ids: serverIds, args: $("#run-args").value,
    sudo_passwords: sudoPasswords,
  }));
  // Closing the socket drops the SSH sessions, which stops the remote scripts.
  stop.onclick = () => {
    ws.close();
    for (const pane of Object.values(panes)) {
      if (pane.badge.classList.contains("running")) {
        pane.badge.className = "badge fail";
        pane.badge.textContent = "stopped";
      }
    }
  };
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    const pane = panes[msg.server_id];
    if (!pane) return msg.message && toast(msg.message);
    const setBadge = (cls, text) => { pane.badge.className = `badge ${cls}`; pane.badge.textContent = text; };
    if (msg.type === "start") setBadge("running", "running");
    if (msg.type === "output") {
      const stick = pane.term.scrollTop + pane.term.clientHeight >= pane.term.scrollHeight - 5;
      pane.term.append(msg.stream === "stderr" ? el("span", { class: "stderr" }, msg.data) : msg.data);
      if (stick) pane.term.scrollTop = pane.term.scrollHeight;
    }
    if (msg.type === "done") setBadge(msg.exit_code === 0 ? "ok" : "fail", `exit ${msg.exit_code}`);
    if (msg.type === "error") {
      setBadge("fail", "error");
      pane.term.append(el("span", { class: "stderr" }, `\n${msg.message}\n`));
    }
  };
  ws.onclose = (e) => {
    btn.disabled = false;
    stop.hidden = true;
    if (e.code === 4401) showLogin();
  };
});

// --- history ------------------------------------------------------------------

async function loadHistory() {
  const runs = await api("/api/history");
  const body = $("#history-body");
  body.replaceChildren();
  if (!runs.length) {
    body.append(el("tr", {}, el("td", { colspan: 5, class: "muted" }, "No runs yet.")));
    return;
  }
  for (const r of runs) {
    const result = r.finished == null ? el("span", { class: "badge running" }, "running")
      : r.exit_code === 0 ? el("span", { class: "badge ok" }, "exit 0")
      : el("span", { class: "badge fail" }, r.exit_code == null ? "error" : `exit ${r.exit_code}`);
    const dur = r.finished ? `${(r.finished - r.started).toFixed(1)}s` : "–";
    body.append(el("tr", { onclick: () => showRun(r.id) },
      el("td", {}, fmtTime(r.started)), el("td", {}, r.script_name),
      el("td", {}, `${r.server_name} (${r.host})`), el("td", {}, dur), el("td", {}, result)));
  }
}

async function showRun(id) {
  const r = await api(`/api/history/${id}`);
  $("#output-title").textContent = `${r.script_name} on ${r.server_name} · ${fmtTime(r.started)}`;
  $("#output-body").textContent = r.output || "(no output)";
  $("#output-dialog").showModal();
}

$("#clear-history").addEventListener("click", async () => {
  if (!(await confirmBox("Delete all run history?"))) return;
  await api("/api/history", { method: "DELETE" });
  loadHistory();
});

// --- settings -----------------------------------------------------------------

async function loadSettings() {
  const s = await api("/api/settings");
  const form = $("#settings-form");
  for (const [k, v] of Object.entries(s)) if (form.elements[k]) form.elements[k].value = v;
}

$("#settings-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  await api("/api/settings", { method: "PUT", json: Object.fromEntries(new FormData(e.target)) });
  toast("Settings saved");
});

$("#password-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/auth/password", { method: "POST", json: Object.fromEntries(new FormData(e.target)) });
    e.target.reset();
    toast("Password changed");
  } catch (err) {
    toast(err.message);
  }
});

for (const mode of ["replace", "merge"]) {
  $(`#import-${mode}`).addEventListener("change", async (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    if (mode === "replace" && !(await confirmBox("Replace all current servers and scripts with this file?"))) return;
    const body = new FormData();
    body.append("file", file);
    try {
      const r = await api(`/api/config/import?mode=${mode}`, { method: "POST", body });
      toast(`Imported: ${r.servers} servers, ${r.scripts} scripts`);
      state.stats = {};
      await Promise.all([loadServers(), loadScripts()]);
    } catch (err) {
      toast(err.message);
    }
  });
}

$("#logout").addEventListener("click", async () => {
  await api("/api/auth/logout", { method: "POST" });
  setupMode = false;
  showLogin();
});

boot();
