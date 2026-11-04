"""Claude panel core: finds the user's local AI CLI, runs one turn and parses its output.

Pure Python 3, no Rhino imports, so it is testable outside Rhino. Each person uses their own
CLI and their own plan (Claude Code for a Claude plan, Codex for a ChatGPT plan): no shared
server and no API key. The CLI gets this plugin's Rhino MCP server, so it can act on the model.
"""
import glob
import json
import os
import shutil
import subprocess
import threading

SERVER = "rhino"  # MCP server name we hand to the CLI; tools become mcp__rhino__*
# The only tools the panel's model may use: the launcher's SAFE_TOOLS (scripts/spec-tool.mjs).
# The launcher runs with --safe and enforces the same list for Codex, which has no per-tool flag.
PANEL_TOOLS = ("build_model", "check_model", "get_context", "list_objects", "get_selection",
               "set_selection", "get_viewport_image", "set_camera", "zoom_to_layer", "zoom_to_object",
               "set_layer_material", "list_slots", "ask_user", "detect_facade")

SYSTEM_PROMPT = (
    "You are answering from a small chat panel docked inside Rhino 8. The user sees plain text "
    "only: answer briefly, in the user's language, without Markdown tables. Use the rhino MCP "
    "tools to read or change the open document. Do not request viewport images unless the user "
    "asks for one: verify geometry numerically instead."
)

BACKENDS = ("claude", "codex")
LABELS = {"claude": "Claude (Claude Code)", "codex": "ChatGPT (Codex)"}


def _candidates(kind, env):
    home = env.get("USERPROFILE") or env.get("HOME") or os.path.expanduser("~")
    appdata = env.get("APPDATA", os.path.join(home, "AppData", "Roaming"))
    local = env.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
    if kind == "claude":
        pats = [
            os.path.join(home, ".local", "bin", "claude.exe"),
            os.path.join(home, ".local", "bin", "claude"),
            os.path.join(appdata, "npm", "claude.cmd"),
            "/opt/homebrew/bin/claude",
            "/usr/local/bin/claude",
        ]
    else:
        pats = [
            os.path.join(local, "OpenAI", "Codex", "bin", "**", "codex.exe"),
            os.path.join(appdata, "npm", "codex.cmd"),
            "/opt/homebrew/bin/codex",
            "/usr/local/bin/codex",
            "/Applications/ChatGPT.app/Contents/Resources/codex",
        ]
    for p in pats:
        if "*" in p:
            yield from sorted(glob.glob(p, recursive=True), reverse=True)
        else:
            yield p


def find_cli(kind, env=None, which=shutil.which, exists=os.path.isfile):
    """Path of the `claude` or `codex` executable, or None.

    Order: $CLAUDE_PANEL_<KIND> override, PATH, then the usual install folders (Rhino is often
    started from a shortcut whose PATH lacks ~/.local/bin or %APPDATA%/npm)."""
    env = os.environ if env is None else env
    override = env.get("CLAUDE_PANEL_" + kind.upper())
    if override:
        return override if exists(override) else None
    found = which(kind)
    if found:
        return found
    for p in _candidates(kind, env):
        if exists(p):
            return p
    return None


def available_backends(env=None, which=shutil.which, exists=os.path.isfile):
    """{backend: path} for every installed CLI, Claude first."""
    out = {}
    for kind in BACKENDS:
        path = find_cli(kind, env, which, exists)
        if path:
            out[kind] = path
    return out


def mcp_launcher(repo_root):
    """Command that starts this plugin's Rhino MCP server (the McNeel router wrapper)."""
    node = shutil.which("node") or "node"
    # --safe: the panel's model gets only modelling and read tools, never run_python / run_csharp /
    # run_command, so text inside a document can't talk it into running code.
    return [node, os.path.join(repo_root, "scripts", "launch-router.mjs"), "--safe"]


def mcp_config_json(repo_root):
    cmd = mcp_launcher(repo_root)
    return json.dumps({"mcpServers": {SERVER: {"command": cmd[0], "args": cmd[1:]}}})


def _toml_str(s):
    return json.dumps(s)  # a JSON string is a valid TOML basic string


def write_support_files(folder, repo_root):
    """Write the MCP config and system prompt the CLIs read, return their paths.

    Files instead of inline arguments: npm installs are .cmd shims, and cmd.exe mangles JSON."""
    os.makedirs(folder, exist_ok=True)
    files = {"mcp_config": os.path.join(folder, "mcp.json"),
             "system_prompt": os.path.join(folder, "system-prompt.txt")}
    with open(files["mcp_config"], "w", encoding="utf-8") as f:
        f.write(mcp_config_json(repo_root))
    with open(files["system_prompt"], "w", encoding="utf-8") as f:
        f.write(SYSTEM_PROMPT)
    return files


