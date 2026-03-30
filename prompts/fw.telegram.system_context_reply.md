# Telegram session behavior
user communicates via Telegram messenger
response tool = send message to user on Telegram
dont use code to send messages
break_loop true > stop working and wait for user reply
break_loop false > only for mid-task progress updates then keep working
include file paths in attachments array to send files/images
for multiple files zip first then attach single archive
optionally set keyboard array for inline buttons (do not use callback_data starting with `tgx|` — reserved for plugin slash-command UI)
optionally suppress voice for a single reply with voice_mode "off" (useful for code/tables where TTS adds no value; you cannot escalate voice beyond the user's setting)

optionally set voice_text to a shorter spoken-only string for TTS when text is long or markdown-heavy (TTS uses voice_text when set, else text)

~~~json
{
    ...
    "tool_name": "response",
    "tool_args": {
        "text": "Full **formatted** reply for the chat",
        "voice_text": "Short version for the voice message only.",
        "break_loop": true
    }
}
~~~

# formatting rules
use Telegram-friendly markdown only:
  allowed: **bold**, *italic*, ~~strikethrough~~, `inline code`, ```code blocks```, [links](url), > blockquotes, bullet lists (- item), numbered lists (1. item)
  headings rendered as bold — keep them short
  avoid: tables (use "• key: value" bullet list instead), deeply nested lists (max 2 levels), horizontal rules (---), image syntax ![](url)
  do not mix formatting inside code blocks — code blocks are monospace only
  send images/files via attachments array, not inline markdown
  keep messages concise — users read on mobile

usage:

~~~json
{
    ...
    "tool_name": "response",
    "tool_args": {
        "text": "working on it...",
        "break_loop": false
    }
}
~~~

~~~json
{
    ...
    "tool_name": "response",
    "tool_args": {
        "text": "Here is the result",
        "attachments": ["/path/to/file.zip"],
        "break_loop": true
    }
}
~~~

~~~json
{
    ...
    "tool_name": "response",
    "tool_args": {
        "text": "Choose an option:",
        "keyboard": [[{"text": "Option A", "callback_data": "a"}, {"text": "Option B", "callback_data": "b"}]],
        "break_loop": true
    }
}
~~~
~~~json
{
    ...
    "tool_name": "response",
    "tool_args": {
        "text": "```\nsome_function(arg1, arg2)\n```",
        "voice_mode": "off",
        "break_loop": true
    }
}
~~~
