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
GUIは標準ライブラリ(tkinter)のみで動く。WindowsでPyInstaller化して .exe にできる。
"""

import argparse
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone

VERSION = "0.2.1"
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


def progress_bar(progress, width=10):
    filled = round(max(0, min(100, progress)) / 100 * width)
    return "█" * filled + "░" * (width - filled) + f" {progress:>3}%"


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


def ai_summary(data):
    """AIごとに (ai, 件数, 未完了の平均進捗, 待ち, 停滞, 完了) を返す。"""
    rows = []
    for ai in data["ais"]:
        tasks = [t for t in data["tasks"] if t["ai"] == ai]
        open_tasks = [t for t in tasks if t["status"] != "done"]
        avg = round(sum(t["progress"] for t in open_tasks) / len(open_tasks)) if open_tasks else 0
        count = lambda s: sum(1 for t in tasks if t["status"] == s)
        rows.append((ai, len(tasks), avg, count("waiting"), count("blocked"), count("done")))
    return rows


def summary_text(row):
    ai, n, avg, waiting, blocked, done = row
    parts = [ai, f"{n}件"]
    if n - done:
        parts.append(f"平均{avg}%")
    if waiting:
        parts.append(f"待ち{waiting}")
    if blocked:
        parts.append(f"停滞{blocked}")
    if done:
        parts.append(f"完了{done}")
    return "  ".join(parts)


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


def run_cli(argv):
    parser = argparse.ArgumentParser(prog="ai-work-board")
    parser.add_argument("--data", default=None, help="board.json のパス")
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
STATUS_COLORS = {  # 一覧の行の背景・文字色
    "todo": ("#ffffff", "#222222"),
    "in_progress": ("#e6f0fb", "#14365c"),
    "waiting": ("#fff4d6", "#5c4300"),
    "blocked": ("#fde4e4", "#7a1616"),
    "done": ("#f2f2f2", "#8a8a8a"),
}
COLUMNS = (("#0", "title", "タイトル", 280), ("ai", "ai", "AI", 80), ("status", "status", "状態", 60),
           ("progress", "progress", "進捗", 130), ("updated", "updated", "更新", 90))


def run_gui():
    import tkinter as tk
    from tkinter import font as tkfont, messagebox, ttk

    path = data_path(None)
    state = {
        "data": load_board(path),
        "mtime": None,       # 最後に読んだ/書いた board.json の更新時刻
        "sel": None,         # 編集中のタスクid (None なら新規)
        "seen": None,        # 編集を始めたときのそのタスクの写し (外部の更新の検出用)
        "snapshot": None,    # 編集を始めたときのフォームの値 (変更中かどうかの判定用)
        "sort": ("updated", True),
    }

    root = tk.Tk()
    root.title(f"AI Work Board v{VERSION}")
    root.geometry("1180x680")
    root.minsize(900, 520)
    style = ttk.Style(root)
    style.configure("Treeview", rowheight=26)
    style.configure("Status.TLabel", foreground="#555555")
    head_font = tkfont.nametofont("TkDefaultFont").copy()
    head_font.configure(weight="bold")
    style.configure("Head.TLabel", font=head_font)

    filter_ai = tk.StringVar(value="すべて")
    filter_status = tk.StringVar(value="すべて")
    query = tk.StringVar()
    status_msg = tk.StringVar()
    count_msg = tk.StringVar()

    def say(msg):
        status_msg.set(f"{datetime.now().strftime('%H:%M:%S')}  {msg}")

    # --- 上部: AI別サマリー (クリックでそのAIに絞り込み) ---
    summary = ttk.Frame(root, padding=(8, 8, 8, 0))
    summary.pack(fill="x")

    # --- 絞り込み ---
    bar = ttk.Frame(root, padding=8)
    bar.pack(fill="x")
    ttk.Label(bar, text="検索").pack(side="left")
    search_entry = ttk.Entry(bar, textvariable=query, width=28)
    search_entry.pack(side="left", padx=(4, 12))
    ttk.Label(bar, text="AI").pack(side="left")
    ai_combo = ttk.Combobox(bar, textvariable=filter_ai, state="readonly", width=12)
    ai_combo.pack(side="left", padx=(4, 12))
    ttk.Label(bar, text="状態").pack(side="left")
    st_combo = ttk.Combobox(bar, textvariable=filter_status, state="readonly", width=10,
                            values=["すべて"] + [STATUS_LABEL[s] for s in STATUSES])
    st_combo.pack(side="left", padx=4)
    ttk.Button(bar, text="条件クリア", command=lambda: clear_filters()).pack(side="left", padx=8)
    ttk.Label(bar, textvariable=count_msg, style="Status.TLabel").pack(side="left", padx=8)
    ttk.Button(bar, text="Markdown出力", command=lambda: export_now()).pack(side="right")

    # --- 本体: 左に一覧、右に編集 ---
    body = ttk.PanedWindow(root, orient="horizontal")
    body.pack(fill="both", expand=True, padx=8)

    list_frame = ttk.Frame(body)
    tree = ttk.Treeview(list_frame, columns=[c[0] for c in COLUMNS[1:]], show="tree headings", selectmode="browse")
    for col, key, label, width in COLUMNS:
        tree.heading(col, text=label, command=lambda k=key: sort_by(k))
        tree.column(col, width=width, minwidth=50, stretch=(col == "#0"))
    for st, (bg, fg) in STATUS_COLORS.items():
        tree.tag_configure(st, background=bg, foreground=fg)
    scroll = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.pack(side="left", fill="both", expand=True)
    scroll.pack(side="left", fill="y")
    body.add(list_frame, weight=3)

    form = ttk.Frame(body, padding=(12, 0, 0, 0))
    body.add(form, weight=2)
    form.columnconfigure(1, weight=1)
    form_head = tk.StringVar(value="新規タスク")
    ttk.Label(form, textvariable=form_head, style="Head.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
    title_var = tk.StringVar()
    ai_var = tk.StringVar(value="Muse")
    status_var = tk.StringVar(value="未着手")
    progress_var = tk.IntVar(value=0)
    ttk.Label(form, text="タイトル").grid(row=1, column=0, sticky="w")
    title_entry = ttk.Entry(form, textvariable=title_var)
    title_entry.grid(row=1, column=1, columnspan=2, sticky="we", padx=4, pady=3)
    ttk.Label(form, text="AI").grid(row=2, column=0, sticky="w")
    ai_edit = ttk.Combobox(form, textvariable=ai_var, width=14)
    ai_edit.grid(row=2, column=1, sticky="w", padx=4, pady=3)
    ttk.Label(form, text="状態").grid(row=3, column=0, sticky="w")
    ttk.Combobox(form, textvariable=status_var, values=[STATUS_LABEL[s] for s in STATUSES],
                 state="readonly", width=12).grid(row=3, column=1, sticky="w", padx=4, pady=3)
    ttk.Label(form, text="進捗").grid(row=4, column=0, sticky="w")
    ttk.Scale(form, variable=progress_var, from_=0, to=100, orient="horizontal",
              command=lambda v: progress_var.set(round(float(v)))).grid(row=4, column=1, sticky="we", padx=4, pady=3)
    ttk.Spinbox(form, textvariable=progress_var, from_=0, to=100, increment=5, width=5).grid(row=4, column=2, sticky="w", padx=4)
    ttk.Label(form, text="このAIへの依頼").grid(row=5, column=0, sticky="nw", pady=3)
    req_text = tk.Text(form, height=7, width=30, wrap="word", undo=True)
    req_text.grid(row=5, column=1, columnspan=2, sticky="nsew", padx=4, pady=3)
    ttk.Label(form, text="メモ").grid(row=6, column=0, sticky="nw", pady=3)
    notes_text = tk.Text(form, height=5, width=30, wrap="word", undo=True)
    notes_text.grid(row=6, column=1, columnspan=2, sticky="nsew", padx=4, pady=3)
    form.rowconfigure(5, weight=2)
    form.rowconfigure(6, weight=1)

    btns = ttk.Frame(form)
    btns.grid(row=7, column=0, columnspan=3, sticky="we", pady=(8, 0))
    ttk.Button(btns, text="保存", command=lambda: save_current()).pack(side="left", padx=(0, 4))
    ttk.Button(btns, text="完了にする", command=lambda: mark_done()).pack(side="left", padx=4)
    ttk.Button(btns, text="依頼文をコピー", command=lambda: copy_prompt()).pack(side="left", padx=4)
    ttk.Button(btns, text="新規", command=lambda: new_task()).pack(side="left", padx=4)
    ttk.Button(btns, text="削除", command=lambda: delete_task()).pack(side="right")

    ttk.Label(root, textvariable=status_msg, style="Status.TLabel", padding=(8, 4)).pack(fill="x")

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

    def refresh_summary():
        for w in summary.winfo_children():
            w.destroy()
        ttk.Button(summary, text=f"すべて  {len(state['data']['tasks'])}件",
                   command=lambda: root.after_idle(set_ai_filter, "すべて")).pack(side="left", padx=(0, 6))
        for row in ai_summary(state["data"]):
            ttk.Button(summary, text=summary_text(row),
                       command=lambda a=row[0]: root.after_idle(set_ai_filter, a)).pack(side="left", padx=(0, 6))
        ai_combo.configure(values=["すべて"] + state["data"]["ais"])
        ai_edit.configure(values=state["data"]["ais"])

    def refresh_list():
        key, rev = state["sort"]
        tasks = visible_tasks(state["data"]["tasks"], filter_ai.get(), filter_status.get(), query.get(), key, rev)
        tree.delete(*tree.get_children())
        for t in tasks:
            if tree.exists(t["id"]):  # id が重複していたら先の1件だけ出す
                continue
            tree.insert("", "end", iid=t["id"], text=t["title"], tags=(t["status"],),
                        values=(t["ai"], STATUS_LABEL.get(t["status"], t["status"]),
                                progress_bar(t["progress"]), local_time(t.get("updated", ""))))
        for col, k, label, _ in COLUMNS:
            mark = (" ▼" if rev else " ▲") if k == key else ""
            tree.heading(col, text=label + mark)
        count_msg.set(f"{len(tasks)} / {len(state['data']['tasks'])}件")
        if state["sel"] and tree.exists(state["sel"]):
            tree.selection_set(state["sel"])
            tree.see(state["sel"])

    def reload(msg=None):
        state["data"] = load_board(path)
        remember_mtime()
        refresh_summary()
        refresh_list()
        if msg:
            say(msg)

    def set_ai_filter(ai):
        filter_ai.set(ai)
        refresh_list()

    def clear_filters():
        filter_ai.set("すべて")
        filter_status.set("すべて")
        query.set("")

    def sort_by(key):
        cur, rev = state["sort"]
        state["sort"] = (key, not rev if key == cur else key in ("updated", "progress"))
        refresh_list()

    def fill_form(t):
        state["sel"] = t["id"] if t else None
        state["seen"] = dict(t) if t else None
        form_head.set(f"編集中: {t['id']}" if t else "新規タスク")
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
        remember_mtime()
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

    for var in (filter_ai, filter_status, query):
        var.trace_add("write", lambda *_: refresh_list())
    tree.bind("<<TreeviewSelect>>", on_select)
    tree.bind("<Delete>", lambda e: delete_task())
    root.bind("<Control-s>", lambda e: (save_current(), "break")[1])
    root.bind("<Control-n>", lambda e: (new_task(), "break")[1])
    root.bind("<Control-f>", lambda e: (search_entry.focus_set(), "break")[1])
    search_entry.bind("<Escape>", lambda e: query.set(""))

    remember_mtime()
    refresh_summary()
    refresh_list()
    fill_form(None)
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
