"""Macro/catalyst awareness layer.

An out-of-band background worker calls Perplexity on a schedule and writes
structured events/catalysts/regime rows to SQLite. The trading hot path
(scorer, profile, strategy) reads from SQLite only — no LLM or network calls
inside on_trading_iteration. The layer is fail-safe: stale or missing data
returns the same behavior as the pre-macro baseline.

See: docs/we-are-adding-a-gleaming-giraffe.md (plan file)
"""
