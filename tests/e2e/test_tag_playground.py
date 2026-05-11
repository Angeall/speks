"""E2E tests for the interactive @[playground] tag.

Covers the full user flow that no unit test can validate:
* button enable/disable as required inputs are filled
* form submission via ``POST /api/run`` and result rendering
* Pydantic mock overrides (incl. ``list[str]`` JSON coercion)
* error simulation via the per-stub checkbox
"""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect


def _open_playground(page: Page, base: str, page_path: str, func: str) -> None:
    """Navigate to a docs page and open the playground for *func*."""
    page.goto(f"{base}/{page_path}/")
    page.wait_for_load_state("networkidle")
    widget = page.locator(f".speks-playground-widget[data-function='{func}']")
    # The widget is a <details> collapsed by default — open it.
    widget.evaluate("el => el.open = true")
    # Also open the inner mock-config <details> just in case.
    widget.locator(".speks-mock-config").evaluate_all(
        "els => els.forEach(e => e.open = true)"
    )


# ---------------------------------------------------------------------------
# Button enable/disable behaviour
# ---------------------------------------------------------------------------


class TestRunButtonState:
    def test_button_disabled_when_required_fields_empty(
        self, speks_server: str, page: Page,
    ) -> None:
        _open_playground(page, speks_server, "credit-rules", "evaluate_credit")
        form = page.locator(
            ".speks-playground-form[data-function='evaluate_credit']"
        )
        btn = form.locator(".speks-run-btn")
        expect(btn).to_be_disabled()

    def test_button_enables_when_all_required_filled(
        self, speks_server: str, page: Page,
    ) -> None:
        _open_playground(page, speks_server, "credit-rules", "evaluate_credit")
        form = page.locator(
            ".speks-playground-form[data-function='evaluate_credit']"
        )
        form.locator("input[name='client_id']").fill("client-42")
        form.locator("input[name='amount']").fill("1000")
        btn = form.locator(".speks-run-btn")
        expect(btn).to_be_enabled()

    def test_button_only_blocked_by_primitive_params_not_nested_pydantic(
        self, speks_server: str, page: Page,
    ) -> None:
        # evaluate_premium_credit has a nested ClientProfile parameter with
        # 6 required structured inputs.  Filling only the top-level `amount`
        # must be enough to enable the button.
        _open_playground(
            page, speks_server, "credit-rules", "evaluate_premium_credit",
        )
        form = page.locator(
            ".speks-playground-form[data-function='evaluate_premium_credit']"
        )
        # Find the plain `amount` input (no data-path)
        form.locator("input[name='amount']").fill("500")
        btn = form.locator(".speks-run-btn")
        expect(btn).to_be_enabled()


# ---------------------------------------------------------------------------
# Run flow with default mock data
# ---------------------------------------------------------------------------


class TestRunDefaultMock:
    def test_clicking_run_executes_and_shows_result(
        self, speks_server: str, page: Page,
    ) -> None:
        _open_playground(page, speks_server, "credit-rules", "evaluate_credit")
        form = page.locator(
            ".speks-playground-form[data-function='evaluate_credit']"
        )
        form.locator("input[name='client_id']").fill("c1")
        form.locator("input[name='amount']").fill("1000")
        form.locator(".speks-run-btn").click()
        result = page.locator("#speks-result-evaluate_credit")
        expect(result).to_be_visible(timeout=5_000)
        # Default mock balance is 1500 > amount 1000 → result is true.
        expect(result).to_have_class(re.compile(r"\bsuccess\b"), timeout=5_000)
        assert "true" in (result.text_content() or "").lower()

    def test_call_log_shows_dotted_service_name(
        self, speks_server: str, page: Page,
    ) -> None:
        _open_playground(page, speks_server, "credit-rules", "evaluate_credit")
        form = page.locator(
            ".speks-playground-form[data-function='evaluate_credit']"
        )
        form.locator("input[name='client_id']").fill("c1")
        form.locator("input[name='amount']").fill("100")
        form.locator(".speks-run-btn").click()
        result = page.locator("#speks-result-evaluate_credit")
        expect(result).to_be_visible(timeout=5_000)
        text = result.text_content() or ""
        assert "CoreBanking.check_balance" in text


