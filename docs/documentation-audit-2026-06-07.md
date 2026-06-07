# Documentation Audit — 2026-06-07

## Scope

Reviewed repository documentation and documentation-adjacent text against the current codebase:

- `README.md`
- `docs/CHANGELOG.md`
- `docs/troubleshooting-tts.md`
- `planning/coordination/WORKLOG.md`
- `planning/telegram-next-level-feature-plan.md`
- `planning/telegram-ux-enhancements-plan.md`
- `prompts/*.md`
- `requirements.txt`

Code/config surfaces used as source of truth:

- `plugin.yaml`
- `default_config.yaml`
- `helpers/command_registry.py`
- `helpers/handler.py`
- `helpers/speech.py`
- `helpers/detail_status.py`
- `helpers/constants.py`
- `extensions/python/job_loop/_10_telegram_bot.py`
- `webui/config.html`
- `webui/telegram-config-store.js`
- test coverage under `tests/`

## Files modified

- `README.md`
  - Clarified `/shortcut` no-argument behavior and inline buttons.
  - Clarified quick actions now include the More menu actions (`Shorter`, `Longer`, `To voice`, `Back`) and the voice-only `Show text` button.
  - Clarified `/session` details summary is generated fresh via the utility LLM when opening details.
  - Removed the unverified `packaging/plugin-index/index.yaml.example` reference because that path is not present in this repository.
- `helpers/command_registry.py`
  - Updated `/shortcut` help text so `/help` matches implementation: no argument shows inline buttons.
- `docs/CHANGELOG.md`
  - Added a note that older entries are historical release notes and may mention removed commands/features.
  - Kept historical `/tts`, `/alsotext`, `/speakstyle`, and intermediate quick-action references as history, not current instructions.
- `docs/documentation-audit-2026-06-07.md`
  - Added this audit report.

## Obsolete or stale content handled

- `README.md` previously referenced `packaging/plugin-index/index.yaml.example`; no such path exists in this repository. Removed and replaced with a manual-review note about Plugin Index publishing.
- `README.md` previously under-described quick actions by focusing on `Show text`; updated to cover the current More-menu actions.
- `README.md` and `docs/CHANGELOG.md` now consistently describe `/shortcut` no-arg inline buttons and utility-LLM-generated session summaries.

## Content intentionally left as historical

The planning and coordination documents are already marked as historical/non-normative. They contain superseded terms and commands (`/tts`, `/alsotext`, `More technical`, `Step by step`) as implementation history. They were not rewritten because changing historical logs would make the record less accurate.

- `planning/coordination/WORKLOG.md`
- `planning/telegram-next-level-feature-plan.md`
- `planning/telegram-ux-enhancements-plan.md`

`docs/CHANGELOG.md` also contains older release entries for removed features. A note was added near the top so readers understand that older entries are chronological history and current behavior is documented in `README.md` plus the Unreleased section.

## Remaining documentation gaps

- Plugin Index publishing instructions could not be fully verified from this repository. The old concrete path was removed; maintainers should add verified upstream/index instructions if they want this repo to document publishing.
- External Agent Zero skill links in `README.md` (`a0-create-plugin`, `a0-manage-plugin`) were not verified from repository contents alone because they point to upstream Agent Zero docs. They are left for manual review.
- No ADR directory exists in this repository. No ADR-specific updates were possible.
- There is no automated docs-link checker configured in the repository. Markdown syntax and references were manually reviewed; external links remain manual-review items.

## Validation

- `pytest -q tests` → `150 passed`
- `python3 -m py_compile helpers/handler.py helpers/command_registry.py extensions/python/job_loop/_10_telegram_bot.py` → ok
