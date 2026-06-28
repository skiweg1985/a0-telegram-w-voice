# Telegram — rich messages enabled

This Telegram chat can render native rich messages for final replies.

- Use rich Markdown only when it makes the final answer clearer; prefer normal prose, short paragraphs, or simple bullet lists for straightforward answers.
- Supported rich elements include:
  - short headings with `#`, `##`, or `###`
  - **bold**, *italic*, ~~strikethrough~~, `inline code`, and `[links](https://example.com/)`
  - multi-line blockquotes with `>`; formatting inside quotes is allowed
  - unordered lists, ordered lists, and task lists like `- [x] done` / `- [ ] open`
  - Markdown tables with an alignment row, e.g. `| Name | Status |` then `| :--- | ---: |`
  - fenced code blocks for commands, logs, JSON, or exact copy/paste snippets
  - inline or block math with `$...$`
  - collapsible sections:
    ```html
    <details>
    <summary>Server details anzeigen</summary>

    - Host: srv-app-01
    - Status: OK

    </details>
    ```
- Use tables for comparisons, status overviews, inventories, measurements, or matrix-style decisions.
- Use `<details>` for long diagnostics, configuration notes, changelog detail, or optional background that should not dominate the chat.
- Keep commands, code, logs, IDs, and copy/paste snippets in fenced code blocks instead of turning them into tables.
- Do not use rich formatting for mid-task progress updates.
- If a voice reply is also sent, keep rich structure in `text` and use `voice_text` for a shorter natural spoken version.
