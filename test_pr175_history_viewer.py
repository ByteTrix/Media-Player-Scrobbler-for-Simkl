"""Behavioural tests for the local watch-history viewer's "hide from this view" feature.

The viewer is static HTML/JS, so these tests drive the real ``script.js`` with Node:
the pure helpers are loaded through ``module.exports`` and the page itself runs
against a small fake DOM so the actual load -> hide -> restore flow is exercised.
Nothing here touches watch_history.json, the network or a real browser profile.
"""
import json
import pathlib
import shutil
import subprocess
import textwrap

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent
SCRIPT_PATH = REPO_ROOT / "simkl_mps" / "watch-history-viewer" / "script.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is required to run the viewer script")

# Shared JS prelude: in-memory storage implementations and sample history data
# shaped like WatchHistoryManager output (Python isoformat timestamps).
JS_PRELUDE = textwrap.dedent(r"""
    const path = require('path');
    const fs = require('fs');
    const vm = require('vm');
    const SCRIPT_PATH = process.argv[2];

    function memoryStorage(initial = {}) {
        const data = new Map(Object.entries(initial));
        return {
            data,
            getItem: key => (data.has(key) ? data.get(key) : null),
            setItem: (key, value) => { data.set(key, String(value)); },
            removeItem: key => { data.delete(key); }
        };
    }

    function quotaStorage(initial = {}) {
        const storage = memoryStorage(initial);
        storage.setItem = () => { const e = new Error('QuotaExceededError'); e.name = 'QuotaExceededError'; throw e; };
        return storage;
    }

    function sampleHistory() {
        return [
            {
                simkl_id: 101, title: 'Movie A', type: 'movie', year: 2020,
                watched_at: '2026-10-01T20:00:00.123456', watch_count: 2, rewatch_count: 1,
                watch_events: [
                    { watched_at: '2026-09-01T20:00:00.000001' },
                    { watched_at: '2026-10-01T20:00:00.123456' }
                ]
            },
            {
                simkl_id: 202, title: 'Show B', type: 'show', year: 2019,
                watched_at: '2026-10-02T21:00:00.500000', watch_count: 3, rewatch_count: 1,
                season: 1, episode: 2, episodes_watched: 2,
                episodes: [
                    { season: 1, number: 1, watched_at: '2026-10-02T21:00:00.500000', watch_count: 2, rewatch_count: 1,
                      watch_events: [{ watched_at: '2026-09-30T21:00:00' }, { watched_at: '2026-10-02T21:00:00.500000' }] },
                    { season: 1, number: 2, watched_at: '2026-10-01T22:00:00', watch_count: 1, rewatch_count: 0,
                      watch_events: [{ watched_at: '2026-10-01T22:00:00' }] }
                ]
            },
            {
                simkl_id: 101, title: 'Same id, other type', type: 'anime', year: 2021,
                watched_at: '2026-10-03T10:00:00'
            }
        ];
    }

    function emit(value) { process.stdout.write(JSON.stringify(value)); }
""")

