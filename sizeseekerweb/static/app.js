import { formatDuration, formatNumber, formatPercent, formatSize, formatTime, getLang, setLang, t } from "./i18n.js";
import { squarify } from "./treemap.js";

const view = document.getElementById("view");
const crumbs = document.getElementById("crumbs");
const toast = document.getElementById("toast");

const TREEMAP_MAX = 120;
const POLL_MS = 400;

// UI state that survives navigation between folders.
const ui = { filter: "", sort: "size-desc", tab: "contents" };
let renderToken = 0;

// ------------------------------------------------------------------ helpers
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value == null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key === "style") for (const [prop, v] of Object.entries(value)) node.style.setProperty(prop, v);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

const ICONS = {
  drive: '<path d="M3 13h18v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/><path d="M5 13 7.5 5h9L19 13"/><circle cx="17" cy="16.5" r="1"/>',
  dir: '<path d="M3 6a1 1 0 0 1 1-1h5l2 2h9a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/>',
  file: '<path d="M6 3h8l4 4v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M14 3v4h4"/>',
  image: '<rect x="3" y="4" width="18" height="16" rx="1"/><circle cx="9" cy="10" r="2"/><path d="m21 17-5-5-9 8"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  other: '<circle cx="12" cy="12" r="8"/><path d="M12 8v5M12 16h.01"/>',
  up: '<path d="M12 19V5M5 12l7-7 7 7"/>',
  reveal: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 5v6h-6"/>',
};

function icon(name, cls = "icon") {
  const span = el("span", { class: cls, "aria-hidden": "true" });
  span.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ICONS.other}</svg>`;
  return span;
}

/** Same thresholds as the original SizeSeeker: <=10 % green, >10 % blue, >=80 % red. */
function levelClass(percent) {
  if (percent == null) return "level-none";
  if (percent >= 80) return "level-high";
  if (percent > 10) return "level-mid";
  return "level-low";
}

function bar(percent, label, neutral = false) {
  const width = percent == null ? 0 : Math.max(percent, percent > 0 ? 0.6 : 0);
  return el(
    "span",
    { class: `bar ${neutral ? "level-neutral" : levelClass(percent)}`, role: "img", "aria-label": label ?? formatPercent(percent) },
    el("span", { class: "bar-fill", style: { width: `${Math.min(width, 100)}%` } }),
  );
}

class ApiError extends Error {
  constructor(message, status, code) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function api(method, url, body) {
  const options = { method, headers: {} };
  if (method !== "GET") {
    options.headers["X-SizeSeeker"] = "1";
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
  }
  let response;
  try {
    response = await fetch(url, options);
  } catch {
    throw new ApiError(t("serverDown"), 0, "offline");
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    throw new ApiError(detail?.message || response.statusText, response.status, detail?.code);
  }
  return data;
}

function showToast(message, isError = false) {
  toast.textContent = message;
  toast.className = isError ? "toast error" : "toast";
  toast.hidden = false;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => (toast.hidden = true), 3500);
}

async function reveal(path) {
  try {
    await api("POST", "/api/reveal", { path });
    showToast(t("revealed"));
  } catch (err) {
    showToast(t("error", { message: err.message }), true);
  }
}

function folderHref(path) {
  return `#/folder/${encodeURIComponent(path)}`;
}

function isInside(path, root) {
  const p = path.toLowerCase();
  const r = root.toLowerCase().replace(/[\\/]+$/, "");
  return p === r || p === `${r}\\` || p.startsWith(`${r}\\`) || p.startsWith(`${r}/`);
}

function setView(...children) {
  view.replaceChildren(...children.filter((child) => child != null && child !== false));
}

function message(text, ...actions) {
  return el("section", { class: "panel message" }, el("p", {}, text), actions.length ? el("div", { class: "actions" }, actions) : null);
}