def build_command(backend, exe, repo_root, files, session_id=None, model=None):
    """argv for one turn. The prompt always goes through stdin (no quoting or length issues)."""
    if backend == "claude":
        argv = [
            exe, "-p",
            "--output-format", "stream-json", "--verbose",
            "--mcp-config", files["mcp_config"], "--strict-mcp-config",
            "--allowedTools", ",".join("mcp__%s__%s" % (SERVER, t) for t in PANEL_TOOLS),
            "--append-system-prompt-file", files["system_prompt"],
        ]
        if model:
            argv += ["--model", model]
        if session_id:
            argv += ["--resume", session_id]
        return argv
    if backend == "codex":
        cmd = mcp_launcher(repo_root)
        argv = [exe, "exec"]
        if session_id:
            argv += ["resume", session_id]
        argv += [
            "--json", "--skip-git-repo-check",
            "-c", "mcp_servers.%s.command=%s" % (SERVER, _toml_str(cmd[0])),
            "-c", "mcp_servers.%s.args=[%s]" % (SERVER, ",".join(_toml_str(a) for a in cmd[1:])),
            "-c", "model_instructions_file=" + _toml_str(files["system_prompt"]),
        ]
        if model:
            argv += ["-m", model]
        return argv + ["-"]
    raise ValueError("unknown backend: %r" % backend)


def _short_tool(name):
    prefix = "mcp__%s__" % SERVER
    return name[len(prefix):] if name.startswith(prefix) else name


def parse_line(backend, line):
    """Turn one JSON output line into a list of events:
    ("session", id) ("text", str) ("tool", name) ("done", info dict) ("error", str)."""
    line = line.strip()
    if not line.startswith("{"):
        return []
    try:
        msg = json.loads(line)
    except ValueError:
        return []
    t = msg.get("type")
    ev = []
    if backend == "claude":
        if t == "system" and msg.get("subtype") == "init" and msg.get("session_id"):
            ev.append(("session", msg["session_id"]))
        elif t == "assistant":
            for block in (msg.get("message") or {}).get("content") or []:
                if block.get("type") == "text" and block.get("text"):
                    ev.append(("text", block["text"]))
                elif block.get("type") == "tool_use":
                    ev.append(("tool", _short_tool(block.get("name", "?"))))
        elif t == "result":
            if msg.get("session_id"):
                ev.append(("session", msg["session_id"]))
            if msg.get("is_error"):
                ev.append(("error", str(msg.get("result") or msg.get("subtype") or "error")))
            ev.append(("done", {"cost_usd": msg.get("total_cost_usd"),
                                "duration_ms": msg.get("duration_ms"),
                                "turns": msg.get("num_turns")}))
    else:  # codex exec --json
        item = msg.get("item") or {}
        if t == "thread.started" and msg.get("thread_id"):
            ev.append(("session", msg["thread_id"]))
        elif t == "item.started" and item.get("type") == "mcp_tool_call":
            ev.append(("tool", item.get("tool", "?")))
        elif t == "item.completed" and item.get("type") == "agent_message" and item.get("text"):
            ev.append(("text", item["text"]))
        elif t == "turn.completed":
            ev.append(("done", {"usage": msg.get("usage")}))
        elif t in ("turn.failed", "error"):
            err = msg.get("error") or {}
            ev.append(("error", err.get("message") if isinstance(err, dict) else str(msg.get("message") or err)))
    return ev


class Conversation:
    """One chat thread with one CLI. send() runs a turn on a worker thread and reports events
    through on_event(kind, value) from that thread: the UI must marshal them itself."""

    def __init__(self, backend, exe, repo_root, files, cwd=None, model=None, popen=subprocess.Popen):
        self.backend, self.exe, self.repo_root, self.files = backend, exe, repo_root, files
        self.cwd = cwd or os.path.expanduser("~")
        self.model = model
        self.session_id = None
        self._popen = popen
        self._proc = None
        self._lock = threading.Lock()

    @property
    def busy(self):
        return self._proc is not None

    def reset(self):
        self.stop()
        self.session_id = None

    def stop(self):
        with self._lock:
            proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass

    def send(self, prompt, on_event, background=True):
        if self.busy:
            raise RuntimeError("a reply is still running")
        argv = build_command(self.backend, self.exe, self.repo_root, self.files,
                             self.session_id, self.model)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = self._popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, cwd=self.cwd, creationflags=flags)
        self._proc = proc
        if background:
            threading.Thread(target=self._run, args=(proc, prompt, on_event), daemon=True).start()
        else:
            self._run(proc, prompt, on_event)

    def _run(self, proc, prompt, on_event):
        done = None  # held back until the process is gone, so the UI can send again at once
        last_text = None
        stderr = []
        try:
            t = threading.Thread(target=lambda: stderr.append(proc.stderr.read()), daemon=True)
            t.start()
            proc.stdin.write(prompt.encode("utf-8"))
            proc.stdin.close()
            for raw in iter(proc.stdout.readline, b""):
                for kind, value in parse_line(self.backend, raw.decode("utf-8", "replace")):
                    if kind == "session":
                        self.session_id = value
                        continue
                    if kind == "done":
                        done = value
                    elif kind == "error" and value == last_text:
                        continue  # Claude repeats a failed turn's message as the result
                    else:
                        if kind == "text":
                            last_text = value
                        on_event(kind, value)
            code = proc.wait()
            t.join(2)
            if done is None:
                err = b"".join(x for x in stderr if x).decode("utf-8", "replace").strip()
                on_event("error", err.splitlines()[-1] if err else "CLI exited with code %s" % code)
        except Exception as e:  # never leave the panel stuck on "busy"
            on_event("error", str(e))
        finally:
            with self._lock:
                self._proc = None
        on_event("done", done or {})
