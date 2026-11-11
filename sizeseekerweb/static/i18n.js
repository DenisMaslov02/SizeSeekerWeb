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
    searchTitle: "Alles durchsuchen",
    searchPlaceholder: "Datei- oder Ordnername … z. B. urlaub mp4 oder *.pdf",
    searchLabel: "Alle indexierten Ordner und Dateien durchsuchen",
    searchHint: "Mehrere Wörter: alle müssen im Namen vorkommen. Platzhalter: * = beliebig viele Zeichen, ? = genau ein Zeichen.",
    kindAll: "Alles",
    kindDir: "Nur Ordner",
    kindFile: "Nur Dateien",
    indexNone: "Noch kein Index. Einmal alle lokalen Platten ({roots}) durchgehen, danach findest du jede Datei und jeden Ordner sofort.",
    indexInfo: "Index: {entries} Einträge auf {roots} · Stand: {time}",
    indexStart: "Alles indexieren",
    indexAgain: "Neu indexieren",
    indexRunning: "Indexiere {roots} … {entries} Einträge, {dirs} Ordner · {elapsed}",
    indexCancelled: "Indexierung abgebrochen. Der bisherige Index bleibt erhalten.",
    indexFailed: "Indexierung fehlgeschlagen: {message}",
    indexErrors: "{count} Ordner ohne Leserechte wurden übersprungen.",
    results: "{count} Treffer",
    resultsMore: "Mehr als {count} Treffer – gib mehr vom Namen ein, um sie einzugrenzen.",
    resultsNone: "Nichts gefunden.",
    openInApp: "In SizeSeekerWeb öffnen",
    searchFirst: "Erst indexieren, dann suchen.",
    scanAll: "Alle scannen",
    scanOnStart: "Beim Programmstart automatisch scannen",
    scanAllHint: "Scannt {drives} vorab, damit sich Ordner danach sofort öffnen.",
    scanAllRunning: "Scanne {drive} ({pos} von {total}) … {dirs} Ordner, {size} · {elapsed}",
    scanAllDone: "Alle Laufwerke gescannt ({drives}) – Ordner öffnen sich jetzt sofort.",
    scanAllCancelled: "Scan aller Laufwerke abgebrochen.",
    scanAllFailed: "Nicht scannbar: {drives}",
    scannedBadge: "✓ gescannt",
    settingSaved: "Gespeichert.",
    dupAnalyzing: "Suche nach Duplikaten … {percent}",
    dupFound: "{wasted} doppelt belegt in {groups} Gruppen.",
    dupNone: "Keine Duplikate ab {min} gefunden.",
    dupShow: "Duplikate ansehen",
    dupTitle: "Duplikate",
    dupIntro: "Ordner mit gleichem Inhalt und Dateien mit gleichem Namen und gleicher Größe (ab {min}, ohne Papierkorb). Erkannt nur anhand des Index, ohne Dateien zu lesen – mit „Inhalt prüfen“ wird es sicher.",
    dupNoIndex: "Duplikate werden nach dem Indexieren automatisch gesucht.",
    dupFilter: "Nach Name oder Pfad filtern …",
    dupKindAll: "Ordner und Dateien",
    dupKindDir: "Nur Ordner",
    dupKindFile: "Nur Dateien",
    dupGroupDir: "Ordner · {entries} Einträge · je {size}",
    dupGroupFile: "Datei · je {size}",
    dupWasted: "{wasted} doppelt",
    dupCopies: "{count} Kopien",
    dupVerify: "Inhalt prüfen",
    dupVerifying: "Prüfe Inhalt … {done} von {total}",
    dupTruncated: "Es werden die {count} Gruppen mit dem meisten doppelten Platz gezeigt.",
    dupMore: "Weitere anzeigen",
    dupMatching: "{count} Gruppen",
    dupNoMatch: "Keine Gruppe passt zum Filter.",
    verIdentical: "Inhalt geprüft: identisch",
    verPartial: "Inhalt geprüft: nur teilweise identisch",
    verDifferent: "Inhalt geprüft: unterschiedlich – keine echten Duplikate",
    verMissing: "Nicht mehr vorhanden",
    verSame: "gleich wie oben",
    verOther: "abweichend",
    verGone: "fehlt",
    verLocked: "nicht lesbar",
    verUnreadable: "Nicht lesbar – von Windows gesperrt oder keine Berechtigung, Vergleich nicht möglich",
    verHardlink: "Hardlink – belegt keinen zusätzlichen Platz",
    verFailed: "Prüfung fehlgeschlagen: {message}",
    verCancelled: "Prüfung abgebrochen.",
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
    searchTitle: "Search everything",
    searchPlaceholder: "File or folder name … e.g. holiday mp4 or *.pdf",
    searchLabel: "Search all indexed folders and files",
    searchHint: "Several words: all must appear in the name. Wildcards: * = any characters, ? = exactly one character.",
    kindAll: "Everything",
    kindDir: "Folders only",
    kindFile: "Files only",
    indexNone: "No index yet. Go through all local disks ({roots}) once, then every file and folder is found instantly.",
    indexInfo: "Index: {entries} entries on {roots} · Built: {time}",
    indexStart: "Index everything",
    indexAgain: "Re-index",
    indexRunning: "Indexing {roots} … {entries} entries, {dirs} folders · {elapsed}",
    indexCancelled: "Indexing cancelled. The previous index is kept.",
    indexFailed: "Indexing failed: {message}",
    indexErrors: "{count} folders without read permission were skipped.",
    results: "{count} results",
    resultsMore: "More than {count} results – type more of the name to narrow them down.",
    resultsNone: "Nothing found.",
    openInApp: "Open in SizeSeekerWeb",
    searchFirst: "Index first, then search.",
    scanAll: "Scan all",
    scanOnStart: "Scan automatically when the app starts",
    scanAllHint: "Scans {drives} in advance so folders open instantly afterwards.",
    scanAllRunning: "Scanning {drive} ({pos} of {total}) … {dirs} folders, {size} · {elapsed}",
    scanAllDone: "All drives scanned ({drives}) – folders now open instantly.",
    scanAllCancelled: "Scanning all drives cancelled.",
    scanAllFailed: "Could not scan: {drives}",
    scannedBadge: "✓ scanned",
    settingSaved: "Saved.",
    dupAnalyzing: "Looking for duplicates … {percent}",
    dupFound: "{wasted} used twice in {groups} groups.",
    dupNone: "No duplicates of {min} or more found.",
    dupShow: "Show duplicates",
    dupTitle: "Duplicates",
    dupIntro: "Folders with the same contents and files with the same name and size ({min} and up, recycle bin excluded). Found from the index without reading files – \"Check contents\" makes sure.",
    dupNoIndex: "Duplicates are looked for automatically after indexing.",
    dupFilter: "Filter by name or path …",
    dupKindAll: "Folders and files",
    dupKindDir: "Folders only",
    dupKindFile: "Files only",
    dupGroupDir: "Folder · {entries} entries · {size} each",
    dupGroupFile: "File · {size} each",
    dupWasted: "{wasted} duplicated",
    dupCopies: "{count} copies",
    dupVerify: "Check contents",
    dupVerifying: "Checking contents … {done} of {total}",
    dupTruncated: "Showing the {count} groups that waste the most space.",
    dupMore: "Show more",
    dupMatching: "{count} groups",
    dupNoMatch: "No group matches the filter.",
    verIdentical: "Contents checked: identical",
    verPartial: "Contents checked: only partly identical",
    verDifferent: "Contents checked: different – not real duplicates",
    verMissing: "No longer there",
    verSame: "same as above",
    verOther: "different",
    verGone: "missing",
    verLocked: "not readable",
    verUnreadable: "Not readable – locked by Windows or no permission, cannot compare",
    verHardlink: "Hard link – takes no extra space",
    verFailed: "Check failed: {message}",
    verCancelled: "Check cancelled.",
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
