"""MkDocs plugin that injects Speks widget JS into pages and registers
the shared CSS stylesheet via ``extra_css``.

CSS is served as an external file (``assets/speks.css``) through MkDocs'
``extra_css`` mechanism.  The plugin copies the packaged stylesheet into
the docs directory at config-time and appends it to ``extra_css``.

JavaScript for the playground is still injected inline via
``on_post_page`` because it contains runtime i18n data.
"""

from __future__ import annotations

import importlib.resources
import json
import shutil
from pathlib import Path

from mkdocs.config.defaults import MkDocsConfig
from mkdocs.plugins import BasePlugin
from mkdocs.structure.pages import Page

from speks.i18n import t

# ---------------------------------------------------------------------------
# JS (injected before </body>)
# ---------------------------------------------------------------------------

PLAYGROUND_JS_TEMPLATE = """\
<script>
window.SPEKS_I18N = {i18n_json};

/* ── Last run state (for save) ── */
window._swLastRun = {{}};

document.addEventListener('DOMContentLoaded', function() {{
  document.querySelectorAll('.speks-playground-form').forEach(function(form) {{
    const btn = form.querySelector('.speks-run-btn');
    if (!btn) return;
    function check() {{
      const missing = form.querySelectorAll('input[required]:not(.speks-error-checkbox):not(.speks-mock-pydantic-input):not(.speks-error-field-input)');
      btn.disabled = Array.from(missing).some(i => !i.value.trim());
    }}
    form.addEventListener('input', check);
    check();
  }});
  /* Toggle error fields on checkbox change */
  document.querySelectorAll('.speks-error-checkbox').forEach(function(cb) {{
    cb.addEventListener('change', function() {{
      const svc = cb.dataset.service;
      const container = cb.closest('.speks-mock-field');
      if (!container) return;
      /* Structured error fields */
      container.querySelectorAll('.speks-error-field-input[data-service="' + svc + '"]').forEach(
        function(input) {{ input.disabled = !cb.checked; }}
      );
      /* Legacy textarea fallback */
      const ta = container.querySelector('.speks-error-input[data-service="' + svc + '"]');
      if (ta) ta.disabled = !cb.checked;
    }});
  }});
}});

/* ── Helpers ── */
function _swSetPath(obj, path, val) {{
  const parts = path.split('.');
  let cur = obj;
  for (let i = 0; i < parts.length - 1; i++) {{
    if (!(parts[i] in cur) || typeof cur[parts[i]] !== 'object' || cur[parts[i]] === null) {{
      cur[parts[i]] = {{}};
    }}
    cur = cur[parts[i]];
  }}
  cur[parts[parts.length - 1]] = val;
}}

function _swFillStructured(form, prefix, obj) {{
  if (typeof obj !== 'object' || obj === null) return;
  Object.entries(obj).forEach(([key, val]) => {{
    const path = prefix + '.' + key;
    if (typeof val === 'object' && val !== null && !Array.isArray(val)) {{
      _swFillStructured(form, path, val);
    }} else {{
      const input = form.querySelector('input[data-path="' + path + '"]');
      if (input) {{
        input.value = val;
        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
      }}
    }}
  }});
}}

function _swCollectForm(form) {{
  const data = {{}};
  /* Collect plain (non-structured) input fields */
  form.querySelectorAll('input:not(.speks-error-checkbox):not(.speks-mock-pydantic-input):not(.speks-error-field-input):not(.speks-structured-input)').forEach(input => {{
    let val = input.value;
    if (input.type === 'number') val = Number(val);
    data[input.name] = val;
  }});
  /* Collect structured (Pydantic) input fields and assemble nested objects */
  form.querySelectorAll('input.speks-structured-input').forEach(input => {{
    const path = input.dataset.path;
    if (!path) return;
    let val = input.value;
    if (input.type === 'number') val = val === '' ? null : Number(val);
    else if (val === 'true') val = true;
    else if (val === 'false') val = false;
    _swSetPath(data, path, val);
  }});
  const mockOverrides = {{}};
  const errorOverrides = {{}};
  let hasInvalid = false;
  /* Collect structured Pydantic mock fields */
  form.querySelectorAll('.speks-mock-pydantic').forEach(container => {{
    const serviceName = container.dataset.service;
    const obj = {{}};
    container.querySelectorAll('.speks-mock-pydantic-input').forEach(input => {{
      let val = input.value;
      if (input.type === 'number') val = val === '' ? null : Number(val);
      obj[input.dataset.field] = val;
    }});
    mockOverrides[serviceName] = obj;
  }});
  /* Collect raw JSON textarea mock fields (non-Pydantic) */
  form.querySelectorAll('.speks-mock-input').forEach(ta => {{
    ta.classList.remove('invalid');
    const serviceName = ta.dataset.service;
    const raw = ta.value.trim();
    if (!raw) return;
    try {{
      mockOverrides[serviceName] = JSON.parse(raw);
    }} catch (e) {{
      ta.classList.add('invalid');
      hasInvalid = true;
    }}
  }});
  form.querySelectorAll('.speks-error-checkbox:checked').forEach(cb => {{
    const serviceName = cb.dataset.service;
    /* Structured error fields */
    const errFields = form.querySelectorAll('.speks-error-field-input[data-service="' + serviceName + '"]');
    if (errFields.length > 0) {{
      const obj = {{}};
      errFields.forEach(input => {{
        let val = input.value;
        if (input.type === 'number') val = val === '' ? null : Number(val);
        obj[input.dataset.errorField] = val;
      }});
      errorOverrides[serviceName] = obj;
    }} else {{
      /* Legacy textarea fallback */
      const errTa = form.querySelector('.speks-error-input[data-service="' + serviceName + '"]');
      if (errTa) {{
        errTa.classList.remove('invalid');
        const raw = errTa.value.trim();
        if (raw) {{
          try {{
            errorOverrides[serviceName] = JSON.parse(raw);
          }} catch (e) {{
            errTa.classList.add('invalid');
            hasInvalid = true;
          }}
        }}
      }}
    }}
  }});
  return {{ data, mockOverrides, errorOverrides, hasInvalid }};
}}

async function _swExecute(funcName, data, mockOverrides, errorOverrides) {{
  const payload = {{function: funcName, args: data, mock_overrides: mockOverrides}};
  if (errorOverrides && Object.keys(errorOverrides).length > 0) {{
    payload.error_overrides = errorOverrides;
  }}
  const resp = await fetch('/api/run', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(payload),
  }});
  return await resp.json();
}}

/* ── Run ── */
async function swRunFunction(btn) {{
  const i18n = window.SPEKS_I18N;
  const form = btn.closest('.speks-playground-form');
  const funcName = form.dataset.function;
  const resultDiv = document.getElementById('speks-result-' + funcName);

  const {{ data, mockOverrides, errorOverrides, hasInvalid }} = _swCollectForm(form);

  if (hasInvalid) {{
    resultDiv.className = 'speks-result error';
    resultDiv.style.display = 'block';
    resultDiv.textContent = i18n.invalid_json;
    return;
  }}

  resultDiv.className = 'speks-result';
  resultDiv.style.display = 'block';
  resultDiv.textContent = i18n.running;

  try {{
    const json = await _swExecute(funcName, data, mockOverrides, errorOverrides);
    if (json.success) {{
      resultDiv.className = 'speks-result success';
      let txt = i18n.inputs_label + '\\n' + JSON.stringify(data, null, 2);
      txt += '\\n\\n' + i18n.result_label + '\\n' + JSON.stringify(json.result, null, 2);
      if (json.call_log && json.call_log.length) {{
        txt += '\\n\\n' + i18n.calls_label + '\\n' +
          JSON.stringify(json.call_log, null, 2);
      }}
      resultDiv.textContent = txt;
      // Enable save button and store last run
      window._swLastRun[funcName] = {{ inputs: data, mocks: mockOverrides, error_mocks: errorOverrides, result: json.result }};
      const saveBtn = form.closest('.speks-playground-widget').querySelector('.speks-tc-save-btn');
      if (saveBtn) saveBtn.disabled = false;
    }} else {{
      resultDiv.className = 'speks-result error';
      resultDiv.textContent = i18n.error_prefix + json.error;
    }}
  }} catch (e) {{
    resultDiv.className = 'speks-result error';
    resultDiv.textContent = i18n.network_error + e.message;
  }}
}}

/* ── Save test case ── */
async function swSaveTestCase(btn) {{
  const i18n = window.SPEKS_I18N;
  const funcName = btn.dataset.function;
  const last = window._swLastRun[funcName];
  if (!last) return;

  const name = prompt(i18n.tc_name_prompt);
  if (!name) return;

  /* Let user confirm/edit the expected result */
  const defaultExpected = JSON.stringify(last.result, null, 2);
  const expectedInput = prompt(i18n.tc_expected_prompt, defaultExpected);
  if (expectedInput === null) return;
  let expectedValue;
  try {{
    expectedValue = JSON.parse(expectedInput);
  }} catch (e) {{
    expectedValue = expectedInput;
  }}

  try {{
    const resp = await fetch('/api/testcases/' + funcName, {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{
        name: name,
        inputs: last.inputs,
        mocks: last.mocks,
        expected: expectedValue,
        error_mocks: last.error_mocks || {{}},
      }}),
    }});
    const tc = await resp.json();
    // Add to list
    const list = document.getElementById('speks-tc-list-' + funcName);
    if (list) {{
      // Remove "no test cases" placeholder
      const placeholder = list.querySelector('em');
      if (placeholder) placeholder.closest('li').remove();
      const li = document.createElement('li');
      li.className = 'speks-tc-item';
      const safeId = _swEscapeHtml(tc.id);
      li.id = 'speks-tc-' + safeId;
      const tcData = JSON.stringify({{ inputs: tc.inputs, mocks: tc.mocks, expected: tc.expected, error_mocks: tc.error_mocks || {{}} }});
      li.innerHTML =
        '<span class="speks-tc-name">' + _swEscapeHtml(tc.name) + '</span>' +
        '<span class="speks-tc-badge" id="speks-tc-badge-' + safeId + '"></span>' +
        '<button type="button" class="speks-tc-btn" ' +
        'onclick="swReplayTestCase(this, \\'' + safeId + '\\')" ' +
        'data-function="' + funcName + '" ' +
        "data-tc='" + _swEscapeHtml(tcData) + "'>" +
        i18n.tc_replay + '</button>' +
        '<button type="button" class="speks-tc-btn danger" ' +
        'onclick="swDeleteTestCase(this, \\'' + safeId + '\\')" ' +
        'data-function="' + funcName + '">' +
        i18n.tc_delete + '</button>';
      list.appendChild(li);
    }}
    btn.disabled = true;
  }} catch (e) {{
    // silent fail
  }}
}}

function _swEscapeHtml(s) {{
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}}

/* ── Fill form from test case data ── */
function _swFillForm(funcName, tcData) {{
  const widget = document.querySelector('.speks-playground-widget[data-function="' + funcName + '"]');
  if (!widget) return;
  const form = widget.querySelector('.speks-playground-form');
  if (!form) return;

  /* Fill input fields */
  if (tcData.inputs) {{
    /* Plain inputs */
    Object.entries(tcData.inputs).forEach(([key, val]) => {{
      if (typeof val === 'object' && val !== null) {{
        /* Structured type — fill via data-path attributes */
        _swFillStructured(form, key, val);
      }} else {{
        const input = form.querySelector('input[name="' + key + '"]');
        if (input) {{
          input.value = val;
          input.dispatchEvent(new Event('input', {{ bubbles: true }}));
        }}
      }}
    }});
  }}

  /* Fill mock fields (Pydantic structured or raw JSON) */
  if (tcData.mocks) {{
    Object.entries(tcData.mocks).forEach(([svc, val]) => {{
      /* Try Pydantic structured fields first */
      const pydantic = form.querySelector('.speks-mock-pydantic[data-service="' + svc + '"]');
      if (pydantic && typeof val === 'object' && val !== null) {{
        Object.entries(val).forEach(([field, fval]) => {{
          const input = pydantic.querySelector('.speks-mock-pydantic-input[data-field="' + field + '"]');
          if (input) {{
            input.value = fval;
            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
          }}
        }});
      }} else {{
        /* Fallback: raw JSON textarea */
        const ta = form.querySelector('.speks-mock-input[data-service="' + svc + '"]');
        if (ta) ta.value = JSON.stringify(val, null, 2);
      }}
    }});
  }}

  /* Fill error mock checkboxes and fields */
  form.querySelectorAll('.speks-error-checkbox').forEach(cb => {{
    const svc = cb.dataset.service;
    const errFields = form.querySelectorAll('.speks-error-field-input[data-service="' + svc + '"]');
    const errTa = form.querySelector('.speks-error-input[data-service="' + svc + '"]');
    if (tcData.error_mocks && tcData.error_mocks[svc]) {{
      cb.checked = true;
      const errData = tcData.error_mocks[svc];
      if (errFields.length > 0 && typeof errData === 'object') {{
        errFields.forEach(input => {{
          input.disabled = false;
          const field = input.dataset.errorField;
          if (field in errData) input.value = errData[field];
        }});
      }} else if (errTa) {{
        errTa.disabled = false;
        errTa.value = JSON.stringify(errData, null, 2);
      }}
    }} else {{
      cb.checked = false;
      errFields.forEach(input => {{ input.disabled = true; }});
      if (errTa) errTa.disabled = true;
    }}
  }});

  /* Open the playground details if closed */
  const details = widget.closest('details') || widget;
  if (details.tagName === 'DETAILS') details.open = true;
}}

/* ── Replay single test case ── */
async function swReplayTestCase(btn, tcId) {{
  const i18n = window.SPEKS_I18N;
  const funcName = btn.dataset.function;
  const tcData = JSON.parse(btn.dataset.tc);
  const badge = document.getElementById('speks-tc-badge-' + tcId);
  const resultDiv = document.getElementById('speks-result-' + funcName);

  /* Fill form with test case inputs */
  _swFillForm(funcName, tcData);

  const errorMocks = tcData.error_mocks || {{}};

  try {{
    const json = await _swExecute(funcName, tcData.inputs, tcData.mocks || {{}}, errorMocks);
    const pass = json.success && JSON.stringify(json.result) === JSON.stringify(tcData.expected);

    badge.textContent = pass ? i18n.tc_pass : i18n.tc_fail;
    badge.className = 'speks-tc-badge ' + (pass ? 'pass' : 'fail');

    // Show full output in result area
    if (resultDiv && json.success) {{
      resultDiv.className = 'speks-result ' + (pass ? 'success' : 'error');
      resultDiv.style.display = 'block';
      let txt = i18n.inputs_label + '\\n' + JSON.stringify(tcData.inputs, null, 2);
      txt += '\\n\\n' + i18n.result_label + '\\n' + JSON.stringify(json.result, null, 2);
      if (!pass) {{
        txt += '\\n\\n' + i18n.tc_expected + ' ' + JSON.stringify(tcData.expected, null, 2);
        txt += '\\n' + i18n.tc_actual + ' ' + JSON.stringify(json.result, null, 2);
      }}
      if (json.call_log && json.call_log.length) {{
        txt += '\\n\\n' + i18n.calls_label + '\\n' + JSON.stringify(json.call_log, null, 2);
      }}
      resultDiv.textContent = txt;
    }} else if (resultDiv && !json.success) {{
      resultDiv.className = 'speks-result error';
      resultDiv.style.display = 'block';
      resultDiv.textContent = i18n.error_prefix + json.error;
    }}
  }} catch (e) {{
    badge.textContent = i18n.tc_fail;
    badge.className = 'speks-tc-badge fail';
    if (resultDiv) {{
      resultDiv.className = 'speks-result error';
      resultDiv.style.display = 'block';
      resultDiv.textContent = i18n.network_error + e.message;
    }}
  }}
  return badge.classList.contains('pass');
}}

/* ── Delete test case ── */
async function swDeleteTestCase(btn, tcId) {{
  const i18n = window.SPEKS_I18N;
  const funcName = btn.dataset.function;
  if (!confirm(i18n.tc_confirm_delete)) return;

  try {{
    await fetch('/api/testcases/' + funcName + '/' + tcId, {{ method: 'DELETE' }});
    const li = document.getElementById('speks-tc-' + tcId);
    if (li) li.remove();
  }} catch (e) {{
    // silent fail
  }}
}}

/* ── Replay all ── */
async function swReplayAll(btn) {{
  const i18n = window.SPEKS_I18N;
  const funcName = btn.dataset.function;
  const list = document.getElementById('speks-tc-list-' + funcName);
  const summaryEl = document.getElementById('speks-tc-summary-' + funcName);
  const items = list.querySelectorAll('.speks-tc-item');

  let passed = 0;
  let total = 0;
  for (const li of items) {{
    const replayBtn = li.querySelector('.speks-tc-btn[onclick^="swReplayTestCase"]');
    if (!replayBtn) continue;
    total++;
    const tcId = replayBtn.getAttribute('onclick').match(/'([^']+)'/)[1];
    const ok = await swReplayTestCase(replayBtn, tcId);
    if (ok) passed++;
  }}

  if (summaryEl) {{
    summaryEl.textContent = i18n.tc_summary.replace('{{passed}}', passed).replace('{{total}}', total);
    summaryEl.className = 'speks-tc-summary ' + (passed === total ? 'all-pass' : 'has-fail');
  }}
}}
</script>
"""