CORE_SCENARIOS = textwrap.dedent(r"""
    const core = require(path.resolve(SCRIPT_PATH));
    const scenario = process.argv[3];
    const visible = (store, items) => items.filter(i => !store.isHidden(i)).map(i => `${i.type}:${i.title}`);

    if (scenario === 'persist_and_rewatch') {
        const storage = memoryStorage();
        const items = sampleHistory();
        let store = core.createHiddenHistoryStore(core.createSafeStorage(() => storage));
        store.load(items);
        const saved = store.hide(items[0], items);
        const afterHide = visible(store, items);

        // Reopen the viewer with the same data: still hidden.
        store = core.createHiddenHistoryStore(core.createSafeStorage(() => storage));
        store.load(items);
        const afterReload = visible(store, items);
        const listed = store.listHidden(items).map(h => h.key);

        // A later rewatch is appended by the app; the title must come back.
        const rewatched = sampleHistory();
        rewatched[0].watch_events.push({ watched_at: '2026-11-01T09:00:00.000001' });
        rewatched[0].watched_at = '2026-11-01T09:00:00.000001';
        store = core.createHiddenHistoryStore(core.createSafeStorage(() => storage));
        store.load(rewatched);
        emit({
            saved, afterHide, afterReload, listed,
            afterRewatch: visible(store, rewatched),
            storedAfterRewatch: JSON.parse(storage.getItem(core.HIDDEN_STORAGE_KEY)).items,
            inputUntouched: JSON.stringify(items) === JSON.stringify(sampleHistory())
        });
    } else if (scenario === 'new_episode_unhides_show') {
        const storage = memoryStorage();
        const items = sampleHistory();
        let store = core.createHiddenHistoryStore(core.createSafeStorage(() => storage));
        store.load(items);
        store.hide(items[1], items);
        const hiddenNow = visible(store, items);

        const withNewEpisode = sampleHistory();
        withNewEpisode[1].episodes.push({ season: 1, number: 3, watched_at: '2026-10-05T20:00:00' });
        store = core.createHiddenHistoryStore(core.createSafeStorage(() => storage));
        store.load(withNewEpisode);
        emit({ hiddenNow, afterNewEpisode: visible(store, withNewEpisode) });
    } else if (scenario === 'restore') {
        const storage = memoryStorage();
        const items = sampleHistory();
        const store = core.createHiddenHistoryStore(core.createSafeStorage(() => storage));
        store.load(items);
        store.hide(items[0], items);
        store.hide(items[1], items);
        const key = core.getHiddenKey(items[0]);
        const restoredOne = store.restore(key);
        const afterOne = visible(store, items);
        const restoredAll = store.restoreAll();
        emit({
            restoredOne, afterOne, restoredAll,
            afterAll: visible(store, items),
            stored: JSON.parse(storage.getItem(core.HIDDEN_STORAGE_KEY)).items
        });
    } else if (scenario === 'storage_unavailable') {
        const safe = core.createSafeStorage(() => { const e = new Error('SecurityError'); e.name = 'SecurityError'; throw e; });
        const store = core.createHiddenHistoryStore(safe);
        const items = sampleHistory();
        const { warnings } = store.load(items);
        const saved = store.hide(items[0], items);
        emit({ writable: safe.writable, read: safe.get('anything'), warnings, saved, afterHide: visible(store, items) });
    } else if (scenario === 'quota_exceeded') {
        const storage = quotaStorage();
        const safe = core.createSafeStorage(() => storage);
        const store = core.createHiddenHistoryStore(safe);
        const items = sampleHistory();
        store.load(items);
        const saved = store.hide(items[0], items);
        emit({ writable: safe.writable, saved, afterHide: visible(store, items) });
    } else if (scenario === 'corrupt_storage') {
        const results = {};
        for (const [name, raw] of Object.entries({ notJson: '{oops', wrongShape: '[1,2,3]', nullItems: '{"items":null}' })) {
            const storage = memoryStorage({ [core.HIDDEN_STORAGE_KEY]: raw });
            const store = core.createHiddenHistoryStore(core.createSafeStorage(() => storage));
            const items = sampleHistory();
            const { warnings } = store.load(items);
            const before = visible(store, items);
            const saved = store.hide(items[0], items);
            results[name] = { warnings: warnings.length, before, saved, afterHide: visible(store, items) };
        }
        emit(results);
    } else if (scenario === 'legacy_migration') {
        const items = sampleHistory();
        const storage = memoryStorage({
            [core.LEGACY_HIDDEN_STORAGE_KEY]: JSON.stringify([core.getHiddenKey(items[1]), 42, null])
        });
        const store = core.createHiddenHistoryStore(core.createSafeStorage(() => storage));
        store.load(items);
        emit({
            visible: visible(store, items),
            legacyLeft: storage.getItem(core.LEGACY_HIDDEN_STORAGE_KEY),
            migrated: Object.keys(JSON.parse(storage.getItem(core.HIDDEN_STORAGE_KEY)).items)
        });
    } else if (scenario === 'counts') {
        const items = sampleHistory();
        // Legacy shape: one row per episode for the same show, with a repeated episode.
        const legacy = [
            { simkl_id: 303, title: 'Legacy Show', type: 'tv', season: 1, episode: 1, watched_at: '2026-01-01T10:00:00' },
            { simkl_id: 303, title: 'Legacy Show', type: 'tv', season: 1, episode: 2, watched_at: '2026-01-02T10:00:00' },
            { simkl_id: 303, title: 'Legacy Show', type: 'tv', season: 1, episode: 1, watched_at: '2026-01-03T10:00:00' }
        ];
        const counts = core.buildHistoryCounts([items[0], items[1], ...legacy]);
        emit({
            movie: counts.get('101'),
            show: counts.get('202'),
            legacy: counts.get('303'),
            microseconds: core.parseTimestamp('2026-10-01T20:00:00.123456') === Date.parse('2026-10-01T20:00:00.123'),
            invalid: core.parseTimestamp('not a date'),
            escaped: core.escapeHtml(`<img src=x onerror="alert('1')">&`)
        });
    } else {
        throw new Error(`unknown scenario ${scenario}`);
    }
""")

