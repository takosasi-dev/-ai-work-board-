---
name: ai-work-board
description: Read and update the AI Work Board (board.json), the user's shared progress board for work requested of each AI (Claude / Muse / Gemini). Use when the user mentions AI Work Board, board.json, BOARD.md, 「ボード」「進捗ボード」「作業ボード」, asks what has been requested of you, asks you to record or report progress on a task, or pastes a request copied from the board (「依頼文をコピー」 text with an id).
---

# AI Work Board

The user tracks what they asked each AI to do, and how far each task has got, in one `board.json`.
A desktop GUI shows it and reloads it every 2 seconds, so whatever you write appears on the user's screen.
Other AIs and the GUI write to the same file, so never rewrite the whole board from memory.

## How to read and write (use the first one that is available)

1. **MCP tools** (server name `ai-work-board`): `list_tasks`, `get_task`, `add_task`, `update_task`, `complete_task`.
   They re-read the file on every call and change only the one task, so they are always safe.
2. **CLI**, when `ai_work_board.py` is available:
   ```text
   python ai_work_board.py --data <board.json> --list
   python ai_work_board.py --data <board.json> --add "タイトル" --ai Claude --status in_progress --request "依頼"
   python ai_work_board.py --data <board.json> --update <id> --progress 60 --status in_progress --notes "経緯"
   python ai_work_board.py --data <board.json> --done <id>
   ```
   `--add` and `--update` print the task id.
3. **Edit `board.json` directly** only when neither is available. Read the file immediately before writing,
   change only the target task, keep every other task and key exactly as it was, and write valid UTF-8 JSON.

If you do not know where `board.json` is, ask the user. It sits next to `AIWorkBoard.exe` (or `ai_work_board.py`)
unless the `AI_WORK_BOARD_DATA` environment variable points elsewhere. `BOARD.md` next to it is a read-only summary.

## Task fields

| Field | Meaning |
|---|---|
| `id` | 8 hex chars. A unique prefix is accepted by the tools and the CLI |
| `title` | Short title |
| `ai` | Who the task is for: `Claude`, `Muse`, `Gemini`, or another name |
| `status` | `todo` 未着手 / `in_progress` 進行中 / `waiting` 待ち / `blocked` 停滞 / `done` 完了 |
| `progress` | 0-100. `done` always means 100 |
| `request` | What the user wants this AI to do |
| `notes` | History, decisions, things to watch out for |
| `created` / `updated` | UTC, `YYYY-MM-DDTHH:MM:SSZ`. Set `updated` when editing the file directly |

## Rules

- Start by listing the tasks assigned to you (`ai` = your name) and read their `request` and `notes`.
- Work on what the user asked. When a task is pasted with an id, update that id; do not create a duplicate.
- Update `status` and `progress` when you make real progress, not only at the end. Use `blocked` or `waiting`
  with a one-line reason in `notes` when you are stuck or need the user.
- Add a new task only for new work the user asked for. Do not delete tasks or edit other AIs' tasks.
- Keep `notes` short and factual. Append to them rather than replacing what the user wrote.
- Never put people's names, email addresses, passwords or API keys into the board.