// ------------------------------------------------------------------ breadcrumbs
function renderCrumbs(path) {
  const items = [el("a", { href: "#/" }, t("drives"))];
  if (path) {
    const parts = path.split("\\").filter(Boolean);
    let acc = "";
    parts.forEach((part, index) => {
      acc = index === 0 ? `${part}\\` : `${acc}${index > 1 ? "\\" : ""}${part}`;
      items.push(el("span", { class: "sep", "aria-hidden": "true" }, "›"));
      const last = index === parts.length - 1;
      items.push(last ? el("span", { "aria-current": "page" }, part) : el("a", { href: folderHref(acc) }, part));
    });
  }
  crumbs.replaceChildren(...items);
}

// ------------------------------------------------------------------ drives
async function renderDrives(token) {
  renderCrumbs(null);
  document.title = "SizeSeekerWeb";
  setView(el("p", { class: "loading" }, t("loading")));
  let drives;
  try {
    drives = await api("GET", "/api/drives");
  } catch (err) {
    if (token === renderToken) setView(message(t("error", { message: err.message })));
    return;
  }
  if (token !== renderToken) return;
  const cards = drives.map((d) => {
    const percent = d.total ? (d.used * 100) / d.total : 0;
    return el(
      "li",
      {},
      el(
        "a",
        { class: "drive", href: folderHref(d.path) },
        icon("drive", "icon drive-icon"),
        el("span", { class: "drive-name" }, d.path.replace(/\\$/, ""), d.label ? el("small", {}, d.label) : null),
        bar(percent, t("used", { percent: formatPercent(percent) })),
        el("span", { class: "drive-meta" }, t("free", { free: formatSize(d.free), total: formatSize(d.total) }), el("span", {}, t("used", { percent: formatPercent(percent) }))),
      ),
    );
  });
  setView(
    el("h1", {}, t("drives")),
    el("p", { class: "intro" }, t("drivesIntro")),
    drives.length ? el("ul", { class: "drives" }, cards) : message(t("noDrives")),
  );
}

// ------------------------------------------------------------------ scanning
async function startScan(path, token) {
  try {
    await api("POST", "/api/scans", { path });
  } catch (err) {
    if (err.code !== "scan_running") throw err;
  }
  return watchScan(path, token);
}

/** Shows the progress of the running scan; resolves with its final status. */
async function watchScan(path, token) {
  const stats = {
    dirs: el("strong", {}, "0"),
    files: el("strong", {}, "0"),
    bytes: el("strong", {}, "0 B"),
    elapsed: el("strong", {}, "0 s"),
  };
  const heading = el("h1", {}, t("scanning", { path }));
  const note = el("p", { class: "intro" });
  const current = el("p", { class: "current", title: "" });
  const cancel = el("button", { class: "btn", type: "button", onclick: () => api("DELETE", "/api/scans/current").catch(() => {}) }, t("cancel"));
  setView(
    el(
      "section",
      { class: "panel scan", "aria-busy": "true" },
      heading,
      note,
      el("div", { class: "spinner", "aria-hidden": "true" }),
      el(
        "dl",
        { class: "stats" },
        el("div", {}, el("dt", {}, t("scanDirs")), el("dd", {}, stats.dirs)),
        el("div", {}, el("dt", {}, t("scanFiles")), el("dd", {}, stats.files)),
        el("div", {}, el("dt", {}, t("scanBytes")), el("dd", {}, stats.bytes)),
        el("div", {}, el("dt", {}, t("scanElapsed")), el("dd", {}, stats.elapsed)),
      ),
      current,
      el("div", { class: "actions" }, cancel),
    ),
  );

  for (;;) {
    const status = await api("GET", "/api/scans/current");
    if (token !== renderToken) return null;
    if (!status) return null;
    const p = status.progress;
    heading.textContent = t("scanning", { path: status.root });
    note.textContent = isInside(path, status.root) ? "" : t("scanningOther", { path: status.root });
    stats.dirs.textContent = formatNumber(p.dirs);
    stats.files.textContent = formatNumber(p.files);
    stats.bytes.textContent = formatSize(p.bytes);
    stats.elapsed.textContent = formatDuration((status.finished_at ?? Date.now() / 1000) - (status.started_at ?? Date.now() / 1000));
    current.textContent = p.current;
    current.title = p.current;
    if (!["pending", "running"].includes(status.state)) return status;
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
  }
}

