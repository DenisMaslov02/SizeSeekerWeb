const STRINGS = {
  de: {
    drives: "Laufwerke",
    drivesIntro: "Wähle ein Laufwerk, um zu sehen, was Platz belegt.",
    noDrives: "Keine Laufwerke gefunden.",
    free: "{free} frei von {total}",
    used: "{percent} belegt",
    up: "Nach oben",
    rescan: "Neu scannen",
    openExplorer: "Im Explorer zeigen",
    scanning: "Scanne {path}",
    scanningOther: "Es läuft bereits ein Scan von {path}. Danach geht es hier weiter.",
    scanDirs: "Ordner",
    scanFiles: "Dateien",
    scanBytes: "Größe",
    scanElapsed: "Dauer",
    cancel: "Abbrechen",
    cancelled: "Scan abgebrochen.",
    scanAgain: "Erneut scannen",
    backToDrives: "Zur Laufwerksübersicht",
    scanFailed: "Scan fehlgeschlagen: {message}",
    summary: "{size} · {files} Dateien · {dirs} Ordner",
    scannedAt: "Stand: {time}",
    unreadable: "{count} Ordner konnten nicht gelesen werden (fehlende Berechtigung). Ihre Größe fehlt in der Summe.",
    tabContents: "Inhalt",
    tabLargest: "Größte Dateien",
    filter: "Filtern …",
    filterLabel: "Einträge nach Namen filtern",
    sort: "Sortierung",
    sortSizeDesc: "Größe (absteigend)",
    sortSizeAsc: "Größe (aufsteigend)",
    sortNameAsc: "Name (A–Z)",
    sortNameDesc: "Name (Z–A)",
    sortKind: "Typ",
    empty: "Dieser Ordner ist leer.",
    noMatch: "Kein Eintrag passt zum Filter.",
    notScanned: "nicht gescannt",
    link: "Verknüpfung",
    largestIntro: "Die größten Dateien in diesem Ordner und allen Unterordnern (ab 1 MB).",
    largestNone: "Keine Dateien ab 1 MB gefunden.",
    folder: "Ordner",
    name: "Name",
    size: "Größe",
    share: "Anteil",
    treemap: "Treemap: Platzverteilung im Ordner",
    others: "Weitere ({count})",
    loading: "Lädt …",
    accessDenied: "Kein Zugriff auf diesen Ordner.",
    notFound: "Ordner nicht gefunden.",
    error: "Fehler: {message}",
    revealed: "Im Explorer geöffnet.",
    serverDown: "Keine Verbindung zu SizeSeekerWeb. Läuft die App noch?",
    entries: "{count} Einträge",
  },
  en: {
    drives: "Drives",
    drivesIntro: "Pick a drive to see what takes up space.",
    noDrives: "No drives found.",
    free: "{free} free of {total}",
    used: "{percent} used",
    up: "Up",
    rescan: "Rescan",
    openExplorer: "Show in Explorer",
    scanning: "Scanning {path}",
    scanningOther: "A scan of {path} is already running. This folder follows afterwards.",
    scanDirs: "Folders",
    scanFiles: "Files",
    scanBytes: "Size",
    scanElapsed: "Elapsed",
    cancel: "Cancel",
    cancelled: "Scan cancelled.",
    scanAgain: "Scan again",
    backToDrives: "Back to drives",
    scanFailed: "Scan failed: {message}",
    summary: "{size} · {files} files · {dirs} folders",
    scannedAt: "Scanned: {time}",
    unreadable: "{count} folders could not be read (missing permission). Their size is not included.",
    tabContents: "Contents",
    tabLargest: "Largest files",
    filter: "Filter …",
    filterLabel: "Filter entries by name",
    sort: "Sort",
    sortSizeDesc: "Size (largest first)",
    sortSizeAsc: "Size (smallest first)",
    sortNameAsc: "Name (A–Z)",
    sortNameDesc: "Name (Z–A)",
    sortKind: "Type",
    empty: "This folder is empty.",
    noMatch: "No entry matches the filter.",
    notScanned: "not scanned",
    link: "Link",
    largestIntro: "The largest files in this folder and all subfolders (1 MB and up).",
    largestNone: "No files of 1 MB or more found.",
    folder: "Folder",
    name: "Name",
    size: "Size",
    share: "Share",
    treemap: "Treemap: how space is split in this folder",
    others: "Others ({count})",
    loading: "Loading …",
    accessDenied: "Access to this folder is denied.",
    notFound: "Folder not found.",
    error: "Error: {message}",
    revealed: "Opened in Explorer.",
    serverDown: "Cannot reach SizeSeekerWeb. Is the app still running?",
    entries: "{count} entries",
  },
};

function load() {
  try {
    const saved = localStorage.getItem("sizeseeker.lang");
    if (saved && STRINGS[saved]) return saved;
  } catch { /* storage unavailable */ }
  return (navigator.language || "de").toLowerCase().startsWith("de") ? "de" : "en";
}

let lang = load();

export function getLang() {
  return lang;
}

export function setLang(next) {
  if (!STRINGS[next]) return;
  lang = next;
  document.documentElement.lang = next;
  try {
    localStorage.setItem("sizeseeker.lang", next);
  } catch { /* storage unavailable */ }
}

export function t(key, vars = {}) {
  const text = STRINGS[lang][key] ?? STRINGS.en[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (_, name) => (name in vars ? String(vars[name]) : `{${name}}`));
}

const UNITS = ["B", "KB", "MB", "GB", "TB", "PB"];

export function formatSize(bytes) {
  if (bytes == null) return "–";
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const digits = unit === 0 ? 0 : value < 10 ? 2 : value < 100 ? 1 : 0;
  return `${new Intl.NumberFormat(lang, { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value)} ${UNITS[unit]}`;
}

export function formatNumber(n) {
  return n == null ? "–" : new Intl.NumberFormat(lang).format(n);
}

export function formatPercent(p) {
  if (p == null) return "–";
  return `${new Intl.NumberFormat(lang, { maximumFractionDigits: p < 10 ? 1 : 0 }).format(p)} %`;
}

export function formatTime(epochSeconds) {
  return new Intl.DateTimeFormat(lang, { dateStyle: "short", timeStyle: "short" }).format(new Date(epochSeconds * 1000));
}

export function formatDuration(seconds) {
  const s = Math.max(0, Math.round(seconds));
  const m = Math.floor(s / 60);
  return m ? `${m}:${String(s % 60).padStart(2, "0")} min` : `${s} s`;
}

setLang(lang);
