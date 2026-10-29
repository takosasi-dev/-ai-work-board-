#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Work Board - 各AIとの作業進捗と依頼を一元管理するGUIツール

対象AI: Claude / Muse / Gemini (追加可能)
データ: board.json (人間にもAIにも読める素直なJSON)
AI連携: このファイルと同じフォルダの board.json を読めば進捗が分かり、
  書き込めばGUIに反映される。CLIでも同じ操作ができる:
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
import uuid
from datetime import datetime, timezone

VERSION = "0.1.0"
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
    for task in data["tasks"]:
        task.setdefault("progress", 0)
        task.setdefault("status", "todo")
        task.setdefault("request", "")
        task.setdefault("notes", "")
    return data


def save_board(path, data):
    for task in data["tasks"]:
        task["progress"] = max(0, min(100, int(task.get("progress", 0))))
        if task.get("status") == "done":
            task["progress"] = 100
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    export_markdown(path, data)


def export_markdown(path, data):
    md_path = os.path.join(os.path.dirname(path), "BOARD.md")
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
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return md_path


# ---------------- CLI (AIがGUIなしで読む・書くための入口) ----------------

def cli_list(path):
    data = load_board(path)
    for t in data["tasks"]:
        print(f"{t['id']} | {t['ai']} | {STATUS_LABEL.get(t['status'], t['status'])} {t['progress']}% | {t['title']}")
    return 0


def cli_add(path, args):
    data = load_board(path)
    task = {
        "id": uuid.uuid4().hex[:8],
        "title": args.title,
        "ai": args.ai or "Muse",
        "status": args.status or "todo",
        "progress": args.progress if args.progress is not None else 0,
        "request": args.request or "",
        "notes": args.notes or "",
        "created": now_iso(),
        "updated": now_iso(),
    }
    if task["ai"] not in data["ais"]:
        data["ais"].append(task["ai"])
    data["tasks"].append(task)
    save_board(path, data)
    print(task["id"])
    return 0


def cli_update(path, args):
    data = load_board(path)
    for t in data["tasks"]:
        if t["id"] == args.id or t["id"].startswith(args.id):
            if args.title is not None:
                t["title"] = args.title
            if args.ai is not None:
                t["ai"] = args.ai
                if t["ai"] not in data["ais"]:
                    data["ais"].append(t["ai"])
            if args.status is not None:
                t["status"] = args.status
            if args.progress is not None:
                t["progress"] = args.progress
            if args.request is not None:
                t["request"] = args.request
            if args.notes is not None:
                t["notes"] = args.notes
            t["updated"] = now_iso()
            save_board(path, data)
            print(t["id"])
            return 0
    print(f"not found: {args.id}", file=sys.stderr)
    return 1


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