def _build_playground_js() -> str:
    """Build the playground JS with translated strings."""
    i18n_data = {
        "invalid_json": t("js.invalid_json"),
        "running": t("js.running"),
        "error_prefix": t("js.error_prefix"),
        "network_error": t("js.network_error"),
        "inputs_label": t("js.inputs_label"),
        "result_label": t("js.result_label"),
        "calls_label": t("js.calls_label"),
        "tc_name_prompt": t("tc.name_prompt"),
        "tc_expected_prompt": t("tc.expected_prompt"),
        "tc_saved": t("tc.saved"),
        "tc_replay": t("tc.replay"),
        "tc_delete": t("tc.delete"),
        "tc_confirm_delete": t("tc.confirm_delete"),
        "tc_pass": t("tc.pass"),
        "tc_fail": t("tc.fail"),
        "tc_expected": t("tc.expected"),
        "tc_actual": t("tc.actual"),
        "tc_summary": t("tc.summary"),
    }
    return PLAYGROUND_JS_TEMPLATE.format(i18n_json=json.dumps(i18n_data, ensure_ascii=False))


class SpeksPlaygroundPlugin(BasePlugin):  # type: ignore[type-arg,no-untyped-call]
    """Inject playground JS into MkDocs pages and register shared CSS."""

    def on_config(self, config: MkDocsConfig) -> MkDocsConfig:
        """Copy packaged assets (CSS + logos) into docs and register them."""
        assets = importlib.resources.files("speks").joinpath("assets")
        docs_dir = Path(str(config["docs_dir"]))
        dest_dir = docs_dir / "assets"
        dest_dir.mkdir(parents=True, exist_ok=True)

        # CSS
        css_src = Path(str(assets.joinpath("speks.css")))
        if css_src.is_file():
            shutil.copy2(css_src, dest_dir / "speks.css")
            css_path = "assets/speks.css"
            if css_path not in config.get("extra_css", []):
                config["extra_css"].append(css_path)

        # Logos — copy and inject into theme config if not already set
        for name in ("logo.svg", "logo-white.svg"):
            src = Path(str(assets.joinpath(name)))
            if src.is_file():
                shutil.copy2(src, dest_dir / name)

        theme = config["theme"]
        if not theme.get("logo"):
            logo_white = dest_dir / "logo-white.svg"
            if logo_white.is_file():
                theme["logo"] = "assets/logo-white.svg"
        if not theme.get("favicon"):
            logo = dest_dir / "logo.svg"
            if logo.is_file():
                theme["favicon"] = "assets/logo.svg"

        # Footer override — prepend packaged overrides to theme dirs
        overrides_dir = Path(str(assets.joinpath("overrides")))
        if overrides_dir.is_dir() and hasattr(theme, "dirs"):
            if str(overrides_dir) not in theme.dirs:
                theme.dirs.insert(0, str(overrides_dir))

        return config

    def on_post_page(
        self,
        output: str,
        *,
        page: Page,
        config: MkDocsConfig,
    ) -> str:
        if "speks-playground-widget" not in output:
            return output

        # Skip injecting interactive JS for versioned (read-only) builds
        import os
        if os.environ.get("SPEKS_VERSIONED_BUILD") == "1":
            return output

        output = output.replace("</body>", _build_playground_js() + "</body>", 1)
        return output