# A deliberately small fake DOM: enough for script.js to boot, render cards and
# wire its listeners, so tests can click the real handlers.
DOM_HARNESS = textwrap.dedent(r"""
    class FakeClassList {
        constructor() { this.set = new Set(); }
        add(...c) { c.forEach(x => this.set.add(x)); }
        remove(...c) { c.forEach(x => this.set.delete(x)); }
        toggle(c) { if (this.set.has(c)) { this.set.delete(c); return false; } this.set.add(c); return true; }
        contains(c) { return this.set.has(c); }
    }

    class FakeElement {
        constructor(tag, id = null) {
            this.tagName = String(tag).toUpperCase();
            this.id = id;
            this.style = { setProperty() {}, removeProperty() {} };
            this.dataset = {};
            this.classList = new FakeClassList();
            this.children = [];
            this.options = [];
            this.listeners = {};
            this.attributes = {};
            this.value = this.tagName === 'SELECT' ? 'all' : '';
            this.hidden = false;
            this.disabled = false;
            this.textContent = '';
            this._innerHTML = '';
            this._closest = {};
        }
        get innerHTML() { return this._innerHTML; }
        set innerHTML(v) { this._innerHTML = String(v); this.children = []; }
        addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
        removeEventListener() {}
        appendChild(child) { this.children.push(child); if (this.tagName === 'SELECT') this.options.push(child); return child; }
        append(...kids) { kids.forEach(k => this.appendChild(k)); }
        replaceChildren() { this.children = []; }
        remove(index) { if (typeof index === 'number') this.options.splice(index, 1); }
        querySelector() { return null; }
        querySelectorAll() { return []; }
        closest(selector) { return this._closest[selector] || null; }
        setAttribute(name, value) { this.attributes[name] = String(value); }
        getAttribute(name) { return this.attributes[name] ?? null; }
        focus() {}
        getBoundingClientRect() { return { top: 0, left: 0, width: 100, height: 150 }; }
        getContext() { return null; }
        click() { (this.listeners.click || []).forEach(fn => fn({ target: this })); }
    }

    function bootViewer({ history, storageFactory, confirmAnswer = true }) {
        const elements = new Map();
        const document = {
            body: new FakeElement('body'),
            listeners: {},
            getElementById(id) {
                if (!elements.has(id)) {
                    const tag = id.startsWith('filter-') || id === 'sort-by' ? 'select' : 'div';
                    elements.set(id, new FakeElement(tag, id));
                }
                return elements.get(id);
            },
            createElement: tag => new FakeElement(tag),
            addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
            querySelector: () => null,
            querySelectorAll: () => []
        };
        const confirmations = [];
        const window = {
            confirm(message) { confirmations.push(message); return confirmAnswer; },
            open() { throw new Error('viewer tried to open a window'); },
            scrollTo() {}
        };
        Object.defineProperty(window, 'localStorage', { get: storageFactory });
        const quietConsole = { log() {}, debug() {}, info() {}, warn() {}, error: (...a) => { errors.push(a.map(String).join(' ')); } };
        const errors = [];
        const context = vm.createContext({
            document, window, console: quietConsole, HISTORY_DATA: history,
            setTimeout: fn => { fn(); return 0; }, clearTimeout() {}, Date, JSON, Math, Number, String, Array, Object, Map, Set, Error
        });
        vm.runInContext(fs.readFileSync(SCRIPT_PATH, 'utf8'), context, { filename: 'script.js' });
        document.listeners.DOMContentLoaded.forEach(fn => fn());

        const byId = id => document.getElementById(id);
        const cards = () => byId('history-container').children;
        return {
            byId, cards, confirmations, errors,
            cardTitles: () => cards().map(c => (c.innerHTML.match(/class="media-title"[^>]*>([^<]*)/) || [])[1].trim()),
            clickHide(card) {
                const button = new FakeElement('button');
                button._closest = { '.hide-history-btn': button, '.media-card': card, 'button, a': button };
                byId('history-container').listeners.click.forEach(fn => fn({ target: button }));
            }
        };
    }

    const scenario = process.argv[3];
    if (scenario === 'hide_and_restore_flow') {
        const storage = memoryStorage();
        const history = sampleHistory();
        history.push({ simkl_id: 404, title: '<img src=x onerror=alert(1)>', type: 'movie', year: 2022,
                       watched_at: '2026-10-04T10:00:00', file_path: 'C:\\Media\\"><script>x</script>.mkv' });
        const snapshot = JSON.stringify(history);
        const viewer = bootViewer({ history, storageFactory: () => storage });

        const initial = viewer.cards().map(c => c.innerHTML).join('\n');
        const initialTitles = viewer.cardTitles();
        const toggleHiddenAtStart = viewer.byId('hidden-items-toggle').style.display;

        const showCard = viewer.cards().find(c => c.innerHTML.includes('Show B'));
        viewer.clickHide(showCard);
        const afterHideTitles = viewer.cardTitles();
        const toggleAfterHide = viewer.byId('hidden-items-toggle').style.display;
        const countAfterHide = viewer.byId('hidden-items-count').textContent;
        const notice = viewer.byId('viewer-notice').textContent;
        const stored = JSON.parse(storage.getItem('simkl_history_hidden_items')).items;
        const rows = viewer.byId('hidden-items-list').children;
        const rowLabels = rows.map(r => r.children[0].textContent);

        // Restore through the button the page rendered in the hidden-items list.
        rows[0].children[2].click();
        emit({
            initialTitles,
            hideButtonLabels: (initial.match(/aria-label="[^"]*"/g) || []).filter(l => l.includes('view')).length,
            mentionsRemove: /Remove|trash/.test(initial),
            rawXss: initial.includes('<img src=x onerror') || initial.includes('<script>'),
            escapedXss: initial.includes('&lt;img src=x onerror=alert(1)&gt;'),
            toggleHiddenAtStart,
            confirmText: viewer.confirmations[0],
            afterHideTitles, toggleAfterHide, countAfterHide, notice, storedKeys: Object.keys(stored), rowLabels,
            afterRestoreTitles: viewer.cardTitles(),
            toggleAfterRestore: viewer.byId('hidden-items-toggle').style.display,
            storedAfterRestore: JSON.parse(storage.getItem('simkl_history_hidden_items')).items,
            historyUntouched: JSON.stringify(history) === snapshot,
            errors: viewer.errors
        });
    } else if (scenario === 'cancelled_confirm') {
        const storage = memoryStorage();
        const viewer = bootViewer({ history: sampleHistory(), storageFactory: () => storage, confirmAnswer: false });
        viewer.clickHide(viewer.cards()[0]);
        emit({ titles: viewer.cardTitles(), stored: storage.getItem('simkl_history_hidden_items'), errors: viewer.errors });
    } else if (scenario === 'blocked_storage') {
        const viewer = bootViewer({
            history: sampleHistory(),
            storageFactory: () => { const e = new Error('SecurityError'); e.name = 'SecurityError'; throw e; }
        });
        const startNotice = viewer.byId('viewer-notice').textContent;
        const startCount = viewer.cards().length;
        viewer.clickHide(viewer.cards().find(c => c.innerHTML.includes('Movie A')));
        emit({
            startCount, startNotice,
            afterHideTitles: viewer.cardTitles(),
            notice: viewer.byId('viewer-notice').textContent,
            errors: viewer.errors
        });
    } else if (scenario === 'all_hidden_empty_state') {
        const storage = memoryStorage();
        const history = [sampleHistory()[0]];
        const viewer = bootViewer({ history, storageFactory: () => storage });
        viewer.clickHide(viewer.cards()[0]);
        emit({
            cards: viewer.cards().length,
            emptyDisplay: viewer.byId('empty-history').style.display,
            toggle: viewer.byId('hidden-items-toggle').style.display
        });
    } else {
        throw new Error(`unknown scenario ${scenario}`);
    }
""")


