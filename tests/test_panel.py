"""Claude panel core (pure Python): CLI discovery, argv, output parsing and a turn end to end."""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "rhino", "panel"))

import claude_panel_core as core  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FILES = {"mcp_config": "C:/x/mcp.json", "system_prompt": "C:/x/system-prompt.txt"}


def jl(*objs):
    return [json.dumps(o) for o in objs]


class Discovery(unittest.TestCase):
    def test_override_wins_and_must_exist(self):
        env = {"CLAUDE_PANEL_CLAUDE": "D:/c/claude.exe"}
        self.assertEqual(core.find_cli("claude", env, which=lambda n: "/path/claude",
                                       exists=lambda p: p == "D:/c/claude.exe"), "D:/c/claude.exe")
        self.assertIsNone(core.find_cli("claude", env, which=lambda n: "/path/claude", exists=lambda p: False))

    def test_path_then_install_folders(self):
        env = {"USERPROFILE": "C:/Users/u", "APPDATA": "C:/Users/u/AppData/Roaming"}
        self.assertEqual(core.find_cli("claude", env, which=lambda n: "/bin/claude", exists=lambda p: False),
                         "/bin/claude")
        local = os.path.join("C:/Users/u", ".local", "bin", "claude.exe")
        self.assertEqual(core.find_cli("claude", env, which=lambda n: None, exists=lambda p: p == local), local)
        npm = os.path.join("C:/Users/u/AppData/Roaming", "npm", "codex.cmd")
        self.assertEqual(core.find_cli("codex", env, which=lambda n: None, exists=lambda p: p == npm), npm)

    def test_available_backends_keeps_claude_first(self):
        found = core.available_backends({}, which=lambda n: "/bin/" + n, exists=lambda p: False)
        self.assertEqual(list(found), ["claude", "codex"])
        self.assertEqual(core.available_backends({}, which=lambda n: None, exists=lambda p: False), {})


class Commands(unittest.TestCase):
    def test_claude_argv(self):
        argv = core.build_command("claude", "claude.exe", REPO, FILES)
        self.assertEqual(argv[:2], ["claude.exe", "-p"])
        self.assertIn("stream-json", argv)
        self.assertEqual(argv[argv.index("--mcp-config") + 1], FILES["mcp_config"])
        self.assertIn("--strict-mcp-config", argv)
        self.assertEqual(argv[argv.index("--allowedTools") + 1], "mcp__rhino")
        self.assertNotIn("--resume", argv)
        resumed = core.build_command("claude", "claude.exe", REPO, FILES, session_id="abc", model="sonnet")
        self.assertEqual(resumed[resumed.index("--resume") + 1], "abc")
        self.assertEqual(resumed[resumed.index("--model") + 1], "sonnet")

    def test_codex_argv(self):
        argv = core.build_command("codex", "codex.exe", REPO, FILES)
        self.assertEqual(argv[:2], ["codex.exe", "exec"])
        self.assertEqual(argv[-1], "-")
        self.assertIn("--json", argv)
        self.assertTrue(any(a.startswith("mcp_servers.rhino.args=[") and "launch-router.mjs" in a for a in argv))
        resumed = core.build_command("codex", "codex.exe", REPO, FILES, session_id="t1")
        self.assertEqual(resumed[2:4], ["resume", "t1"])

    def test_unknown_backend(self):
        with self.assertRaises(ValueError):
            core.build_command("gemini", "x", REPO, FILES)

    def test_support_files(self):
        d = tempfile.mkdtemp()
        try:
            files = core.write_support_files(os.path.join(d, "panel"), REPO)
            with open(files["mcp_config"], encoding="utf-8") as f:
                cfg = json.load(f)
            server = cfg["mcpServers"]["rhino"]
            self.assertTrue(server["args"][0].endswith(os.path.join("scripts", "launch-router.mjs")))
            self.assertTrue(os.path.isfile(server["args"][0]))
            with open(files["system_prompt"], encoding="utf-8") as f:
                self.assertIn("Rhino", f.read())
        finally:
            shutil.rmtree(d)


