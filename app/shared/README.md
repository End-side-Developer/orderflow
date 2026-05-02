# Shared Contracts

This directory holds cross-service schemas and reference contracts.

## Contents

- contracts/: API contract snapshots and generated clients.
- schemas/: shared payload schemas and event structures.

## Rules

- No service-specific runtime logic.
- Version contract changes in small increments.
- Backward-compatible updates are preferred unless intentionally breaking.
