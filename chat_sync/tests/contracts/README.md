# Chat AI contract fixtures

`schemas/` is the v1 wire contract. `valid/` and `invalid/` are deterministic
examples consumed by server, Web, and iOS contract tests. Unknown event types
and block kinds are intentionally included in `valid/` because forward
compatibility is part of the contract.

The files contain fake UUIDs and UTC timestamps only. They must never contain
Provider keys, access tokens, full prompts, medical source text, or raw
HealthKit samples.

