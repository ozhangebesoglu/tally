# CLAUDE.md

This file provides guidance for Claude when working on this codebase.

## Testing Requirements

- **Always add tests** for new features in the analyzer. Tests go in `tests/test_analyzer.py`.
- **Always use the Playwright MCP** to test any changes to the HTML report. Generate a report with test data and verify the UI works correctly.

## Development

- **Always use `uv run`** to run tally during development. Example:
  ```bash
  uv run python -m tally --help
  ```

## Releases

- **Always use the GitHub workflow** for releasing new versions. Do not create releases manually.

## Commit Messages

- **Always use `Fixes #<issue>` syntax** when fixing GitHub issues to auto-close them. Example:
  ```
  Fix tooltip display on mobile

  Fixes #42
  ```

## Configuration Changes

- **Always make backwards compatible changes** to `settings.yaml` format. Existing user configs should continue to work without modification.
- If a breaking change is necessary, implement **automatic migration** in `config_loader.py` to convert old format to new format.
- Document new configuration options in `config/settings.yaml.example`.

## Error Messages & Diagnostics

- **Error messages should be self-descriptive** and guide users/agents on what to do next.
- Include specific suggestions in error messages (e.g., "Add: columns:\n  description: \"{field} ...\"").
- **Use `tally diag`** to diagnose configuration issues. It shows:
  - Config directory and settings file status
  - Data sources with parsed format details (columns, custom captures, templates)
  - Merchant rules (baseline + user rules)
- The tool should be self-descriptive enough that users can fix issues without external documentation.

## Project Structure

- `src/tally/` - Main source code
  - `analyzer.py` - Core analysis and HTML report generation
  - `merchant_utils.py` - Merchant normalization and rules
  - `format_parser.py` - CSV format parsing
  - `config_loader.py` - Configuration loading and migration
- `tests/` - Test files
- `docs/` - Marketing website (GitHub Pages)
- `config/` - Example configuration files
