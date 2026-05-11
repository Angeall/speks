"""E2E reproduction tests for the patient-eligibility playground.

The user reported that the *Run* button stays disabled even after filling
in the two primitive ``str`` parameters of ``check_eligibility``.  These
tests pin the expected behaviour for each of the three playground entry
points exposed by the example project.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect


def _open(page: Page, base: str, page_path: str, func: str) -> None:
    page.goto(f"{base}/{page_path}/")
    page.wait_for_load_state("networkidle")
    widget = page.locator(f".speks-playground-widget[data-function='{func}']")
    widget.evaluate("el => el.open = true")
    widget.locator(".speks-mock-config").evaluate_all(
        "els => els.forEach(e => e.open = true)"
    )


class TestPatientButtonState:
    def test_check_eligibility_enables_with_two_strings(
        self, patient_server: str, page: Page,
    ) -> None:
        _open(page, patient_server, "eligibility", "check_eligibility")
        form = page.locator(
            ".speks-playground-form[data-function='check_eligibility']"
        )
        form.locator("input[name='patient_id']").fill("P-001")
        form.locator("input[name='service_code']").fill("preventive-exam")
        btn = form.locator(".speks-run-btn")
        expect(btn).to_be_enabled()

    def test_estimate_patient_cost_enables_with_all_inputs(
        self, patient_server: str, page: Page,
    ) -> None:
        _open(page, patient_server, "eligibility", "estimate_patient_cost")
        form = page.locator(
            ".speks-playground-form[data-function='estimate_patient_cost']"
        )
        form.locator("input[name='patient_id']").fill("P-001")
        form.locator("input[name='service_code']").fill("diagnostic-imaging")
        form.locator("input[name='billed_amount']").fill("250")
        btn = form.locator(".speks-run-btn")
        expect(btn).to_be_enabled()

    def test_evaluate_prior_auth_enables_with_two_strings(
        self, patient_server: str, page: Page,
    ) -> None:
        _open(page, patient_server, "prior-auth", "evaluate_prior_auth")
        form = page.locator(
            ".speks-playground-form[data-function='evaluate_prior_auth']"
        )
        form.locator("input[name='patient_id']").fill("P-001")
        form.locator("input[name='procedure_code']").fill("MRI-001")
        btn = form.locator(".speks-run-btn")
        expect(btn).to_be_enabled()


class TestPatientPageHealth:
    """Surface JS errors that might explain a stuck disabled button."""

    def test_no_js_errors_on_eligibility_page(
        self, patient_server: str, page: Page,
    ) -> None:
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on(
            "console",
            lambda msg: errors.append(msg.text) if msg.type == "error" else None,
        )
        page.goto(f"{patient_server}/eligibility/")
        page.wait_for_load_state("networkidle")
        assert not errors, "Unexpected JS errors:\n" + "\n".join(errors)

    def test_no_js_errors_on_prior_auth_page(
        self, patient_server: str, page: Page,
    ) -> None:
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on(
            "console",
            lambda msg: errors.append(msg.text) if msg.type == "error" else None,
        )
        page.goto(f"{patient_server}/prior-auth/")
        page.wait_for_load_state("networkidle")
        assert not errors, "Unexpected JS errors:\n" + "\n".join(errors)


class TestPatientRunFlow:
    """Full Run flow on each playground (button → click → result settles)."""

    def _wait_result(self, page: Page, func: str) -> str:
        sel = f"#speks-result-{func}"
        page.locator(f"{sel}.success, {sel}.error").wait_for(
            state="attached", timeout=15_000,
        )
        return page.locator(sel).text_content() or ""

    def test_check_eligibility_runs_to_completion(
        self, patient_server: str, page: Page,
    ) -> None:
        _open(page, patient_server, "eligibility", "check_eligibility")
        form = page.locator(
            ".speks-playground-form[data-function='check_eligibility']"
        )
        form.locator("input[name='patient_id']").fill("P-001")
        form.locator("input[name='service_code']").fill("preventive-exam")
        form.locator(".speks-run-btn").click()
        text = self._wait_result(page, "check_eligibility")
        # Default mocks → eligible=true.  Just check no error indicator.
        assert "Error" not in text or "eligible" in text.lower()

    def test_estimate_patient_cost_runs_to_completion(
        self, patient_server: str, page: Page,
    ) -> None:
        _open(page, patient_server, "eligibility", "estimate_patient_cost")
        form = page.locator(
            ".speks-playground-form[data-function='estimate_patient_cost']"
        )
        form.locator("input[name='patient_id']").fill("P-001")
        form.locator("input[name='service_code']").fill("diagnostic-imaging")
        form.locator("input[name='billed_amount']").fill("250")
        form.locator(".speks-run-btn").click()
        text = self._wait_result(page, "estimate_patient_cost")
        assert "patient_responsibility" in text or "covered" in text.lower()

    def test_evaluate_prior_auth_runs_to_completion(
        self, patient_server: str, page: Page,
    ) -> None:
        _open(page, patient_server, "prior-auth", "evaluate_prior_auth")
        form = page.locator(
            ".speks-playground-form[data-function='evaluate_prior_auth']"
        )
        form.locator("input[name='patient_id']").fill("P-001")
        form.locator("input[name='procedure_code']").fill("MRI-001")
        form.locator(".speks-run-btn").click()
        text = self._wait_result(page, "evaluate_prior_auth")
        # Status must be set (APPROVED / DENIED / etc.).
        assert "status" in text.lower()

    def test_naive_string_in_list_field_does_not_crash(
        self, patient_server: str, page: Page,
    ) -> None:
        """User types a single word in a ``list[str]`` mock field.

        The previous behaviour returned a raw dict to the business code,
        causing ``'dict' object has no attribute 'member_id'``.  After
        the per-field coercion fix, invalid fields fall back to their
        default and the run completes normally.
        """
        _open(page, patient_server, "eligibility", "check_eligibility")
        form = page.locator(
            ".speks-playground-form[data-function='check_eligibility']"
        )
        form.locator("input[name='patient_id']").fill("P-001")
        form.locator("input[name='service_code']").fill("preventive-exam")
        # Mimic the user clearing the JSON default and typing a single
        # word — the exact gesture that used to crash.
        conditions_input = form.locator(
            "input.speks-mock-pydantic-input"
            "[data-service='EHR.fetch_patient_record'][data-field='conditions']"
        )
        conditions_input.fill("hypertension")
        form.locator(".speks-run-btn").click()
        text = self._wait_result(page, "check_eligibility")
        # The run must succeed (no AttributeError surfaced as JSON error).
        assert "'dict' object has no attribute" not in text
        assert "eligible" in text.lower()
