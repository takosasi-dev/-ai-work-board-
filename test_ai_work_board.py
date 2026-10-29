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
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        raw["tasks"][0]["progress"] = "30"
        raw["tasks"][1]["progress"] = "abc"
        raw["tasks"].append({"progress": None, "ai": "Copilot"})  # id もタイトルも無い1件
        with open(path, "w", encoding="utf-8", newline="") as f:
            json.dump(raw, f, ensure_ascii=False)
        data = b.load_board(path)
        assert [t["progress"] for t in data["tasks"][:2]] == [30, 0]
        assert data["tasks"][-1]["title"] == "(無題)" and "Copilot" in data["ais"]
        b.visible_tasks(data["tasks"], query="x")
        b.ai_summary(data)

        # MCP: -X utf8 も PYTHONIOENCODING も付けない (Claude などが素の python で起動したときと同じ)
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
        msgs = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "add_task", "arguments": {"title": "MCPで足した仕事", "ai": "Claude", "request": "日本語の依頼"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "update_task", "arguments": {"id": "nope"}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
             "params": {"name": "update_task", "arguments": {"id": "sample-m", "status": "bad"}}},
            {"jsonrpc": "2.0", "id": 6, "method": "nope"},
        ]
        out = subprocess.run([sys.executable, os.path.join(HERE, "ai_work_board.py"), "--data", path, "--mcp"],
                             input="".join(json.dumps(m, ensure_ascii=False) + "\n" for m in msgs).encode("utf-8"),
                             capture_output=True, env=env, timeout=30)
        assert out.returncode == 0, out.stderr.decode("utf-8", "replace")
        replies = [json.loads(l) for l in out.stdout.decode("utf-8").splitlines()]
        assert [r["id"] for r in replies] == [1, 2, 3, 4, 5, 6]  # 通知には返事しない
        assert replies[0]["result"]["serverInfo"]["version"] == b.VERSION
        assert {t["name"] for t in replies[1]["result"]["tools"]} == {t["name"] for t in b.MCP_TOOLS}
        added = json.loads(replies[2]["result"]["content"][0]["text"])
        assert added["title"] == "MCPで足した仕事" and not replies[2]["result"].get("isError")
        assert replies[3]["result"]["isError"] and replies[4]["result"]["isError"]
        assert replies[5]["error"]["code"] == -32601
        data = b.load_board(path)
        assert b.find_task(data, added["id"])["request"] == "日本語の依頼"
        assert b.find_task(data, "sample-muse-1")["status"] != "bad"
        done = json.loads(b.mcp_call(path, "complete_task", {"id": added["id"], "notes": "済み"}))
        assert done["status"] == "done" and b.find_task(b.load_board(path), added["id"])["progress"] == 100
        assert {t["id"] for t in json.loads(b.mcp_call(path, "list_tasks", {"status": "done"}))} == {added["id"], new_id}

        # 本物の相手のように1通ずつ返事を待つ。途中で相手が切れても例外を出さずに終わる
        p = subprocess.Popen([sys.executable, os.path.join(HERE, "ai_work_board.py"), "--data", path, "--mcp"],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        for i, m in enumerate((msgs[0], msgs[2]), 1):
            p.stdin.write((json.dumps(m) + "\n").encode())
            p.stdin.flush()
            assert json.loads(p.stdout.readline())["id"] == m["id"], i
        p.stdout.close()
        p.stdin.write((json.dumps(msgs[2]) + "\n").encode())
        p.stdin.close()
        assert p.wait(timeout=30) == 0
        assert p.stderr.read() == b""

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
    assert rows[0] == {"ai": "Claude", "count": 2, "open": 1, "avg": 0, "by": {"done": 1, "todo": 1}}
    assert b.lane_detail(rows[1]) == "件  平均 20%\n停滞 1"
    assert b.lane_detail(rows[2]) == "件\n"
    assert b.lane_detail(b.summarize("x", tasks[:1])) == "件  すべて完了\n完了 1"

    # AIの色: 決まった3つ以外は順に割り当て
    ais = ["Claude", "Copilot", "Grok"]
    assert b.ai_color(ais, "Claude") == "#E0A458"
    assert b.ai_color(ais, "Grok") == b.EXTRA_AI_COLORS[1]
    assert b.ai_color(ais, "未登録") == b.EXTRA_AI_COLORS[0]

    # 表示用
    assert b.local_time("bad") == "bad"
    assert len(b.local_time("2026-10-29T06:48:07Z")) == len("10/29 15:48")
    prompt = b.request_prompt(tasks[1])
    assert "Museさん" in prompt and "--update b2" in prompt and "ログ調査" in prompt and "メモ:" not in prompt

    print("OK")


if __name__ == "__main__":
    main()
