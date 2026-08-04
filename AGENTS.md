# Repository Guidelines

This repository is a dual-momentum signal system for Chinese equity indices (创业板指 vs. 中证红利). A Streamlit dashboard compares N-day momentum between the two indices, holds the stronger one, or goes to cash when both are below the risk-free rate.

## Project Structure & Module Organization

- `app.py` — Streamlit entry point; UI tabs, charts, and backtest display.
- `strategy.py` — momentum calculation and signal generation (vectorized and real-time variants).
- `data_loader.py` — market data fetching via akshare, cleaning, caching, and demo-data fallback.
- `backtester.py` — T+1 backtest engine and statistics (return, drawdown, Sharpe, win rate).
- `config.py` — global strategy parameters: index codes, momentum window, risk-free rate, cooldown.
- `tests/` — pytest suite: `test_strategy.py`, `test_backtester.py`.
- `docs/superpowers/` — design specs (`specs/`) and implementation plans (`plans/`).

## Build, Test, and Development Commands

There is no build step; this is pure Python.

- `pip install -r requirements.txt` — install runtime and test dependencies.
- `streamlit run app.py` — launch the dashboard locally.
- `pytest` — run the full test suite.
- `pytest tests/test_strategy.py` — run a single test module.

## Coding Style & Naming Conventions

- Follow PEP 8: 4-space indentation, two blank lines between top-level definitions.
- Use type hints on function signatures (e.g., `pd.Series`, `DataFrame`).
- Name functions and modules in `snake_case`; constants in `UPPER_SNAKE_CASE`.
- Docstrings describe `Args`/`Returns`; existing docstrings are in Chinese, so match the language of the file you edit.
- No linter or formatter is configured; keep changes consistent with surrounding code.

## Testing Guidelines

- Framework: pytest (declared in `requirements.txt`).
- Place tests in `tests/test_*.py` and name test functions `test_<behavior>`.
- Cover signal edge cases (insufficient data/NaN windows, tie-breaking) and T+1 execution to prevent look-ahead bias.
- Run `pytest` before committing. No coverage threshold is enforced.

## Commit & Pull Request Guidelines

- Use Conventional Commits: `feat:`, `fix:`, `chore:`, `docs:`. Example from history: `feat: backtest engine with T+1 execution and tests`.
- Keep each commit scoped to one logical change and add context when the motivation is not obvious.
- For PRs, describe what changed and why, link the relevant spec or issue, and report test results.

## Agent-Specific Instructions

- For significant changes, follow the `docs/superpowers` workflow: update the plan in `plans/` before implementing, then the spec in `specs/` if behavior changes.
- Never commit credentials or local data; market data is fetched at runtime.
