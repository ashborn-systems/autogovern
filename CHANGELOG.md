# Changelog

All notable changes to auto-govern are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [0.1.0] - 2026-07-18

### Added
- CLI with seven commands: init, scan, generate, diff, check, explain, hook
- AgentProfile scanner with A2A AgentCard construction and provenance tracking
- Framework pack loader with section dependency graph
- Generation engine with incremental, idempotent regeneration
- Material change detection (heuristic, profile diff, semantic scoring)
- Vanilla mode: generate works without init, progressive enhancement
- Headless input: --profile flag on generate, check, diff
- Public library API: scan, generate_docs, check, load_profile
- Run manifests written on every command
- Forge-aware CI writers (GitHub, Forgejo, Bitbucket, generic)
- Pre-commit hook (warning-only, never blocks)
- GitHub Action wrapping check and generate
- Install scripts for POSIX and Windows
