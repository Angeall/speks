<p align="center">
  <img src="logo.svg" alt="Speks logo" width="200">
</p>

# Speks

**Interactive Functional Analysis Generator** — turn pseudo-code and Markdown specifications into a live, testable documentation website.

[![CI](https://github.com/Angeall/speks/actions/workflows/ci.yml/badge.svg)](https://github.com/Angeall/speks/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-yellow.svg)](LICENSE)
[![Website](https://img.shields.io/badge/Website-Speks-orange)](https://speks.cloud)

## Why Speks?

Business rules live in code, but stakeholders read documentation. Speks bridges the gap:

- **Write** business rules as Python pseudo-code with built-in mocking for external services
- **Document** them in Markdown with special tags that embed live code, contracts, and diagrams
- **Generate** an interactive website where anyone can read, understand, and **test** every rule

No more stale specs. No more "the doc says X but the code does Y". Your documentation **is** the executable specification.

## Quick Start

```bash
pip install pyspeks
speks init my-project
cd my-project
speks serve
```

Open [http://localhost:8000](http://localhost:8000) to see your interactive documentation.

## What You Get

Write business rules as Python pseudo-code:

```python
from speks import ExternalService, MockResponse

class CheckClientBalance(ExternalService):
    def execute(self, client_id: str) -> float:
        pass  # real HTTP call in production

    def mock(self, client_id: str) -> MockResponse:
        return MockResponse(data=1500.0)

def evaluate_credit(client_id: str, amount: float) -> bool:
    balance = CheckClientBalance().call(client_id)
    return balance > amount
```

Then document them in Markdown with special tags:

```markdown
## Credit Evaluation
@[contract](src/rules.py:evaluate_credit)
@[code](src/rules.py:evaluate_credit)
@[playground](src/rules.py:evaluate_credit)
@[sequence](src/rules.py:evaluate_credit)
@[dependencies](src/)
@[mermaid](diagrams/flow.mmd)
@[plantuml](diagrams/sequence.puml)
```

Speks generates a live website where stakeholders can **read, understand, and test** every business rule — with auto-generated dependency graphs and sequence diagrams.

## Features

- **Interactive Playground** — Each documented function gets an auto-generated form to test it live in the browser
- **Mocking Engine** — External services are auto-mocked; users can override mock values and simulate errors
- **Custom Markdown Tags** — `@[code]`, `@[playground]`, `@[contract]`, `@[dependencies]`, `@[sequence]`, `@[mermaid]`, `@[plantuml]`
- **Auto-generated Diagrams** — Dependency graphs and sequence diagrams derived from your code via static analysis
- **Test Case Management** — Save, replay, and validate test scenarios directly from the documentation
- **Standalone Binaries** — Distribute as a single executable (Windows, macOS, Linux) — no Python required

## Markdown Tags Reference

| Tag | Description |
|-----|-------------|
| `@[code](src/file.py:func)` | Embed function source code with syntax highlighting |
| `@[playground](src/file.py:func)` | Interactive form to test the function live |
| `@[contract](src/file.py:func)` | Function signature as a readable table |
| `@[dependencies](src/)` | Auto-generated dependency graph (Mermaid) |
| `@[sequence](src/file.py:func)` | Auto-generated sequence diagram |
| `@[mermaid](diagrams/flow.mmd)` | Embed a Mermaid diagram from file |
| `@[plantuml](diagrams/file.puml)` | Embed a PlantUML diagram |

## Project Layout

```
speks/               # The generator library & CLI
  core/              # Markdown parser, code extractor, dependency & sequence analysis
  engine/            # Mocking system, external service base classes
  web/               # Site builder, dev server (FastAPI)
  mkdocs_plugins/    # MkDocs plugins for each tag type
  i18n/              # Internationalization (en, fr)
  cli.py             # CLI entry point (init, serve)
```

## User Workspace

After `speks init`, a workspace is created:

```
my-project/
  src/               # Python pseudo-code (business rules)
  docs/              # Markdown documentation
  diagrams/          # PlantUML diagrams
  testcases/         # Saved test scenarios (JSON)
  speks.toml         # Project configuration
  mkdocs.yml         # MkDocs configuration
```

## Examples

See the [`examples/`](examples/) directory for complete projects across different industries:

| Example | Domain | Demonstrates |
|---------|--------|-------------|
| [Credit Evaluation](examples/credit-evaluation/) | Banking | Core features, mocking, error handling, sequence diagrams |
| [Order Processing](examples/order-processing/) | E-commerce | Multi-step workflows, pricing rules, inventory checks |
| [Patient Eligibility](examples/patient-eligibility/) | Healthcare | Compliance rules, multi-service orchestration |
| [Shipping Calculator](examples/shipping-calculator/) | Logistics | Decision trees, zone-based calculations |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