def run_gui():
    import tkinter as tk
    from tkinter import messagebox, ttk

    path = data_path(None)
    data = load_board(path)

    root = tk.Tk()
    root.title(f"AI Work Board v{VERSION}")
    root.geometry("980x620")

    filter_ai = tk.StringVar(value="すべて")
    filter_status = tk.StringVar(value="すべて")
    sel_id = {"id": None}

    top = ttk.Frame(root, padding=8)
    top.pack(fill="x")
    ttk.Label(top, text="AI:").pack(side="left")
    ai_combo = ttk.Combobox(top, textvariable=filter_ai, values=["すべて"] + data["ais"], state="readonly", width=14)
    ai_combo.pack(side="left", padx=4)
    ttk.Label(top, text="状態:").pack(side="left")
    st_combo = ttk.Combobox(top, textvariable=filter_status, values=["すべて"] + [STATUS_LABEL[s] for s in STATUSES], state="readonly", width=12)
    st_combo.pack(side="left", padx=4)
    ttk.Button(top, text="絞り込み", command=lambda: refresh()).pack(side="left", padx=8)
    ttk.Button(top, text="Markdown出力", command=lambda: (save_board(path, data), messagebox.showinfo("出力", "BOARD.md を更新しました"))).pack(side="left")

    tree = ttk.Treeview(root, columns=("ai", "status", "progress", "updated"), show="tree headings")
    tree.heading("#0", text="タイトル")
    tree.heading("ai", text="AI")
    tree.heading("status", text="状態")
    tree.heading("progress", text="進捗")
    tree.heading("updated", text="更新")
    tree.column("#0", width=420)
    tree.column("ai", width=110)
    tree.column("status", width=90)
    tree.column("progress", width=80)
    tree.column("updated", width=170)
    tree.pack(fill="both", expand=True, padx=8, pady=4)

    form = ttk.Frame(root, padding=8)
    form.pack(fill="x")
    title_var = tk.StringVar()
    ai_var = tk.StringVar(value="Muse")
    status_var = tk.StringVar(value="進行中")
    progress_var = tk.IntVar(value=0)
    ttk.Label(form, text="タイトル").grid(row=0, column=0, sticky="w")
    ttk.Entry(form, textvariable=title_var, width=60).grid(row=0, column=1, columnspan=3, sticky="we", padx=4, pady=2)
    ttk.Label(form, text="AI").grid(row=1, column=0, sticky="w")
    ttk.Combobox(form, textvariable=ai_var, values=data["ais"], width=14).grid(row=1, column=1, sticky="w", padx=4, pady=2)
    ttk.Label(form, text="状態").grid(row=1, column=2, sticky="w")
    ttk.Combobox(form, textvariable=status_var, values=[STATUS_LABEL[s] for s in STATUSES], state="readonly", width=12).grid(row=1, column=3, sticky="w", padx=4, pady=2)
    ttk.Label(form, text="進捗").grid(row=2, column=0, sticky="w")
    ttk.Scale(form, variable=progress_var, from_=0, to=100, orient="horizontal", length=300).grid(row=2, column=1, columnspan=2, sticky="we", padx=4, pady=2)
    ttk.Label(form, textvariable=progress_var).grid(row=2, column=3, sticky="w")
    ttk.Label(form, text="このAIへの依頼").grid(row=3, column=0, sticky="nw")
    req_text = tk.Text(form, height=3, width=60)
    req_text.grid(row=3, column=1, columnspan=3, sticky="we", padx=4, pady=2)
    ttk.Label(form, text="メモ").grid(row=4, column=0, sticky="nw")
    notes_text = tk.Text(form, height=3, width=60)
    notes_text.grid(row=4, column=1, columnspan=3, sticky="we", padx=4, pady=2)

    def refresh():
        for row in tree.get_children():
            tree.delete(row)
        for t in data["tasks"]:
            if filter_ai.get() != "すべて" and t["ai"] != filter_ai.get():
                continue
            if filter_status.get() != "すべて" and STATUS_LABEL.get(t["status"]) != filter_status.get():
                continue
            tree.insert("", "end", iid=t["id"], text=t["title"],
                        values=(t["ai"], STATUS_LABEL.get(t["status"], t["status"]), f"{t['progress']}%", t.get("updated", "")))

    def on_select(_event=None):
        sel = tree.selection()
        if not sel:
            return
        sel_id["id"] = sel[0]
        t = next((x for x in data["tasks"] if x["id"] == sel[0]), None)
        if not t:
            return
        title_var.set(t["title"])
        ai_var.set(t["ai"])
        status_var.set(STATUS_LABEL.get(t["status"], t["status"]))
        progress_var.set(int(t["progress"]))
        req_text.delete("1.0", "end")
        req_text.insert("1.0", t.get("request", ""))
        notes_text.delete("1.0", "end")
        notes_text.insert("1.0", t.get("notes", ""))

    def save_current():
        title = title_var.get().strip()
        if not title:
            messagebox.showwarning("入力", "タイトルを入力してください")
            return
        status = LABEL_STATUS.get(status_var.get(), "todo")
        if sel_id["id"]:
            t = next((x for x in data["tasks"] if x["id"] == sel_id["id"]), None)
            if t:
                t.update({"title": title, "ai": ai_var.get(), "status": status,
                          "progress": int(progress_var.get()),
                          "request": req_text.get("1.0", "end").strip(),
                          "notes": notes_text.get("1.0", "end").strip(),
                          "updated": now_iso()})
        else:
            data["tasks"].append({
                "id": uuid.uuid4().hex[:8], "title": title, "ai": ai_var.get(),
                "status": status, "progress": int(progress_var.get()),
                "request": req_text.get("1.0", "end").strip(),
                "notes": notes_text.get("1.0", "end").strip(),
                "created": now_iso(), "updated": now_iso()})
            if ai_var.get() not in data["ais"]:
                data["ais"].append(ai_var.get())
        save_board(path, data)
        refresh()

    def new_task():
        sel_id["id"] = None
        title_var.set("")
        progress_var.set(0)
        req_text.delete("1.0", "end")
        notes_text.delete("1.0", "end")

    def delete_task():
        if not sel_id["id"]:
            return
        if messagebox.askyesno("削除", "選択したタスクを削除しますか？"):
            data["tasks"] = [x for x in data["tasks"] if x["id"] != sel_id["id"]]
            save_board(path, data)
            new_task()
            refresh()

    btns = ttk.Frame(root, padding=8)
    btns.pack(fill="x")
    ttk.Button(btns, text="新規", command=new_task).pack(side="left", padx=4)
    ttk.Button(btns, text="保存", command=save_current).pack(side="left", padx=4)
    ttk.Button(btns, text="削除", command=delete_task).pack(side="left", padx=4)
    ttk.Button(btns, text="完了にする", command=lambda: (status_var.set("完了"), progress_var.set(100), save_current())).pack(side="left", padx=4)

    tree.bind("<<TreeviewSelect>>", on_select)
    refresh()
    root.mainloop()


def main():
    result = run_cli(sys.argv[1:])
    if result is None:
        run_gui()
    else:
        sys.exit(result)


if __name__ == "__main__":
    main()
