# Latest Release: v3.3.6

**Release Date:** April 12, 2026

LedgerMind v3.3.6 is a major performance and security update that eliminates N+1 query bottlenecks, hardens subprocess execution, and enhances the CLI experience with rich visual feedback.

## 🚀 Key Improvements

- **Massive Performance Gains** — Resolved N+1 queries across enrichment facade, search, metadata fetching, and event processing. SQLite batch operations now use chunking and json_each optimization.
- **Critical Security Fixes** — Patched multiple subprocess execution vulnerabilities (CRITICAL, HIGH, MEDIUM), added missing authentication to MCP tools and admin endpoints.
- **Enhanced CLI Experience** — Rich console formatting for standardized output, clickable status bar with error states, and output channel replacing intrusive error popups.
- **Command Palette** — New "show output" command for easier access to processing results.

[View full v3.3.6 changelog](./v3.3.6.md)