// ------------------------------------------------------------------ folder
async function renderFolder(path, token, { forceScan = false } = {}) {
  renderCrumbs(path);
  document.title = `${path} – SizeSeekerWeb`;
  setView(el("p", { class: "loading" }, t("loading")));
  try {
    let data = forceScan ? null : await api("GET", `/api/folder?path=${encodeURIComponent(path)}`);
    if (token !== renderToken) return;
    if (!data || !data.scanned) {
      const running = await api("GET", "/api/scans/current");
      if (token !== renderToken) return;
      const status = running && ["pending", "running"].includes(running.state)
        ? await watchScan(path, token)
        : await startScan(path, token);
      if (token !== renderToken || !status) return;
      if (status.state === "cancelled") {
        setView(message(t("cancelled"), scanAgainButton(path), el("a", { class: "btn", href: "#/" }, t("backToDrives"))));
        return;
      }
      if (status.state === "error") {
        setView(message(t("scanFailed", { message: status.error }), scanAgainButton(path)));
        return;
      }
      if (!isInside(path, status.root)) {
        // Another folder's scan finished first - now scan this one.
        renderFolder(path, token);
        return;
      }
      data = await api("GET", `/api/folder?path=${encodeURIComponent(path)}`);
      if (token !== renderToken) return;
    }
    showFolder(data, token);
  } catch (err) {
    if (token !== renderToken) return;
    const text = err.code === "access_denied" ? t("accessDenied") : err.code === "not_found" ? t("notFound") : t("error", { message: err.message });
    setView(message(text, el("a", { class: "btn", href: "#/" }, t("backToDrives"))));
  }
}

function scanAgainButton(path) {
  return el("button", { class: "btn primary", type: "button", onclick: () => renderFolder(path, ++renderToken, { forceScan: true }) }, t("scanAgain"));
}

function showFolder(data, token) {
  const upHref = data.parent ? folderHref(data.parent) : "#/";
  const header = el(
    "section",
    { class: "folder-head" },
    el("a", { class: "btn icon-btn", href: upHref, title: t("up"), "aria-label": t("up") }, icon("up")),
    el(
      "div",
      { class: "folder-title" },
      el("h1", {}, data.name),
      el(
        "p",
        { class: "meta" },
        t("summary", { size: formatSize(data.size), files: formatNumber(data.files), dirs: formatNumber(data.dirs) }),
        data.scan ? el("span", {}, ` · ${t("scannedAt", { time: formatTime(data.scan.finished_at) })}`) : null,
      ),
    ),
    el(
      "div",
      { class: "actions" },
      el("button", { class: "btn", type: "button", onclick: () => reveal(data.path) }, icon("reveal"), t("openExplorer")),
      el("button", { class: "btn primary", type: "button", onclick: () => renderFolder(data.path, ++renderToken, { forceScan: true }) }, icon("refresh"), t("rescan")),
    ),
  );
  const warning = data.errors ? el("p", { class: "warning", role: "note" }, t("unreadable", { count: formatNumber(data.errors) })) : null;

  const treemapBox = el("div", { class: "treemap", role: "group", "aria-label": t("treemap") });
  const tabContents = el("button", { type: "button", role: "tab", id: "tab-contents" }, t("tabContents"));
  const tabLargest = el("button", { type: "button", role: "tab", id: "tab-largest" }, t("tabLargest"));
  const panel = el("div", { class: "tab-panel", role: "tabpanel" });

  const selectTab = (name) => {
    ui.tab = name;
    tabContents.setAttribute("aria-selected", String(name === "contents"));
    tabLargest.setAttribute("aria-selected", String(name === "largest"));
    panel.setAttribute("aria-labelledby", name === "contents" ? "tab-contents" : "tab-largest");
    if (name === "contents") renderContents(panel, data);
    else renderLargest(panel, data, token);
  };
  tabContents.addEventListener("click", () => selectTab("contents"));
  tabLargest.addEventListener("click", () => selectTab("largest"));

  setView(header, warning, treemapBox, el("div", { class: "tabs", role: "tablist" }, tabContents, tabLargest), panel);
  drawTreemap(treemapBox, data.entries);
  selectTab(ui.tab);
}