class Parsing(unittest.TestCase):
    def test_claude_stream(self):
        lines = jl(
            {"type": "system", "subtype": "init", "session_id": "s1"},
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "mcp__rhino__build_model", "input": {}}]}},
            {"type": "user", "message": {"content": []}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "Fatto."}]}},
            {"type": "result", "subtype": "success", "is_error": False, "session_id": "s1",
             "total_cost_usd": 0.01, "duration_ms": 900, "num_turns": 2},
        ) + ["not json", ""]
        events = [e for line in lines for e in core.parse_line("claude", line)]
        self.assertEqual(events[0], ("session", "s1"))
        self.assertIn(("tool", "build_model"), events)
        self.assertIn(("text", "Fatto."), events)
        self.assertEqual(events[-1][0], "done")
        self.assertEqual(events[-1][1]["cost_usd"], 0.01)

    def test_claude_error_result(self):
        ev = core.parse_line("claude", jl({"type": "result", "is_error": True, "result": "Not logged in"})[0])
        self.assertEqual(ev[0], ("error", "Not logged in"))
        self.assertEqual(ev[-1][0], "done")

    def test_codex_stream(self):
        lines = jl(
            {"type": "thread.started", "thread_id": "t1"},
            {"type": "item.started", "item": {"type": "mcp_tool_call", "server": "rhino", "tool": "get_context"}},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "Ciao"}},
            {"type": "turn.completed", "usage": {"input_tokens": 5}},
            {"type": "turn.failed", "error": {"message": "boom"}},
        )
        events = [e for line in lines for e in core.parse_line("codex", line)]
        self.assertEqual(events, [("session", "t1"), ("tool", "get_context"), ("text", "Ciao"),
                                  ("done", {"usage": {"input_tokens": 5}}), ("error", "boom")])


class FakeProc:
    def __init__(self, out, err=b"", code=0):
        self.stdin = io.BytesIO()
        self.stdin.close = lambda: None
        self.stdout = io.BytesIO(out)
        self.stderr = io.BytesIO(err)
        self.code = code
        self.killed = False

    def poll(self):
        return None

    def wait(self):
        return self.code

    def kill(self):
        self.killed = True


class Turn(unittest.TestCase):
    def run_turn(self, proc, prompt="ciao"):
        seen, calls = [], []

        def popen(argv, **kw):
            calls.append((argv, kw))
            return proc
        conv = core.Conversation("claude", "claude.exe", REPO, FILES, cwd="C:/w", popen=popen)
        conv.send(prompt, lambda k, v: seen.append((k, v, conv.busy)), background=False)
        return conv, seen, calls

    def test_turn_streams_events_and_keeps_session(self):
        out = "\n".join(jl(
            {"type": "system", "subtype": "init", "session_id": "s9"},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "Ok"}]}},
            {"type": "result", "is_error": False, "session_id": "s9", "total_cost_usd": 0.002},
        )).encode()
        proc = FakeProc(out)
        conv, seen, calls = self.run_turn(proc, "disegna un cubo")
        self.assertEqual(proc.stdin.getvalue().decode(), "disegna un cubo")
        self.assertEqual(calls[0][1]["stdin"], subprocess.PIPE)
        self.assertEqual(calls[0][1]["cwd"], "C:/w")
        self.assertEqual([(k, v) for k, v, _ in seen][0], ("text", "Ok"))
        kind, info, busy = seen[-1]
        self.assertEqual(kind, "done")
        self.assertEqual(info["cost_usd"], 0.002)
        self.assertFalse(busy, "done must arrive after the process is released")
        self.assertEqual(conv.session_id, "s9")
        # the next turn resumes the same session
        conv._popen = lambda argv, **kw: calls.append((argv, kw)) or FakeProc(b"")
        conv.send("e ora?", lambda *a: None, background=False)
        self.assertEqual(calls[-1][0][calls[-1][0].index("--resume") + 1], "s9")

    def test_crash_reports_stderr(self):
        conv, seen, _ = self.run_turn(FakeProc(b"", b"warning\nError: not logged in\n", code=1))
        self.assertEqual([(k, v) for k, v, _ in seen], [("error", "Error: not logged in"), ("done", {})])
        self.assertFalse(conv.busy)

    def test_error_repeating_the_text_is_shown_once(self):
        out = "\n".join(jl(
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "Not logged in"}]}},
            {"type": "result", "is_error": True, "result": "Not logged in"},
        )).encode()
        _, seen, _ = self.run_turn(FakeProc(out))
        self.assertEqual([k for k, _, _ in seen], ["text", "done"])

    def test_reset_forgets_session(self):
        conv, _, _ = self.run_turn(FakeProc(b'{"type":"result","session_id":"s1"}'))
        self.assertEqual(conv.session_id, "s1")
        conv.reset()
        self.assertIsNone(conv.session_id)


if __name__ == "__main__":
    unittest.main()
