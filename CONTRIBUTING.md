# Contributing to Speks

Thank you for your interest in contributing to Speks!

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/your-org/speks.git
   cd speks
   ```

2. Create a virtual environment and install in dev mode:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

3. Install pre-commit hooks:
   ```bash
   pip install pre-commit
   pre-commit install
   ```

## Running checks

```bash
# Tests
python -m pytest tests/ -q

# Type checking
python -m mypy speks/

# Tests with coverage
python -m pytest tests/ --cov=speks --cov-report=term-missing
```

## Pull Request Guidelines

- Keep PRs focused on a single change.
- Ensure all tests pass and mypy reports no errors.
- Add tests for new functionality.
- Write clear commit messages describing *what* and *why*.

## Reporting Issues

Open a GitHub issue with:
- A clear title and description.
- Steps to reproduce (if applicable).
- Python version and OS.

## Code Style

- We use **Ruff** for linting and formatting.
- Type hints are enforced with `mypy --strict`.
- All modules use `from __future__ import annotations`.