function drawTreemap(box, entries) {
  const items = entries.filter((e) => e.size > 0).sort((a, b) => b.size - a.size);
  const shown = items.slice(0, TREEMAP_MAX);
  const rest = items.slice(TREEMAP_MAX);
  if (rest.length) shown.push({ kind: "rest", name: t("others", { count: rest.length }), size: rest.reduce((s, e) => s + e.size, 0) });
  const total = shown.reduce((s, e) => s + e.size, 0);

  const layout = () => {
    const { width, height } = box.getBoundingClientRect();
    const rects = squarify(shown.map((e) => e.size), 0, 0, width, height);
    box.replaceChildren(
      ...rects.map((r, i) => {
        const entry = shown[i];
        const share = (entry.size * 100) / total;
        const tip = `${entry.name} – ${formatSize(entry.size)} (${formatPercent(share)})`;
        const big = r.w > 70 && r.h > 34;
        const attrs = {
          class: `tile kind-${entry.kind}`,
          title: tip,
          style: { left: `${r.x}px`, top: `${r.y}px`, width: `${r.w}px`, height: `${r.h}px`, "--shade": String(i % 6) },
        };
        const label = big ? [el("span", { class: "tile-name" }, entry.name), el("span", { class: "tile-size" }, formatSize(entry.size))] : [];
        return entry.kind === "dir"
          ? el("a", { ...attrs, href: folderHref(entry.path), "aria-label": tip }, label)
          : el("div", { ...attrs, role: "img", "aria-label": tip }, label);
      }),
    );
  };
  if (!shown.length) {
    box.hidden = true;
    return;
  }
  layout();
  const observer = new ResizeObserver(() => (box.isConnected ? layout() : observer.disconnect()));
  observer.observe(box);
}

const SORTERS = {
  "size-desc": (a, b) => (b.size ?? -1) - (a.size ?? -1) || a.name.localeCompare(b.name),
  "size-asc": (a, b) => (a.size ?? -1) - (b.size ?? -1) || a.name.localeCompare(b.name),
  "name-asc": (a, b) => a.name.localeCompare(b.name, getLang(), { numeric: true }),
  "name-desc": (a, b) => b.name.localeCompare(a.name, getLang(), { numeric: true }),
  kind: (a, b) => a.kind.localeCompare(b.kind) || (b.size ?? -1) - (a.size ?? -1),
};

function renderContents(panel, data) {
  const filter = el("input", { type: "search", class: "input", placeholder: t("filter"), "aria-label": t("filterLabel"), value: ui.filter });
  const sort = el(
    "select",
    { class: "input", "aria-label": t("sort") },
    ["size-desc", "size-asc", "name-asc", "name-desc", "kind"].map((key) =>
      el("option", { value: key, selected: ui.sort === key }, t({ "size-desc": "sortSizeDesc", "size-asc": "sortSizeAsc", "name-asc": "sortNameAsc", "name-desc": "sortNameDesc", kind: "sortKind" }[key])),
    ),
  );
  const count = el("span", { class: "count" });
  const list = el("ul", { class: "entries" });

  const update = () => {
    const needle = ui.filter.trim().toLowerCase();
    const rows = data.entries.filter((e) => !needle || e.name.toLowerCase().includes(needle)).sort(SORTERS[ui.sort]);
    count.textContent = t("entries", { count: formatNumber(rows.length) });
    if (!data.entries.length) list.replaceChildren(el("li", { class: "empty" }, t("empty")));
    else if (!rows.length) list.replaceChildren(el("li", { class: "empty" }, t("noMatch")));
    else list.replaceChildren(...rows.map(entryRow));
  };
  filter.addEventListener("input", () => {
    ui.filter = filter.value;
    update();
  });
  sort.addEventListener("change", () => {
    ui.sort = sort.value;
    update();
  });
  panel.replaceChildren(el("div", { class: "toolbar" }, filter, sort, count), list);
  update();
}

