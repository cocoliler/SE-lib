# Acceptance Evidence

`scripts/verify_all.ps1` writes each run to `evidence/runs/<timestamp>/`.
Generated runs are local and ignored by Git.

Each run contains:

- `summary.md`: human-readable status and command results
- `summary.json`: machine-readable execution record
- `logs/`: raw command, backend and browser logs
- `runtime/`: isolated SQLite data used by the HTTP test
- `browser-*.png`: specification, workflow and dark-theme UI evidence
- `p0-state.json`: IDs and hashes used to verify restart persistence
- `real-acceptance*.json`: REAL run, usage, timing, proposal and review evidence

Do not place API keys, `.env` files, user documents or downloaded evidence in this directory.
The summary intentionally records TEST-only execution; REAL acceptance must be recorded
separately with its model, prompt version, usage and human review.
