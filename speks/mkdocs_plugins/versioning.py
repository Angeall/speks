"""MkDocs plugin that injects a version selector and diff comparison UI.

The plugin adds:
- A version selector dropdown in the page header
- A "Compare versions" button that opens a side-by-side diff view
- JavaScript that fetches ``/versions.json`` and ``/api/diff`` for rendering
"""

from __future__ import annotations

import json

from mkdocs.config.defaults import MkDocsConfig
from mkdocs.plugins import BasePlugin
from mkdocs.structure.pages import Page

from speks.i18n import t

# ---------------------------------------------------------------------------
# Version selector + diff UI (injected before </body>)
# ---------------------------------------------------------------------------

VERSIONING_JS = """\
<script>
(function() {{
  const i18n = {i18n_json};
  const DIFF_CSS_URL = 'https://cdn.jsdelivr.net/npm/diff2html@3.4.48/bundles/css/diff2html.min.css';
  const DIFF_JS_URL = 'https://cdn.jsdelivr.net/npm/diff2html@3.4.48/bundles/js/diff2html-ui-slim.min.js';

  /* ── Load versions.json ── */
  let versionsData = [];

  function getBasePath() {{
    /* Detect if we are inside a _versions/<sha>/ path */
    const path = window.location.pathname;
    const match = path.match(/^(.*\\/_versions\\/[^\\/]+\\/).*$/);
    if (match) return match[1];
    return '/';
  }}

  function getCurrentVersion() {{
    const path = window.location.pathname;
    const match = path.match(/\\/_versions\\/([^\\/]+)\\//);
    return match ? match[1] : null;
  }}

  function getPageRelativePath() {{
    const path = window.location.pathname;
    const versionMatch = path.match(/^.*\\/_versions\\/[^\\/]+\\/(.*)$/);
    if (versionMatch) return versionMatch[1];
    return path.replace(/^\\//, '');
  }}

  async function loadVersions() {{
    try {{
      const resp = await fetch('/versions.json');
      if (resp.ok) versionsData = await resp.json();
    }} catch (e) {{
      /* No versions available */
    }}
    if (versionsData.length > 0) {{
      injectVersionSelector();
    }}
  }}

  /* ── Version selector dropdown ── */
  function injectVersionSelector() {{
    const header = document.querySelector('.md-header__inner');
    if (!header) return;

    const container = document.createElement('div');
    container.className = 'speks-version-selector';

    const currentSha = getCurrentVersion();
    const pagePath = getPageRelativePath();

    /* Version dropdown */
    const select = document.createElement('select');
    select.className = 'speks-version-select';

    const currentOpt = document.createElement('option');
    currentOpt.value = '/';
    currentOpt.textContent = i18n.current_version;
    if (!currentSha) currentOpt.selected = true;
    select.appendChild(currentOpt);

    versionsData.forEach(function(v) {{
      const opt = document.createElement('option');
      opt.value = '/_versions/' + v.short_sha + '/';
      opt.textContent = v.short_sha + ' — ' +
        v.date.split('T')[0] + ' — ' + v.subject.substring(0, 50);
      if (currentSha === v.short_sha) opt.selected = true;
      select.appendChild(opt);
    }});

    select.addEventListener('change', function() {{
      window.location.href = select.value + pagePath;
    }});

    /* Compare button */
    const compareBtn = document.createElement('button');
    compareBtn.className = 'speks-compare-btn';
    compareBtn.textContent = i18n.compare_versions;
    compareBtn.addEventListener('click', openCompareDialog);

    container.appendChild(select);
    container.appendChild(compareBtn);
    header.appendChild(container);
  }}

  /* ── Compare dialog ── */
  function openCompareDialog() {{
    /* Remove existing dialog */
    const existing = document.getElementById('speks-diff-dialog');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'speks-diff-dialog';
    overlay.className = 'speks-diff-overlay';

    const dialog = document.createElement('div');
    dialog.className = 'speks-diff-dialog';

    /* Header */
    const header = document.createElement('div');
    header.className = 'speks-diff-header';
    header.innerHTML = '<h3>' + i18n.compare_title + '</h3>';

    const closeBtn = document.createElement('button');
    closeBtn.className = 'speks-diff-close';
    closeBtn.textContent = '\\u00d7';
    closeBtn.addEventListener('click', function() {{ overlay.remove(); }});
    header.appendChild(closeBtn);

    /* Controls */
    const controls = document.createElement('div');
    controls.className = 'speks-diff-controls';

    /* From selector */
    const fromLabel = document.createElement('label');
    fromLabel.textContent = i18n.from_version + ' ';
    const fromSelect = document.createElement('select');
    fromSelect.id = 'speks-diff-from';

    /* To selector */
    const toLabel = document.createElement('label');
    toLabel.textContent = i18n.to_version + ' ';
    const toSelect = document.createElement('select');
    toSelect.id = 'speks-diff-to';

    /* Populate selectors */
    const currentOpt = document.createElement('option');
    currentOpt.value = 'current';
    currentOpt.textContent = i18n.current_version;

    [fromSelect, toSelect].forEach(function(sel) {{
      versionsData.forEach(function(v, idx) {{
        const opt = document.createElement('option');
        opt.value = v.sha;
        opt.textContent = v.short_sha + ' — ' +
        v.date.split('T')[0] + ' — ' + v.subject.substring(0, 50);
        sel.appendChild(opt);
      }});
      const cur = currentOpt.cloneNode(true);
      sel.insertBefore(cur, sel.firstChild);
    }});

    /* Default: from = oldest, to = current */
    if (versionsData.length > 0) {{
      fromSelect.value = versionsData[versionsData.length - 1].sha;
    }}
    toSelect.value = 'current';

    fromLabel.appendChild(fromSelect);
    toLabel.appendChild(toSelect);
    controls.appendChild(fromLabel);
    controls.appendChild(toLabel);

    /* Compare button */
    const runBtn = document.createElement('button');
    runBtn.className = 'speks-diff-run-btn';
    runBtn.textContent = i18n.run_compare;
    runBtn.addEventListener('click', function() {{
      runDiff(fromSelect.value, toSelect.value, resultArea);
    }});
    controls.appendChild(runBtn);

    /* Result area */
    const resultArea = document.createElement('div');
    resultArea.className = 'speks-diff-result';
    resultArea.id = 'speks-diff-result';

    dialog.appendChild(header);
    dialog.appendChild(controls);
    dialog.appendChild(resultArea);
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);

    /* Close on outside click */
    overlay.addEventListener('click', function(e) {{
      if (e.target === overlay) overlay.remove();
    }});
  }}

  /* ── Run diff ── */
  async function runDiff(fromRev, toRev, container) {{
    const pagePath = getPageRelativePath();
    container.innerHTML = '<p>' + i18n.loading_diff + '</p>';

    try {{
      const params = new URLSearchParams({{
        page: pagePath,
        from_rev: fromRev,
        to_rev: toRev,
      }});
      const resp = await fetch('/api/diff?' + params.toString());
      if (!resp.ok) {{
        container.innerHTML = '<p class="speks-diff-error">' + i18n.diff_error + '</p>';
        return;
      }}
      const data = await resp.json();

      if (!data.has_changes) {{
        container.innerHTML = '<p>' + i18n.no_changes + '</p>';
        return;
      }}

      /* Load diff2html if not already loaded */
      await loadDiff2Html();

      container.innerHTML = '';
      const diffElement = document.createElement('div');
      diffElement.id = 'speks-diff-output';
      container.appendChild(diffElement);

      /* Render side-by-side diff */
      const configuration = {{
        drawFileList: false,
        matching: 'lines',
        outputFormat: 'side-by-side',
        highlight: true,
        renderNothingWhenEmpty: false,
      }};
      const diff2htmlUi = new Diff2HtmlUI(diffElement, data.unified_diff, configuration);
      diff2htmlUi.draw();
    }} catch (e) {{
      container.innerHTML = '<p class="speks-diff-error">' +
        i18n.diff_error + ': ' + e.message + '</p>';
    }}
  }}

  /* ── Lazy-load diff2html ── */
  let diff2htmlLoaded = false;
  function loadDiff2Html() {{
    if (diff2htmlLoaded) return Promise.resolve();
    return new Promise(function(resolve, reject) {{
      /* CSS */
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = DIFF_CSS_URL;
      document.head.appendChild(link);

      /* JS */
      const script = document.createElement('script');
      script.src = DIFF_JS_URL;
      script.onload = function() {{
        diff2htmlLoaded = true;
        resolve();
      }};
      script.onerror = reject;
      document.head.appendChild(script);
    }});
  }}

  /* ── Initialize ── */
  if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', loadVersions);
  }} else {{
    loadVersions();
  }}
}})();
</script>
"""


def _build_versioning_js() -> str:
    """Build the versioning JS with translated strings."""
    i18n_data = {
        "current_version": t("versioning.current_version"),
        "compare_versions": t("versioning.compare_versions"),
        "compare_title": t("versioning.compare_title"),
        "from_version": t("versioning.from_version"),
        "to_version": t("versioning.to_version"),
        "run_compare": t("versioning.run_compare"),
        "loading_diff": t("versioning.loading_diff"),
        "diff_error": t("versioning.diff_error"),
        "no_changes": t("versioning.no_changes"),
    }
    return VERSIONING_JS.format(i18n_json=json.dumps(i18n_data, ensure_ascii=False))


class SpeksVersioningPlugin(BasePlugin):  # type: ignore[type-arg,no-untyped-call]
    """Inject version selector and diff UI into every page."""

    def on_post_page(
        self,
        output: str,
        *,
        page: Page,
        config: MkDocsConfig,
    ) -> str:
        js_block = _build_versioning_js()
        output = output.replace("</body>", js_block + "</body>", 1)
        return output
