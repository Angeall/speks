# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [0.1.2] — 2026-04-02

### Fixed

- Fixed display of nested pydantic models in contracts

## [0.1.1] — 2026-04-01

### Added

- Read more comments to document function in website
- Better rendering of nested Pydantic models in playground
- Fullscreen mode for website for better readability

### Fixed

- Fixed `speks serve --develop` to avoid infinite loop

## [0.1.0] — 2026-03-18

### Added

- Initial release of Speks.
- CLI commands: `speks init` (workspace scaffolding) and `speks serve` (dev server).
- `speks serve --develop` flag for file watching and automatic rebuild on changes.
- `speks serve --revisions` flag to control the number of git revisions built.
- Seven custom Markdown tags: `@[code]`, `@[contract]`, `@[playground]`, `@[sequence]`, `@[dependencies]`, `@[plantuml]`, `@[mermaid]`.
- MkDocs plugins: `speks-tags`, `speks-playground`, `speks-dependencies`, `speks-sequence`, `speks-versioning`, `speks-plantuml`.
- Interactive playground widgets with mock overrides and error injection.
- Mocking engine with `ExternalService` / `MockResponse` / `MockErrorResponse` primitives and call tracing.
- Contract table rendering (inputs / outputs) from function signatures and Pydantic models.
- Auto-generated sequence diagrams from Python AST analysis (service calls, conditionals).
- Static dependency analyzer with Mermaid flowchart generation.
- Test case management: save, replay, bulk replay with pass/fail validation.
- Git-based multi-version documentation with revision selector and side-by-side diff viewer.
- PlantUML integration via configurable server with collapsible source display.
- Standalone HTML renderer for Markdown files with embedded CSS.
- FastAPI dev server with endpoints for function execution, test cases, version diffing.
- Internationalization support (English and French).
- Example projects: credit-evaluation, order-processing, patient-eligibility, shipping-calculator.