# ---------------------------------------------------------------------------
# Pydantic mock overrides
# ---------------------------------------------------------------------------


class TestMockOverrides:
    def test_overriding_pydantic_field_changes_result(
        self, speks_server: str, page: Page,
    ) -> None:
        # CoreBanking.check_balance default mock has balance=1500.
        # Override it to 100; with amount=500 → 100 < 500 → result false.
        _open_playground(page, speks_server, "credit-rules", "evaluate_credit")
        form = page.locator(
            ".speks-playground-form[data-function='evaluate_credit']"
        )
        form.locator("input[name='client_id']").fill("c1")
        form.locator("input[name='amount']").fill("500")
        # Modify the Pydantic mock field for `balance`.
        balance_input = form.locator(
            "input.speks-mock-pydantic-input"
            "[data-service='CoreBanking.check_balance'][data-field='balance']"
        )
        balance_input.fill("100")
        form.locator(".speks-run-btn").click()
        result = page.locator("#speks-result-evaluate_credit")
        expect(result).to_be_visible(timeout=5_000)
        text = (result.text_content() or "").lower()
        # The function returns False when balance <= amount.
        assert "false" in text or '"result": false' in text


# ---------------------------------------------------------------------------
# Error simulation (per-stub error checkbox)
# ---------------------------------------------------------------------------


class TestErrorSimulation:
    def test_checking_error_box_raises_serviceerror_in_call_log(
        self, speks_server: str, page: Page,
    ) -> None:
        _open_playground(page, speks_server, "credit-rules", "evaluate_credit")
        form = page.locator(
            ".speks-playground-form[data-function='evaluate_credit']"
        )
        form.locator("input[name='client_id']").fill("c1")
        form.locator("input[name='amount']").fill("100")
        # Tick the error simulation checkbox for the stub.
        err_box = form.locator(
            "input.speks-error-checkbox"
            "[data-service='CoreBanking.check_balance']"
        )
        err_box.check()
        form.locator(".speks-run-btn").click()
        result = page.locator("#speks-result-evaluate_credit")
        expect(result).to_be_visible(timeout=5_000)
        text = result.text_content() or ""
        # The business rule catches ServiceError and returns False.
        # The call log must record the error.
        assert "CLIENT_NOT_FOUND" in text or "error_code" in text


# ---------------------------------------------------------------------------
# Test cases save / replay
# ---------------------------------------------------------------------------


class TestTestCases:
    def test_save_button_disabled_until_first_run(
        self, speks_server: str, page: Page,
    ) -> None:
        _open_playground(page, speks_server, "credit-rules", "evaluate_credit")
        widget = page.locator(
            ".speks-playground-widget[data-function='evaluate_credit']"
        )
        save_btn = widget.locator(".speks-tc-save-btn")
        expect(save_btn).to_be_disabled()

    def test_save_button_enables_after_successful_run(
        self, speks_server: str, page: Page,
    ) -> None:
        _open_playground(page, speks_server, "credit-rules", "evaluate_credit")
        form = page.locator(
            ".speks-playground-form[data-function='evaluate_credit']"
        )
        form.locator("input[name='client_id']").fill("c1")
        form.locator("input[name='amount']").fill("100")
        form.locator(".speks-run-btn").click()
        page.wait_for_function(
            "() => document.querySelector('#speks-result-evaluate_credit')"
            "        ?.classList.contains('success')",
            timeout=5_000,
        )
        save_btn = page.locator(
            ".speks-playground-widget[data-function='evaluate_credit']"
            " .speks-tc-save-btn"
        )
        expect(save_btn).to_be_enabled()