def _run(tmp_path, body, scenario):
    harness = tmp_path / "harness.js"
    harness.write_text(JS_PRELUDE + body, encoding="utf-8")
    proc = subprocess.run(
        [NODE, str(harness), str(SCRIPT_PATH), scenario],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_script_is_valid_javascript():
    proc = subprocess.run([NODE, "--check", str(SCRIPT_PATH)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr


def test_hidden_title_persists_until_it_is_watched_again(tmp_path):
    result = _run(tmp_path, CORE_SCENARIOS, "persist_and_rewatch")
    assert result["saved"] is True
    assert "movie:Movie A" not in result["afterHide"]
    # Same simkl_id with a different type is a different title.
    assert "anime:Same id, other type" in result["afterHide"]
    assert "movie:Movie A" not in result["afterReload"]
    assert result["listed"] == ["movie::101"]
    assert "movie:Movie A" in result["afterRewatch"]
    assert result["storedAfterRewatch"] == {}
    assert result["inputUntouched"] is True


def test_new_episode_brings_hidden_show_back(tmp_path):
    result = _run(tmp_path, CORE_SCENARIOS, "new_episode_unhides_show")
    assert "show:Show B" not in result["hiddenNow"]
    assert "show:Show B" in result["afterNewEpisode"]


def test_restore_single_and_all(tmp_path):
    result = _run(tmp_path, CORE_SCENARIOS, "restore")
    assert result["restoredOne"] is True
    assert "movie:Movie A" in result["afterOne"]
    assert "show:Show B" not in result["afterOne"]
    assert result["restoredAll"] is True
    assert len(result["afterAll"]) == 3
    assert result["stored"] == {}


def test_unavailable_storage_hides_for_session_only(tmp_path):
    result = _run(tmp_path, CORE_SCENARIOS, "storage_unavailable")
    assert result["writable"] is False
    assert result["read"] is None
    assert result["warnings"] == []
    assert result["saved"] is False
    assert "movie:Movie A" not in result["afterHide"]


def test_full_storage_reports_unsaved_hide(tmp_path):
    result = _run(tmp_path, CORE_SCENARIOS, "quota_exceeded")
    assert result["writable"] is False
    assert result["saved"] is False
    assert "movie:Movie A" not in result["afterHide"]


def test_corrupt_hidden_list_is_ignored_and_replaced(tmp_path):
    result = _run(tmp_path, CORE_SCENARIOS, "corrupt_storage")
    for name, outcome in result.items():
        assert outcome["warnings"] == 1, name
        assert len(outcome["before"]) == 3, name
        assert outcome["saved"] is True, name
        assert "movie:Movie A" not in outcome["afterHide"], name


def test_legacy_removed_keys_are_migrated(tmp_path):
    result = _run(tmp_path, CORE_SCENARIOS, "legacy_migration")
    assert "show:Show B" not in result["visible"]
    assert len(result["visible"]) == 2
    assert result["legacyLeft"] is None
    assert result["migrated"] == ["tv::202"]


def test_counts_respect_episode_groups_and_explicit_counts(tmp_path):
    result = _run(tmp_path, CORE_SCENARIOS, "counts")
    assert result["movie"]["watchCount"] == 2 and result["movie"]["rewatchCount"] == 1
    # App-written show totals: 3 episode plays, 1 of them a rewatch.
    assert result["show"]["watchCount"] == 3 and result["show"]["rewatchCount"] == 1
    # Legacy per-episode rows: only the repeated S01E01 counts as a rewatch.
    assert result["legacy"]["watchCount"] == 3 and result["legacy"]["rewatchCount"] == 1
    assert result["microseconds"] is True
    assert result["invalid"] is None
    assert result["escaped"] == "&lt;img src=x onerror=&quot;alert(&#39;1&#39;)&quot;&gt;&amp;"


def test_viewer_hide_and_restore_flow(tmp_path):
    result = _run(tmp_path, DOM_HARNESS, "hide_and_restore_flow")
    assert result["errors"] == []
    assert "Show B (2019)" in result["initialTitles"]
    assert result["hideButtonLabels"] == 4
    assert result["mentionsRemove"] is False
    assert result["rawXss"] is False
    assert result["escapedXss"] is True
    assert result["toggleHiddenAtStart"] == "none"
    assert "does NOT delete" in result["confirmText"]
    assert "Simkl" in result["confirmText"]

    assert "Show B (2019)" not in result["afterHideTitles"]
    assert len(result["afterHideTitles"]) == 3
    assert result["toggleAfterHide"] == ""
    assert result["countAfterHide"] == "1"
    assert "hidden from this view" in result["notice"]
    assert result["storedKeys"] == ["tv::202"]
    assert result["rowLabels"] == ["Show B (2019)"]

    assert "Show B (2019)" in result["afterRestoreTitles"]
    assert result["toggleAfterRestore"] == "none"
    assert result["storedAfterRestore"] == {}
    assert result["historyUntouched"] is True


def test_cancelled_confirmation_changes_nothing(tmp_path):
    result = _run(tmp_path, DOM_HARNESS, "cancelled_confirm")
    assert result["errors"] == []
    assert len(result["titles"]) == 3
    assert result["stored"] is None


def test_viewer_works_when_storage_is_blocked(tmp_path):
    result = _run(tmp_path, DOM_HARNESS, "blocked_storage")
    assert result["errors"] == []
    assert result["startCount"] == 3
    assert "storage is unavailable" in result["startNotice"]
    assert "Movie A (2020)" not in result["afterHideTitles"]
    assert "will show again next time" in result["notice"]


def test_all_hidden_shows_restore_hint(tmp_path):
    result = _run(tmp_path, DOM_HARNESS, "all_hidden_empty_state")
    assert result["cards"] == 0
    assert result["emptyDisplay"] == "block"
    assert result["toggle"] == ""
