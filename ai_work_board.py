#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Work Board - 各AIとの作業進捗と依頼を一元管理するGUIツール

対象AI: Claude / Muse / Gemini (追加可能)
データ: board.json (人間にもAIにも読める素直なJSON)
AI連携: このファイルと同じフォルダの board.json を読めば進捗が分かり、
  書き込めばGUIに数秒で反映される。CLIでも同じ操作ができる:
    python ai_work_board.py --list
    python ai_work_board.py --add "タイトル" --ai Muse --status in_progress
    python ai_work_board.py --update <id> --progress 60 --status in_progress
    python ai_work_board.py --done <id>
    python ai_work_board.py --export
  MCP サーバーとしても動く (Claude Code / Claude Desktop / Gemini CLI などに道具として渡す):
    python ai_work_board.py --mcp
GUIは標準ライブラリ(tkinter)のみで動く。WindowsでPyInstaller化して .exe にできる。
"""

import argparse
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone

VERSION = "0.4.0"
DEFAULT_AIS = ["Claude", "Muse", "Gemini"]
STATUSES = ["todo", "in_progress", "waiting", "blocked", "done"]
STATUS_LABEL = {
    "todo": "未着手",
    "in_progress": "進行中",
    "waiting": "待ち",
    "blocked": "停滞",
    "done": "完了",
}
LABEL_STATUS = {v: k for k, v in STATUS_LABEL.items()}
TASK_FIELDS = ("title", "ai", "status", "progress", "request", "notes")


def base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def data_path(custom=None):
    if custom:
        return custom
    env = os.environ.get("AI_WORK_BOARD_DATA")
    if env:
        return env
    return os.path.join(base_dir(), "board.json")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sample_data():
    return {
        "version": 1,
        "ais": list(DEFAULT_AIS),
        "tasks": [
            {
                "id": "sample-claude-1",
                "title": "サンプル: Claudeへの依頼タスク",
                "ai": "Claude",
                "status": "in_progress",
                "progress": 40,
                "request": "ここにClaudeへお願いしたい作業を書く",
                "notes": "サンプルです。削除して使ってください。",
                "created": now_iso(),
                "updated": now_iso(),
            },
            {
                "id": "sample-muse-1",
                "title": "サンプル: Museへの依頼タスク",
                "ai": "Muse",
                "status": "todo",
                "progress": 0,
                "request": "ここにMuseへお願いしたい作業を書く",
                "notes": "サンプルです。削除して使ってください。",
                "created": now_iso(),
                "updated": now_iso(),
            },
            {
                "id": "sample-gemini-1",
                "title": "サンプル: Geminiへの依頼タスク",
                "ai": "Gemini",
                "status": "todo",
                "progress": 0,
                "request": "ここにGeminiへお願いしたい作業を書く",
                "notes": "サンプルです。削除して使ってください。",
                "created": now_iso(),
                "updated": now_iso(),
            },
        ],
    }


def load_board(path):
    if not os.path.exists(path):
        data = sample_data()
        save_board(path, data)
        return data
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("version", 1)
    data.setdefault("ais", list(DEFAULT_AIS))
    data.setdefault("tasks", [])
    # AIが手で書いたデータは欠けたり型が違ったりするので、ここで揃える
    for task in data["tasks"]:
        try:
            task["progress"] = int(task.get("progress", 0))
        except (TypeError, ValueError):
            task["progress"] = 0
        task.setdefault("id", uuid.uuid4().hex[:8])
        task.setdefault("title", "(無題)")
        task.setdefault("ai", "Muse")
        task.setdefault("status", "todo")
        task.setdefault("request", "")
        task.setdefault("notes", "")
        if task["ai"] not in data["ais"]:
            data["ais"].append(task["ai"])
    return data


def _write_atomic(path, text):
    # 書きかけのファイルをAIやGUIに読ませないよう、一時ファイルに書いてから差し替える
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def save_board(path, data):
    for task in data["tasks"]:
        task["progress"] = max(0, min(100, int(task.get("progress", 0))))
        if task.get("status") == "done":
            task["progress"] = 100
    _write_atomic(path, json.dumps(data, ensure_ascii=False, indent=2))
    export_markdown(path, data)


def export_markdown(path, data):
    md_path = os.path.join(os.path.dirname(os.path.abspath(path)), "BOARD.md")
    lines = ["# AI Work Board", "", f"更新: {now_iso()}", ""]
    for ai in data["ais"]:
        tasks = [t for t in data["tasks"] if t["ai"] == ai]
        lines.append(f"## {ai} ({len(tasks)}件)")
        lines.append("")
        if not tasks:
            lines.append("- なし")
        for t in tasks:
            label = STATUS_LABEL.get(t["status"], t["status"])
            lines.append(f"- [{label} {t['progress']}%] {t['title']} (id: {t['id']})")
            if t.get("request"):
                lines.append(f"  - 依頼: {t['request']}")
            if t.get("notes"):
                lines.append(f"  - メモ: {t['notes']}")
        lines.append("")
    _write_atomic(md_path, "\n".join(lines))
    return md_path


# ---------------- タスク操作 (CLIとGUIで共通) ----------------

def find_task(data, task_id):
    """id の完全一致、無ければ前方一致が1件だけのときそのタスク。"""
    for t in data["tasks"]:
        if t["id"] == task_id:
            return t
    hits = [t for t in data["tasks"] if t["id"].startswith(task_id)]
    return hits[0] if len(hits) == 1 else None


def apply_task(data, fields, task_id=None):
    """fields のうち None 以外を書き込む。task_id が無ければ新規追加。対象タスクを返す。"""
    if task_id is None:
        task = {"id": uuid.uuid4().hex[:8], "title": "", "ai": "Muse", "status": "todo",
                "progress": 0, "request": "", "notes": "", "created": now_iso()}
        data["tasks"].append(task)
    else:
        task = find_task(data, task_id)
        if task is None:
            return None
    for key in TASK_FIELDS:
        if fields.get(key) is not None:
            task[key] = fields[key]
    if task["ai"] not in data["ais"]:
        data["ais"].append(task["ai"])
    task["updated"] = now_iso()
    return task


def local_time(iso):
    """'2026-10-29T06:48:07Z' -> '10/29 15:48' (PCのローカル時刻)"""
    try:
        dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return iso or ""
    return dt.astimezone().strftime("%m/%d %H:%M")


def visible_tasks(tasks, ai="すべて", status="すべて", query="", sort_key="updated", reverse=True):
    q = query.strip().lower()
    out = []
    for t in tasks:
        if ai != "すべて" and t["ai"] != ai:
            continue
        if status != "すべて" and STATUS_LABEL.get(t["status"]) != status:
            continue
        if q and not any(q in str(t.get(k, "")).lower() for k in ("title", "request", "notes", "id")):
            continue
        out.append(t)

    def key(t):
        if sort_key == "status":
            return STATUSES.index(t["status"]) if t["status"] in STATUSES else len(STATUSES)
        if sort_key == "progress":
            return int(t.get("progress", 0))
        return str(t.get(sort_key, "")).lower()

    return sorted(out, key=key, reverse=reverse)


def summarize(name, tasks):
    """{ai, count, avg (未完了の平均進捗), by (状態ごとの件数)}"""
    open_tasks = [t for t in tasks if t["status"] != "done"]
    by = {}
    for t in tasks:
        by[t["status"]] = by.get(t["status"], 0) + 1
    avg = round(sum(t["progress"] for t in open_tasks) / len(open_tasks)) if open_tasks else 0
    return {"ai": name, "count": len(tasks), "open": len(open_tasks), "avg": avg, "by": by}


def ai_summary(data):
    return [summarize(ai, [t for t in data["tasks"] if t["ai"] == ai]) for ai in data["ais"]]


def lane_detail(row):
    """レーンの件数の横に出す2行。"""
    if not row["count"]:
        first = "件"
    elif row["open"]:
        first = f"件  平均 {row['avg']}%"
    else:
        first = "件  すべて完了"
    rest = [f"{STATUS_LABEL[s]} {row['by'][s]}" for s in ("waiting", "blocked", "done") if row["by"].get(s)]
    return first + "\n" + "  ".join(rest)


AI_COLORS = {"Claude": "#E0A458", "Muse": "#A98BFF", "Gemini": "#3FB6C6"}
EXTRA_AI_COLORS = ("#6DC47A", "#EF7FA5", "#C9BC55", "#7F9CF5")


def ai_color(ais, ai):
    if ai in AI_COLORS:
        return AI_COLORS[ai]
    others = [a for a in ais if a not in AI_COLORS]
    return EXTRA_AI_COLORS[others.index(ai) % len(EXTRA_AI_COLORS) if ai in others else 0]


def request_prompt(task):
    """AIに貼り付ける依頼文。"""
    lines = [
        f"{task['ai']}さん、次のタスクをお願いします。",
        "",
        f"タイトル: {task['title']}",
        f"状態: {STATUS_LABEL.get(task['status'], task['status'])} {task['progress']}%",
    ]
    if task.get("request"):
        lines += ["", "依頼:", task["request"]]
    if task.get("notes"):
        lines += ["", "メモ:", task["notes"]]
    lines += [
        "",
        "進んだら board.json のこのタスク (id: {}) の status / progress / updated を更新してください。".format(task["id"]),
        f"CLIなら: python ai_work_board.py --update {task['id']} --progress <0-100> --status <{'|'.join(STATUSES)}>",
    ]
    return "\n".join(lines)


# ---------------- CLI (AIがGUIなしで読む・書くための入口) ----------------

def cli_list(path):
    data = load_board(path)
    for t in data["tasks"]:
        print(f"{t['id']} | {t['ai']} | {STATUS_LABEL.get(t['status'], t['status'])} {t['progress']}% | {t['title']}")
    return 0


def cli_add(path, args):
    data = load_board(path)
    task = apply_task(data, {
        "title": args.title,
        "ai": args.ai or "Muse",
        "status": args.status or "todo",
        "progress": args.progress if args.progress is not None else 0,
        "request": args.request or "",
        "notes": args.notes or "",
    })
    save_board(path, data)
    print(task["id"])
    return 0


def cli_update(path, args):
    data = load_board(path)
    task = apply_task(data, {k: getattr(args, k) for k in TASK_FIELDS}, args.id)
    if task is None:
        print(f"not found (or ambiguous): {args.id}", file=sys.stderr)
        return 1
    save_board(path, data)
    print(task["id"])
    return 0


# ---------------- MCP (Claude などに道具として渡す入口) ----------------

MCP_INSTRUCTIONS = (
    "AI Work Board のタスクを読み書きする道具です。作業を始める前に list_tasks で既存のタスクを確かめてください。"
    "新しい依頼は add_task、進んだら update_task で status と progress を更新し、終わったら complete_task。"
    "他の AI のタスクを消したり書き換えたりしないでください。人の名前やメールアドレスはタスクに入れないでください。"
)
_ID_PROP = {"id": {"type": "string", "description": "タスクの id (前方一致が1件だけなら短くてもよい)"}}
_TASK_PROPS = {
    "title": {"type": "string", "description": "タイトル"},
    "ai": {"type": "string", "description": "担当の AI (Claude / Muse / Gemini など)"},
    "status": {"type": "string", "enum": STATUSES,
               "description": "todo=未着手 in_progress=進行中 waiting=待ち blocked=停滞 done=完了"},
    "progress": {"type": "integer", "minimum": 0, "maximum": 100, "description": "進捗 (%)"},
    "request": {"type": "string", "description": "この AI への依頼"},
    "notes": {"type": "string", "description": "経緯や注意点"},
}
MCP_TOOLS = [
    {"name": "list_tasks", "description": "タスクの一覧 (更新が新しい順)。ai・status・query (タイトル・依頼・メモ・id の部分一致) で絞れる。",
     "inputSchema": {"type": "object", "properties": {
         "ai": _TASK_PROPS["ai"], "status": _TASK_PROPS["status"], "query": {"type": "string"}}}},
    {"name": "get_task", "description": "タスク1件を返す。",
     "inputSchema": {"type": "object", "properties": _ID_PROP, "required": ["id"]}},
    {"name": "add_task", "description": "タスクを追加して、そのタスクを返す (id が付く)。",
     "inputSchema": {"type": "object", "properties": _TASK_PROPS, "required": ["title", "ai"]}},
    {"name": "update_task", "description": "渡した項目だけ書き換えて、そのタスクを返す。",
     "inputSchema": {"type": "object", "properties": {**_ID_PROP, **_TASK_PROPS}, "required": ["id"]}},
    {"name": "complete_task", "description": "完了 (status=done, progress=100) にする。notes も一緒に書ける。",
     "inputSchema": {"type": "object", "properties": {**_ID_PROP, "notes": _TASK_PROPS["notes"]}, "required": ["id"]}},
]


def mcp_call(path, name, args):
    """道具を1回動かして結果の文字列を返す。毎回読み直して1件だけ書く (GUI や他の AI も同じファイルを書くため)。"""
    if name not in {t["name"] for t in MCP_TOOLS}:
        raise ValueError(f"知らない道具: {name}")
    data = load_board(path)
    if name == "list_tasks":
        status = STATUS_LABEL.get(args.get("status"), "すべて")
        tasks = visible_tasks(data["tasks"], args.get("ai") or "すべて", status, args.get("query") or "")
        return json.dumps(tasks, ensure_ascii=False, indent=1)
    fields = {k: args.get(k) for k in TASK_FIELDS}
    if name == "complete_task":
        fields.update(status="done", progress=100)
    if fields["status"] is not None and fields["status"] not in STATUSES:
        raise ValueError(f"status は {' / '.join(STATUSES)} のどれか")
    if fields["progress"] is not None:
        fields["progress"] = int(fields["progress"])
    if name == "add_task":
        if not fields["title"] or not fields["ai"]:
            raise ValueError("title と ai が要ります")
        task = apply_task(data, fields)
    else:
        task_id = str(args.get("id") or "")
        task = find_task(data, task_id) if task_id else None
        if task is None:
            raise ValueError(f"id が見つからないか、複数に当たります: {task_id}")
        if name == "get_task":
            return json.dumps(task, ensure_ascii=False, indent=1)
        apply_task(data, fields, task["id"])
    save_board(path, data)
    return json.dumps(task, ensure_ascii=False, indent=1)


def run_mcp(path):
    """MCP (JSON-RPC 2.0、1行1メッセージ) を標準入出力で話す。出力が壊れるので print は使わない。"""
    if sys.stdin is None or sys.stdout is None:  # 窓のアプリとして入出力なしで起動された
        return 1
    out = sys.stdout.buffer

    def send(msg):
        out.write(json.dumps(msg, ensure_ascii=False).encode("utf-8") + b"\n")
        out.flush()

    for line in sys.stdin.buffer:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            continue
        if not isinstance(msg, dict) or "id" not in msg:
            continue  # 通知には返事をしない
        method, params = msg.get("method"), msg.get("params") or {}
        reply = {"jsonrpc": "2.0", "id": msg["id"]}
        if method == "initialize":
            reply["result"] = {
                "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "ai-work-board", "version": VERSION},
                "instructions": MCP_INSTRUCTIONS,
            }
        elif method == "ping":
            reply["result"] = {}
        elif method == "tools/list":
            reply["result"] = {"tools": MCP_TOOLS}
        elif method == "tools/call":
            try:
                text = mcp_call(path, params.get("name"), params.get("arguments") or {})
                reply["result"] = {"content": [{"type": "text", "text": text}]}
            except Exception as e:  # 道具の失敗は AI に返して、サーバーは止めない
                reply["result"] = {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True}
        else:
            reply["error"] = {"code": -32601, "message": f"method not found: {method}"}
        send(reply)
    return 0


def run_cli(argv):
    parser = argparse.ArgumentParser(prog="ai-work-board")
    parser.add_argument("--data", default=None, help="board.json のパス")
    parser.add_argument("--mcp", action="store_true", help="MCP サーバーとして標準入出力で動く")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--add", metavar="TITLE")
    parser.add_argument("--update", metavar="ID")
    parser.add_argument("--done", metavar="ID")
    parser.add_argument("--ai", default=None)
    parser.add_argument("--status", default=None, choices=STATUSES)
    parser.add_argument("--progress", type=int, default=None)
    parser.add_argument("--title")
    parser.add_argument("--request")
    parser.add_argument("--notes")
    args = parser.parse_args(argv)
    path = data_path(args.data)
    if args.mcp:
        return run_mcp(path)
    if args.list:
        return cli_list(path)
    if args.export:
        data = load_board(path)
        print(export_markdown(path, data))
        return 0
    if args.add:
        args.title = args.add
        return cli_add(path, args)
    if args.done:
        args.id = args.done
        args.status = "done"
        args.progress = 100
        args.title = None
        args.ai = None
        args.request = None
        args.notes = None
        return cli_update(path, args)
    if args.update:
        args.id = args.update
        return cli_update(path, args)
    return None


# ---------------- GUI ----------------

POLL_MS = 2000
THEMES = {
    "dark": {
        "bg": "#151A24", "surface": "#1D2330", "raised": "#283041", "line": "#323B4E", "field": "#121722",
        "text": "#E7EAF1", "muted": "#8C95A8", "accent": "#6FA8FF", "accent_hover": "#8BB9FF",
        "on_accent": "#0D1320", "select": "#2B3A57",
        "status": {"todo": "#6B7488", "in_progress": "#6FA8FF", "waiting": "#E6B450", "blocked": "#EE6B6B",
                   "done": "#4FBF85"},
        "tint": {"waiting": "#24221A", "blocked": "#2A1D23"},
    },
    "light": {
        "bg": "#E8ECF2", "surface": "#F8FAFC", "raised": "#DDE3EC", "line": "#C8D1DD", "field": "#FFFFFF",
        "text": "#1B2230", "muted": "#5D6777", "accent": "#2F6FDB", "accent_hover": "#255FC2",
        "on_accent": "#FFFFFF", "select": "#D3E2FB",
        "status": {"todo": "#9AA3B2", "in_progress": "#2F6FDB", "waiting": "#C98F12", "blocked": "#D64545",
                   "done": "#2E9A62"},
        "tint": {"waiting": "#FBF3DE", "blocked": "#FBE7E7"},
    },
}
COLUMNS = (("#0", "title", "タイトル", 250), ("ai", "ai", "AI", 76), ("status", "status", "状態", 60),
           ("progress", "progress", "進捗", 56), ("updated", "updated", "更新", 104))


def ui_settings_path(path):
    return os.path.join(os.path.dirname(os.path.abspath(path)), "ai_work_board_ui.json")


def load_ui_settings(path):
    try:
        with open(ui_settings_path(path), encoding="utf-8") as f:
            settings = json.load(f)
        return settings if isinstance(settings, dict) else {}
    except (OSError, ValueError):
        return {}


def save_ui_settings(path, settings):
    try:
        _write_atomic(ui_settings_path(path), json.dumps(settings, ensure_ascii=False))
    except OSError:
        pass  # 見た目の設定は保存できなくても動作に差し支えない


def run_gui():
    import tkinter as tk
    from tkinter import font as tkfont, messagebox, ttk

    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # 高DPIの画面でぼやけないように
        except Exception:
            pass

    path = data_path(None)
    settings = load_ui_settings(path)
    state = {
        "data": load_board(path),
        "mtime": None,       # 最後に読んだ/書いた board.json の更新時刻
        "sel": None,         # 編集中のタスクid (None なら新規)
        "seen": None,        # 編集を始めたときのそのタスクの写し (外部の更新の検出用)
        "snapshot": None,    # 編集を始めたときのフォームの値 (変更中かどうかの判定用)
        "sort": ("updated", True),
        "theme": settings.get("theme") if settings.get("theme") in THEMES else "dark",
        "bars": {},          # 一覧の進捗バーの画像 (状態, 進捗) -> PhotoImage
    }

    root = tk.Tk()
    root.title("AI Work Board")
    scale = root.winfo_fpixels("1i") / 96

    def px(n):
        return int(round(n * scale))

    root.geometry(f"{px(1240)}x{px(760)}")
    root.minsize(px(960), px(600))

    families = set(tkfont.families(root))

    def pick(*names):
        return next((n for n in names if n in families), tkfont.nametofont("TkDefaultFont").actual("family"))

    jp = pick("BIZ UDPGothic", "Yu Gothic UI", "Meiryo UI", "Noto Sans CJK JP")
    num = pick("Bahnschrift", "Segoe UI", jp)
    F = {
        "ui": tkfont.Font(root, family=jp, size=10),
        "small": tkfont.Font(root, family=jp, size=9),
        "bold": tkfont.Font(root, family=jp, size=10, weight="bold"),
        "head": tkfont.Font(root, family=jp, size=12, weight="bold"),
        "title": tkfont.Font(root, family=num, size=17, weight="bold"),
        "big": tkfont.Font(root, family=num, size=22, weight="bold"),
        "num": tkfont.Font(root, family=num, size=18, weight="bold"),
    }
    root.option_add("*Font", F["ui"])
    style = ttk.Style(root)
    style.theme_use("clam")

    filter_ai = tk.StringVar(value="すべて")
    filter_status = tk.StringVar(value="すべて")
    query = tk.StringVar()
    status_msg = tk.StringVar()
    count_msg = tk.StringVar()

    def say(msg):
        status_msg.set(f"{datetime.now().strftime('%H:%M:%S')}  {msg}")

    # --- 見出し ---
    header = ttk.Frame(root, padding=(px(20), px(14), px(20), px(4)))
    header.pack(fill="x")
    ttk.Label(header, text="AI Work Board", font=F["title"]).pack(side="left")
    ttk.Label(header, text=f"v{VERSION}", style="Muted.TLabel").pack(side="left", padx=(px(8), 0), pady=(px(6), 0))
    ttk.Button(header, text="Markdown出力", command=lambda: export_now()).pack(side="right")
    theme_btn = ttk.Button(header, command=lambda: toggle_theme())
    theme_btn.pack(side="right", padx=px(8))
    ttk.Button(header, text="新規タスク", command=lambda: new_task()).pack(side="right")

    # --- AIごとのレーン (押すとそのAIに絞り込み) ---
    lanes = tk.Frame(root)
    lanes.pack(fill="x", padx=px(20), pady=(px(10), px(4)))

    # --- 検索と状態の絞り込み ---
    bar = ttk.Frame(root, padding=(px(20), px(8)))
    bar.pack(fill="x")
    ttk.Label(bar, text="検索", style="Muted.TLabel").pack(side="left")
    search_entry = ttk.Entry(bar, textvariable=query, width=26)
    search_entry.pack(side="left", padx=(px(8), px(18)))
    for label in ["すべて"] + [STATUS_LABEL[s] for s in STATUSES]:
        ttk.Radiobutton(bar, text=label, value=label, variable=filter_status,
                        style="Pill.Toolbutton").pack(side="left", padx=(0, px(4)))
    ttk.Label(bar, textvariable=count_msg, style="Muted.TLabel").pack(side="right")

    # 本体より先に下へ置く (後から pack すると本体に押し出されて見切れる)
    ttk.Label(root, textvariable=status_msg, style="Muted.TLabel", padding=(px(20), px(8))).pack(side="bottom", fill="x")

    # --- 本体: 左に一覧、右に編集 ---
    body = ttk.PanedWindow(root, orient="horizontal")
    body.pack(fill="both", expand=True, padx=px(20), pady=(px(4), 0))

    list_frame = ttk.Frame(body, style="Card.TFrame")
    tree = ttk.Treeview(list_frame, columns=[c[0] for c in COLUMNS[1:]], show="tree headings", selectmode="browse")
    for col, key, label, width in COLUMNS:
        tree.heading(col, text=label, anchor="e" if key == "progress" else "w", command=lambda k=key: sort_by(k))
        tree.column(col, width=px(width), minwidth=px(50), stretch=(col == "#0"),
                    anchor="e" if key == "progress" else "w")
    scroll = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.pack(side="left", fill="both", expand=True, padx=(px(6), 0), pady=px(6))
    scroll.pack(side="left", fill="y", pady=px(6))
    body.add(list_frame, weight=3)

    card = ttk.Frame(body, style="Card.TFrame")
    body.add(card, weight=2)
    stripe = tk.Frame(card, height=px(3))  # 編集中のタスクのAIの色
    stripe.pack(fill="x")
    form = ttk.Frame(card, style="Card.TFrame", padding=(px(18), px(12), px(18), px(16)))
    form.pack(fill="both", expand=True)
    form.columnconfigure(0, weight=1)
    form.columnconfigure(1, weight=1)

    form_head = tk.StringVar()
    form_id = tk.StringVar()
    title_var = tk.StringVar()
    ai_var = tk.StringVar(value="Muse")
    status_var = tk.StringVar(value=STATUS_LABEL["todo"])
    progress_var = tk.IntVar(value=0)
    progress_text = tk.StringVar(value="0%")

    def field_label(text, row, col=0, span=2):
        ttk.Label(form, text=text, style="CardMuted.TLabel").grid(
            row=row, column=col, columnspan=span, sticky="w", pady=(px(12), px(4)))

    ttk.Label(form, textvariable=form_head, style="CardHead.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(form, textvariable=form_id, style="CardMuted.TLabel").grid(row=0, column=1, sticky="e")
    field_label("タイトル", 1)
    title_entry = ttk.Entry(form, textvariable=title_var)
    title_entry.grid(row=2, column=0, columnspan=2, sticky="we")
    field_label("AI", 3, 0, 1)
    field_label("状態", 3, 1, 1)
    ai_edit = ttk.Combobox(form, textvariable=ai_var)
    ai_edit.grid(row=4, column=0, sticky="we", padx=(0, px(10)))
    ttk.Combobox(form, textvariable=status_var, values=[STATUS_LABEL[s] for s in STATUSES],
                 state="readonly").grid(row=4, column=1, sticky="we")
    field_label("進捗", 5, 0, 1)
    ttk.Label(form, textvariable=progress_text, style="CardNum.TLabel").grid(row=5, column=1, sticky="se", pady=(px(8), 0))
    meter = tk.Canvas(form, height=px(14), highlightthickness=0, takefocus=1, cursor="hand2")
    meter.grid(row=6, column=0, columnspan=2, sticky="we")
    field_label("このAIへの依頼", 7)
    text_opts = dict(height=5, width=30, wrap="word", undo=True, relief="flat", borderwidth=0,
                     highlightthickness=1, padx=px(10), pady=px(8))
    req_text = tk.Text(form, **text_opts)
    req_text.grid(row=8, column=0, columnspan=2, sticky="nsew")
    field_label("メモ", 9)
    notes_text = tk.Text(form, **text_opts)
    notes_text.grid(row=10, column=0, columnspan=2, sticky="nsew")
    form.rowconfigure(8, weight=3)
    form.rowconfigure(10, weight=2)

    btns = ttk.Frame(form, style="Card.TFrame")
    btns.grid(row=11, column=0, columnspan=2, sticky="we", pady=(px(16), 0))
    ttk.Button(btns, text="保存", style="Accent.TButton", command=lambda: save_current()).pack(side="left", padx=(0, px(6)))
    ttk.Button(btns, text="完了にする", command=lambda: mark_done()).pack(side="left", padx=(0, px(6)))
    ttk.Button(btns, text="依頼文をコピー", command=lambda: copy_prompt()).pack(side="left")
    ttk.Button(btns, text="削除", style="Danger.TButton", command=lambda: delete_task()).pack(side="right")

    # --- 見た目 ---
    def palette():
        return THEMES[state["theme"]]

    def set_titlebar():
        if sys.platform != "win32":
            return
        try:
            import ctypes
            root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
            dark = ctypes.c_int(1 if state["theme"] == "dark" else 0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))
        except Exception:
            pass

    def paint_stripe():
        p = palette()
        stripe.configure(bg=ai_color(state["data"]["ais"], ai_var.get()) if state["sel"] else p["accent"])

    def apply_theme():
        p = palette()
        root.configure(bg=p["bg"])
        flat = lambda color: dict(bordercolor=color, lightcolor=color, darkcolor=color)  # noqa: E731
        style.configure(".", background=p["bg"], foreground=p["text"], fieldbackground=p["field"],
                        troughcolor=p["raised"], selectbackground=p["accent"], selectforeground=p["on_accent"],
                        insertcolor=p["text"], focuscolor=p["accent"], font=F["ui"], **flat(p["bg"]))
        style.configure("Muted.TLabel", foreground=p["muted"])
        style.configure("Card.TFrame", background=p["surface"])
        style.configure("CardHead.TLabel", background=p["surface"], foreground=p["text"], font=F["head"])
        style.configure("CardMuted.TLabel", background=p["surface"], foreground=p["muted"], font=F["small"])
        style.configure("CardNum.TLabel", background=p["surface"], foreground=p["text"], font=F["num"])
        for name in ("TEntry", "TCombobox"):
            style.configure(name, padding=(px(8), px(5)), fieldbackground=p["field"], foreground=p["text"],
                            background=p["raised"], arrowcolor=p["muted"], bordercolor=p["line"],
                            lightcolor=p["field"], darkcolor=p["field"])
            style.map(name, bordercolor=[("focus", p["accent"])], lightcolor=[("focus", p["field"])],
                      fieldbackground=[("readonly", p["field"])], foreground=[("readonly", p["text"])],
                      selectbackground=[("readonly", p["field"])], selectforeground=[("readonly", p["text"])],
                      background=[("active", p["line"])])
        for opt, key in (("background", "field"), ("foreground", "text"),
                         ("selectBackground", "accent"), ("selectForeground", "on_accent")):
            root.option_add(f"*TCombobox*Listbox.{opt}", p[key])
        style.configure("TButton", padding=(px(14), px(6)), width=-4, background=p["raised"], foreground=p["text"],
                        relief="flat", **flat(p["raised"]))
        style.map("TButton", background=[("pressed", p["line"]), ("active", p["line"])],
                  bordercolor=[("focus", p["accent"])])
        style.configure("Accent.TButton", background=p["accent"], foreground=p["on_accent"], font=F["bold"],
                        **flat(p["accent"]))
        style.map("Accent.TButton", background=[("pressed", p["accent"]), ("active", p["accent_hover"])],
                  bordercolor=[("focus", p["text"])])
        style.configure("Danger.TButton", background=p["surface"], foreground=p["status"]["blocked"],
                        **flat(p["surface"]))
        style.map("Danger.TButton", background=[("pressed", p["line"]), ("active", p["raised"])])
        style.configure("Pill.Toolbutton", padding=(px(12), px(4)), background=p["bg"], foreground=p["muted"],
                        **flat(p["bg"]))
        style.map("Pill.Toolbutton", background=[("selected", p["raised"]), ("active", p["surface"])],
                  foreground=[("selected", p["text"]), ("active", p["text"])],
                  bordercolor=[("selected", p["line"])])
        style.configure("Treeview", background=p["surface"], fieldbackground=p["surface"], foreground=p["text"],
                        rowheight=px(32), font=F["ui"], borderwidth=0, **flat(p["surface"]))
        style.map("Treeview", background=[("selected", p["select"])], foreground=[("selected", p["text"])],
                  bordercolor=[("focus", p["surface"])], lightcolor=[("focus", p["surface"])],
                  darkcolor=[("focus", p["surface"])])
        style.configure("Treeview.Heading", background=p["surface"], foreground=p["muted"], relief="flat",
                        font=F["small"], padding=(px(6), px(6)), **flat(p["surface"]))
        style.map("Treeview.Heading", background=[("active", p["raised"])])
        style.configure("Vertical.TScrollbar", background=p["raised"], troughcolor=p["surface"],
                        arrowcolor=p["muted"], gripcount=0, **flat(p["surface"]))
        style.map("Vertical.TScrollbar", background=[("active", p["line"])])
        style.configure("Sash", sashthickness=px(14), gripcount=0, background=p["bg"], **flat(p["bg"]))
        for st, color in p["tint"].items():
            tree.tag_configure(st, background=color)
        tree.tag_configure("done", foreground=p["muted"])
        for widget in (req_text, notes_text):
            widget.configure(bg=p["field"], fg=p["text"], insertbackground=p["text"], selectbackground=p["accent"],
                             selectforeground=p["on_accent"], highlightbackground=p["line"],
                             highlightcolor=p["accent"])
        lanes.configure(bg=p["bg"])
        theme_btn.configure(text="ライトにする" if state["theme"] == "dark" else "ダークにする")
        state["bars"].clear()
        paint_stripe()
        set_titlebar()
        refresh_summary()
        refresh_list()

    def toggle_theme():
        state["theme"] = "light" if state["theme"] == "dark" else "dark"
        settings["theme"] = state["theme"]
        save_ui_settings(path, settings)
        apply_theme()

    def draw_meter(*_):
        p = palette()
        w, h = meter.winfo_width(), meter.winfo_height()
        meter.delete("all")
        meter.configure(bg=p["surface"])
        meter.create_rectangle(0, 0, w, h, fill=p["raised"], width=0)
        filled = w * get_progress() / 100
        color = p["status"].get(LABEL_STATUS.get(status_var.get(), "todo"), p["accent"])
        if filled:
            meter.create_rectangle(0, 0, filled, h, fill=color, width=0)
        if str(root.tk.call("focus")) == str(meter):  # focus_get はコンボボックスの一覧で例外を出すことがある
            meter.create_rectangle(0, 0, w - 1, h - 1, outline=p["accent"])

    def meter_to(x):
        progress_var.set(max(0, min(100, round(x / max(1, meter.winfo_width()) * 100))))

    def bar_image(status, progress):
        key = (status, progress)
        if key not in state["bars"]:
            p = palette()
            w, h = px(46), px(6)
            img = tk.PhotoImage(width=w + px(12), height=h)  # 右の余白は透明 (タイトルとの間)
            img.put(p["raised"], to=(0, 0, w, h))
            filled = round(w * max(0, min(100, progress)) / 100)
            if filled:
                img.put(p["status"].get(status, p["muted"]), to=(0, 0, filled, h))
            state["bars"][key] = img
        return state["bars"][key]

    # --- 表示 ---
    def get_progress():
        try:
            return max(0, min(100, int(progress_var.get())))
        except (tk.TclError, ValueError):
            return 0

    def form_values():
        return {"title": title_var.get().strip(), "ai": ai_var.get().strip() or "Muse",
                "status": LABEL_STATUS.get(status_var.get(), "todo"), "progress": get_progress(),
                "request": req_text.get("1.0", "end").strip(), "notes": notes_text.get("1.0", "end").strip()}

    def form_dirty():
        return state["snapshot"] is not None and form_values() != state["snapshot"]

    def remember_mtime():
        try:
            state["mtime"] = os.stat(path).st_mtime_ns
        except OSError:
            state["mtime"] = None

    def lane(row, color):
        p = palette()
        bg = p["surface"]
        active = filter_ai.get() == row["ai"]
        box = tk.Frame(lanes, bg=bg, cursor="hand2", highlightthickness=2,
                       highlightbackground=color if active else bg)
        box.pack(side="left", padx=(0, px(10)))
        tk.Frame(box, bg=color, width=px(4)).pack(side="left", fill="y")
        inner = tk.Frame(box, bg=bg)
        inner.pack(side="left", padx=(px(12), px(16)), pady=(px(8), px(10)))
        tk.Label(inner, text=row["ai"], font=F["bold"], bg=bg, fg=p["text"]).pack(anchor="w")
        line = tk.Frame(inner, bg=bg)
        line.pack(anchor="w")
        tk.Label(line, text=str(row["count"]), font=F["big"], bg=bg, fg=p["text"]).pack(side="left")
        tk.Label(line, text=lane_detail(row), font=F["small"], bg=bg, fg=p["muted"],
                 justify="left").pack(side="left", padx=(px(8), 0))
        w, h, gap = px(170), px(6), px(2)
        mix = tk.Canvas(inner, width=w, height=h, bg=bg, highlightthickness=0)
        mix.pack(anchor="w", pady=(px(6), 0))
        mix.create_rectangle(0, 0, w, h, fill=p["raised"], width=0)
        x = 0
        for st in STATUSES:  # 状態の内訳を左から 未着手→完了 の順に
            n = row["by"].get(st, 0)
            if n:
                seg = w * n / row["count"]
                mix.create_rectangle(x, 0, x + seg - (gap if x + seg < w - 1 else 0), h,
                                     fill=p["status"][st], width=0)
                x += seg
        stack = [box]
        while stack:
            widget = stack.pop()
            widget.bind("<Button-1>", lambda e, a=row["ai"]: root.after_idle(set_ai_filter, a))
            stack.extend(widget.winfo_children())

    def refresh_summary():
        for widget in lanes.winfo_children():
            widget.destroy()
        lane(summarize("すべて", state["data"]["tasks"]), palette()["muted"])
        for row in ai_summary(state["data"]):
            lane(row, ai_color(state["data"]["ais"], row["ai"]))
        ai_edit.configure(values=state["data"]["ais"])

    def refresh_list():
        key, rev = state["sort"]
        tasks = visible_tasks(state["data"]["tasks"], filter_ai.get(), filter_status.get(), query.get(), key, rev)
        tree.delete(*tree.get_children())
        for t in tasks:
            if tree.exists(t["id"]):  # id が重複していたら先の1件だけ出す
                continue
            tree.insert("", "end", iid=t["id"], text=t["title"], image=bar_image(t["status"], t["progress"]),
                        tags=(t["status"],),
                        values=(t["ai"], STATUS_LABEL.get(t["status"], t["status"]), f"{t['progress']}%",
                                local_time(t.get("updated", ""))))
        for col, k, label, _ in COLUMNS:
            mark = (" ▼" if rev else " ▲") if k == key else ""
            tree.heading(col, text=label + mark)
        count_msg.set(f"{len(tasks)} / {len(state['data']['tasks'])}件を表示")
        if state["sel"] and tree.exists(state["sel"]):
            tree.selection_set(state["sel"])
            tree.see(state["sel"])

    def reload():
        state["data"] = load_board(path)
        remember_mtime()
        refresh_summary()
        refresh_list()

    def set_ai_filter(ai):
        filter_ai.set("すべて" if filter_ai.get() == ai else ai)  # 同じレーンをもう一度押すと解除
        refresh_summary()
        refresh_list()

    def sort_by(key):
        cur, rev = state["sort"]
        state["sort"] = (key, not rev if key == cur else key in ("updated", "progress"))
        refresh_list()

    def fill_form(t):
        state["sel"] = t["id"] if t else None
        state["seen"] = dict(t) if t else None
        form_head.set("タスクを編集" if t else "新しいタスク")
        form_id.set(f"id {t['id']}" if t else "")
        title_var.set(t["title"] if t else "")
        if t:
            ai_var.set(t["ai"])  # 新規のときはAIは直前のまま (続けて同じAIに足しやすい)
        status_var.set(STATUS_LABEL.get(t["status"], t["status"]) if t else STATUS_LABEL["todo"])
        progress_var.set(int(t["progress"]) if t else 0)
        for widget, key in ((req_text, "request"), (notes_text, "notes")):
            widget.delete("1.0", "end")
            widget.insert("1.0", t.get(key, "") if t else "")
            widget.edit_reset()
        state["snapshot"] = form_values()
        paint_stripe()

    def on_select(_event=None):
        sel = tree.selection()
        if not sel or sel[0] == state["sel"]:
            return
        if form_dirty() and not messagebox.askyesno("未保存", "編集中の内容が保存されていません。破棄して切り替えますか？"):
            tree.selection_set(state["sel"]) if state["sel"] and tree.exists(state["sel"]) else tree.selection_remove(sel)
            return
        t = find_task(state["data"], sel[0])
        if t:
            fill_form(t)

    # --- 書き込み: 毎回ディスクから読み直し、対象の1件だけ書き換える (AIの書き込みを消さない) ---
    def load_fresh():
        try:
            return load_board(path)
        except (OSError, ValueError) as e:
            messagebox.showerror("読み込みエラー", f"board.json を読めませんでした。保存を中止します。\n{e}")
            return None

    def commit(fresh):
        try:
            save_board(path, fresh)
        except OSError as e:
            messagebox.showerror("保存エラー", f"board.json に書けませんでした。\n{e}")
            return False
        state["data"] = fresh
        remember_mtime()
        refresh_summary()
        return True

    def save_current():
        fields = form_values()
        if not fields["title"]:
            messagebox.showwarning("入力", "タイトルを入力してください")
            title_entry.focus_set()
            return
        fresh = load_fresh()
        if fresh is None:
            return
        task_id = state["sel"]
        if task_id:
            current = find_task(fresh, task_id)
            if current is None:
                if not messagebox.askyesno("削除済み", "このタスクは外部で削除されています。新しいタスクとして保存しますか？"):
                    return
                task_id = None
            elif current != state["seen"] and not messagebox.askyesno(
                    "外部で更新済み", "このタスクは外部 (AIなど) で更新されています。\n今の入力内容で上書きしますか？"):
                return
        task = apply_task(fresh, fields, task_id)
        if not commit(fresh):
            return
        fill_form(task)
        refresh_list()
        say(f"保存しました: {task['title']}")

    def mark_done():
        status_var.set(STATUS_LABEL["done"])
        progress_var.set(100)
        save_current()

    def new_task():
        if form_dirty() and not messagebox.askyesno("未保存", "編集中の内容が保存されていません。破棄しますか？"):
            return
        tree.selection_remove(*tree.selection())
        fill_form(None)
        title_entry.focus_set()

    def delete_task():
        if not state["sel"]:
            return
        t = find_task(state["data"], state["sel"])
        if not messagebox.askyesno("削除", f"「{t['title'] if t else state['sel']}」を削除しますか？"):
            return
        fresh = load_fresh()
        if fresh is None:
            return
        fresh["tasks"] = [x for x in fresh["tasks"] if x["id"] != state["sel"]]
        if not commit(fresh):
            return
        fill_form(None)
        refresh_list()
        say("削除しました")

    def copy_prompt():
        fields = form_values()
        if not fields["title"]:
            return
        task = dict(fields, id=state["sel"] or "(未保存)")
        root.clipboard_clear()
        root.clipboard_append(request_prompt(task))
        say(f"{task['ai']} への依頼文をコピーしました")

    def export_now():
        try:
            md = export_markdown(path, load_board(path))
        except (OSError, ValueError) as e:
            messagebox.showerror("出力", str(e))
            return
        say(f"Markdownを出力しました: {md}")

    # --- 外部 (AI・CLI) の変更を監視 ---
    def poll():
        try:
            mtime = os.stat(path).st_mtime_ns
            if mtime != state["mtime"]:
                reload()
                t = find_task(state["data"], state["sel"]) if state["sel"] else None
                if state["sel"] and t is None:
                    say("外部の変更を読み込みました (編集中のタスクは外部で削除されています)")
                elif t and t != state["seen"]:
                    if form_dirty():
                        say("外部の変更を読み込みました (編集中のタスクも外部で更新されています。保存すると確認が出ます)")
                    else:
                        fill_form(t)
                        say("外部の変更を読み込みました (編集中のタスクを最新にしました)")
                else:
                    say("外部の変更を読み込みました")
        except Exception:
            pass  # 書き込み途中や形の崩れたデータで読めないときは次の周期で読み直す
        finally:
            root.after(POLL_MS, poll)  # 何があっても監視は止めない

    for var in (filter_status, query):
        var.trace_add("write", lambda *_: refresh_list())
    progress_var.trace_add("write", lambda *_: (progress_text.set(f"{get_progress()}%"), draw_meter()))
    status_var.trace_add("write", draw_meter)
    meter.bind("<Configure>", draw_meter)
    meter.bind("<FocusIn>", draw_meter)
    meter.bind("<FocusOut>", draw_meter)
    meter.bind("<Button-1>", lambda e: (meter.focus_set(), meter_to(e.x)))
    meter.bind("<B1-Motion>", lambda e: meter_to(e.x))
    meter.bind("<Left>", lambda e: progress_var.set(max(0, get_progress() - 5)))
    meter.bind("<Right>", lambda e: progress_var.set(min(100, get_progress() + 5)))
    ai_var.trace_add("write", lambda *_: paint_stripe())
    tree.bind("<<TreeviewSelect>>", on_select)
    tree.bind("<Delete>", lambda e: delete_task())
    root.bind("<Control-s>", lambda e: (save_current(), "break")[1])
    root.bind("<Control-n>", lambda e: (new_task(), "break")[1])
    root.bind("<Control-f>", lambda e: (search_entry.focus_set(), "break")[1])
    search_entry.bind("<Escape>", lambda e: query.set(""))

    remember_mtime()
    fill_form(None)
    apply_theme()
    def place_sash():  # 窓の大きさが決まってから一覧を6割に
        if body.winfo_width() < 100:
            root.after(50, place_sash)
        else:
            body.sashpos(0, int(body.winfo_width() * 0.6))

    place_sash()
    say(f"{path} を開きました")
    root.after(POLL_MS, poll)
    root.mainloop()


def main():
    result = run_cli(sys.argv[1:])
    if result is None:
        run_gui()
    else:
        sys.exit(result)


if __name__ == "__main__":
    main()
