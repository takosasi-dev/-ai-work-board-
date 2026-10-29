#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""データ層とCLIの確認 (窓は出さない)。 python test_ai_work_board.py"""
import json
import os
import subprocess
import sys
import tempfile

import ai_work_board as b

HERE = os.path.dirname(os.path.abspath(__file__))


def cli(path, *args):
    out = subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, "ai_work_board.py"), "--data", path, *args],
                         capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def main():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "board.json")

        # 初回はサンプルを作る。保存は一時ファイルを残さない
        data = b.load_board(path)
        assert len(data["tasks"]) == 3
        assert sorted(os.listdir(d)) == ["BOARD.md", "board.json"], os.listdir(d)

        # GUIの流れ: 選択時の写しを持つ → その間にAIがCLIで追加・更新 → GUIは読み直して1件だけ書く
        seen = dict(b.find_task(b.load_board(path), "sample-claude-1"))
        new_id = cli(path, "--add", "AIが足したタスク", "--ai", "Gemini")
        cli(path, "--update", "sample-claude", "--notes", "AIが書いたメモ")
        fresh = b.load_board(path)
        assert b.find_task(fresh, "sample-claude-1") != seen  # 衝突を検出できる (同じ秒でも)
        b.apply_task(fresh, {"title": "GUIで直した", "ai": "Claude", "status": "waiting", "progress": 55,
                             "request": "r", "notes": "n"}, "sample-claude-1")
        b.save_board(path, fresh)
        after = b.load_board(path)
        assert b.find_task(after, new_id)["title"] == "AIが足したタスク"  # AIの追加が消えていない
        assert b.find_task(after, "sample-claude-1")["status"] == "waiting"

        # 前方一致は1件のときだけ
        assert b.find_task(after, "sample-") is None
        assert b.find_task(after, "sample-m")["id"] == "sample-muse-1"

        # --done で100%、--list に出る
        cli(path, "--done", new_id)
        assert b.find_task(b.load_board(path), new_id)["progress"] == 100
        assert new_id in cli(path, "--list")

        # AIが進捗を文字列で書いても読める
        raw = json.load(open(path, encoding="utf-8"))
        raw["tasks"][0]["progress"] = "30"
        raw["tasks"][1]["progress"] = "abc"
        json.dump(raw, open(path, "w", encoding="utf-8"), ensure_ascii=False)
        data = b.load_board(path)
        assert [t["progress"] for t in data["tasks"][:2]] == [30, 0]

    # 絞り込み・検索・並べ替え
    tasks = [
        {"id": "a1", "title": "Alpha", "ai": "Claude", "status": "done", "progress": 100, "request": "", "notes": "", "updated": "2026-01-02T00:00:00Z"},
        {"id": "b2", "title": "Beta", "ai": "Muse", "status": "blocked", "progress": 20, "request": "ログ調査", "notes": "", "updated": "2026-01-03T00:00:00Z"},
        {"id": "c3", "title": "Gamma", "ai": "Claude", "status": "todo", "progress": 0, "request": "", "notes": "", "updated": "2026-01-01T00:00:00Z"},
    ]
    ids = lambda ts: [t["id"] for t in ts]
    assert ids(b.visible_tasks(tasks)) == ["b2", "a1", "c3"]  # 既定は更新が新しい順
    assert ids(b.visible_tasks(tasks, ai="Claude")) == ["a1", "c3"]
    assert ids(b.visible_tasks(tasks, status="停滞")) == ["b2"]
    assert ids(b.visible_tasks(tasks, query="ログ")) == ["b2"]
    assert ids(b.visible_tasks(tasks, query="GAM")) == ["c3"]
    assert ids(b.visible_tasks(tasks, sort_key="status", reverse=False)) == ["c3", "b2", "a1"]
    assert ids(b.visible_tasks(tasks, sort_key="progress", reverse=True)) == ["a1", "b2", "c3"]

    # サマリー (平均は未完了だけ)
    rows = b.ai_summary({"ais": ["Claude", "Muse", "Gemini"], "tasks": tasks})
    assert rows[0] == ("Claude", 2, 0, 0, 0, 1)
    assert b.summary_text(rows[1]) == "Muse  1件  平均20%  停滞1"
    assert b.summary_text(rows[2]) == "Gemini  0件"

    # 表示用
    assert b.progress_bar(40) == "████░░░░░░  40%"
    assert b.local_time("bad") == "bad"
    assert len(b.local_time("2026-10-29T06:48:07Z")) == len("10/29 15:48")
    prompt = b.request_prompt(tasks[1])
    assert "Museさん" in prompt and "--update b2" in prompt and "ログ調査" in prompt and "メモ:" not in prompt

    print("OK")


if __name__ == "__main__":
    main()
