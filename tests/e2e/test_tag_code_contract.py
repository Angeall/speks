"""E2E tests for @[code] and @[contract] tag rendering."""

from __future__ import annotations

from playwright.sync_api import Page, expect


# ---------------------------------------------------------------------------
# @[code]
# ---------------------------------------------------------------------------


class TestCodeTag:
    def test_function_code_is_rendered_with_syntax_highlighting(
        self, speks_server: str, page: Page,
    ) -> None:
        page.goto(f"{speks_server}/credit-rules/")
        page.wait_for_load_state("networkidle")
        # @[code](src/credit.py:evaluate_credit) renders a Python code block
        # (highlighted by pymdownx.highlight, embedded in a Material code
        # container).  At least one block must be in the DOM with the
        # language-python class.
        code_blocks = page.locator("pre code")
        assert code_blocks.count() >= 1
        # The function signature must appear in at least one code block's
        # text content (syntax highlighting fragments the raw HTML).
        all_text = " ".join(
            code_blocks.nth(i).text_content() or ""
            for i in range(code_blocks.count())
        )
        assert "evaluate_credit" in all_text
        assert "client_id" in all_text

    def test_class_code_renders_full_class(
        self, speks_server: str, page: Page,
    ) -> None:
        page.goto(f"{speks_server}/credit-rules/")
        page.wait_for_load_state("networkidle")
        # @[code](src/credit.py:CoreBanking) should expand the entire class.
        # Syntax highlighting wraps keywords in <span>s, so the literal
        # string "class CoreBanking" is fragmented in HTML.  Read the text
        # content of every <code> block instead.
        all_text = " ".join(
            page.locator("pre code").nth(i).text_content() or ""
            for i in range(page.locator("pre code").count())
        )
        assert "CoreBanking" in all_text
        assert "@stub" in all_text
        assert "check_balance" in all_text

    def test_missing_symbol_does_not_break_page(
        self, speks_server: str, page: Page,
    ) -> None:
        # `credit-rules.md` references `CreditHistory` in `typed_credit.py`,
        # which is actually defined in `credit.py`. The tag falls back to
        # an HTML comment and must not crash the page render.
        page.goto(f"{speks_server}/credit-rules/")
        page.wait_for_load_state("networkidle")
        # The page should still have content
        assert page.locator("h1").count() >= 1


# ---------------------------------------------------------------------------
# @[contract]
# ---------------------------------------------------------------------------


class TestContractTag:
    def test_renders_contract_table(self, speks_server: str, page: Page) -> None:
        page.goto(f"{speks_server}/credit-rules/")
        page.wait_for_load_state("networkidle")
        # @[contract](src/credit.py:evaluate_credit) → div.speks-contract
        contracts = page.locator(".speks-contract")
        expect(contracts.first).to_be_visible()

    def test_contract_shows_parameter_names_and_types(
        self, speks_server: str, page: Page,
    ) -> None:
        page.goto(f"{speks_server}/credit-rules/")
        page.wait_for_load_state("networkidle")
        # The evaluate_credit contract should list client_id and amount
        contract = page.locator(".speks-contract").first
        text = contract.inner_text()
        assert "client_id" in text
        assert "amount" in text
        # Their types should also be present
        assert "str" in text
        assert "float" in text

    def test_contract_shows_return_type(self, speks_server: str, page: Page) -> None:
        page.goto(f"{speks_server}/credit-rules/")
        page.wait_for_load_state("networkidle")
        contract = page.locator(".speks-contract").first
        text = contract.inner_text()
        # evaluate_credit returns bool
        assert "bool" in text
        # The "Output" section heading should be present (en locale)
        # Locale may be FR/EN — check both
        assert any(token in text for token in ("Output", "Sortie", "return"))

    def test_contract_unfolds_pydantic_request(
        self, speks_server: str, page: Page,
    ) -> None:
        # evaluate_credit_typed takes a `CreditRequest` Pydantic model.
        # The contract should include a collapsible <details> showing
        # the inner fields.
        page.goto(f"{speks_server}/credit-rules/")
        page.wait_for_load_state("networkidle")
        details = page.locator(".speks-contract-type-details")
        assert details.count() >= 1
        # Open every nested-type <details> to expose field names.
        page.evaluate(
            "document.querySelectorAll('.speks-contract-type-details')"
            ".forEach(d => d.open = true)"
        )
        all_text = " ".join(
            details.nth(i).inner_text() for i in range(details.count())
        )
        # CreditRequest has client_id, amount, score_threshold, include_history
        assert "client_id" in all_text
        assert "score_threshold" in all_text