function entryRow(entry) {
  const sizeText = entry.kind === "link" ? t("link") : entry.size == null ? t("notScanned") : formatSize(entry.size);
  const main = [
    icon(entry.kind, `icon kind-${entry.kind}`),
    el("span", { class: "entry-name", title: entry.name }, entry.name),
    el("span", { class: "entry-share" }, bar(entry.percent), el("span", { class: "pct" }, formatPercent(entry.percent))),
    el("span", { class: "entry-size" }, sizeText),
  ];
  return el(
    "li",
    { class: "entry" },
    entry.kind === "dir" ? el("a", { class: "entry-main", href: folderHref(entry.path) }, main) : el("div", { class: "entry-main" }, main),
    el("button", { class: "btn icon-btn", type: "button", title: t("openExplorer"), "aria-label": `${t("openExplorer")}: ${entry.name}`, onclick: () => reveal(entry.path) }, icon("reveal")),
  );
}

async function renderLargest(panel, data, token) {
  panel.replaceChildren(el("p", { class: "loading" }, t("loading")));
  let files;
  try {
    files = await api("GET", `/api/largest?path=${encodeURIComponent(data.path)}&limit=100`);
  } catch (err) {
    if (token === renderToken) panel.replaceChildren(el("p", { class: "warning" }, t("error", { message: err.message })));
    return;
  }
  if (token !== renderToken || ui.tab !== "largest") return;
  if (!files.length) {
    panel.replaceChildren(el("p", { class: "intro" }, t("largestIntro")), el("p", { class: "empty" }, t("largestNone")));
    return;
  }
  const base = data.path.replace(/\\$/, "");
  const largest = files[0].size;
  panel.replaceChildren(
    el("p", { class: "intro" }, t("largestIntro")),
    el(
      "table",
      { class: "largest" },
      el("thead", {}, el("tr", {}, el("th", { scope: "col" }, t("name")), el("th", { scope: "col" }, t("folder")), el("th", { scope: "col", class: "num" }, t("size")), el("th", { scope: "col" }, el("span", { class: "sr-only" }, t("openExplorer"))))),
      el(
        "tbody",
        {},
        files.map((f) => {
          const dir = f.path.slice(0, f.path.length - f.name.length).replace(/\\$/, "");
          const rel = dir.length > base.length ? `…${dir.slice(base.length)}` : "";
          return el(
            "tr",
            {},
            el("td", { class: "file-cell" }, icon(f.kind, `icon kind-${f.kind}`), el("span", { title: f.path }, f.name)),
            el("td", { class: "dir-cell", title: dir }, dir.length > base.length ? el("a", { href: folderHref(dir) }, rel) : "."),
            el("td", { class: "num" }, el("span", { class: "size-with-bar" }, bar((f.size * 100) / largest, formatSize(f.size), true), formatSize(f.size))),
            el("td", {}, el("button", { class: "btn icon-btn", type: "button", title: t("openExplorer"), "aria-label": `${t("openExplorer")}: ${f.name}`, onclick: () => reveal(f.path) }, icon("reveal"))),
          );
        }),
      ),
    ),
  );
}

// ------------------------------------------------------------------ router
function route() {
  const token = ++renderToken;
  const hash = location.hash || "#/";
  const match = hash.match(/^#\/folder\/(.+)$/);
  if (match) {
    let path;
    try {
      path = decodeURIComponent(match[1]);
    } catch {
      location.hash = "#/";
      return;
    }
    renderFolder(path, token);
  } else {
    renderDrives(token);
  }
  view.focus({ preventScroll: true });
}

function initLanguage() {
  const buttons = document.querySelectorAll("[data-lang]");
  const sync = () => buttons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === getLang())));
  buttons.forEach((b) =>
    b.addEventListener("click", () => {
      if (b.dataset.lang === getLang()) return;
      setLang(b.dataset.lang);
      sync();
      route();
    }),
  );
  sync();
}

initLanguage();
window.addEventListener("hashchange", route);
route();
