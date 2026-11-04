#! python3
"""ClaudePanel: a dockable chat panel inside Rhino 8 that talks to the user's own AI CLI.

Run this file once (_-RunPythonScript, or the Script Editor): it adds the `ClaudePanel` alias.
After that `ClaudePanel` shows the panel docked under Layers, and hides it when it is visible.
The panel stays a normal Rhino panel: drag its tab to dock it elsewhere, float it or close it.

Replies come from `claude` (Claude Code, your Claude plan) or `codex` (Codex, your ChatGPT
plan) running on this computer, with this plugin's Rhino MCP server so they can edit the model.
"""
import os
import sys
import tempfile

import clr
import System
import Eto.Drawing as ed
import Eto.Forms as ef
import Rhino
import scriptcontext as sc
from Rhino.UI import Panels, PanelIds

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import importlib  # noqa: E402
import claude_panel_core as core  # noqa: E402
importlib.reload(core)  # pick up edits without restarting Rhino

PANEL_ID = "6f1d3c2a-9b7e-4c55-8a1e-2c0b5e7d9a42"
CAPTION = "Claude"
ALIAS = "ClaudePanel"
SCRIPT_EDITOR_PLUGIN = "c9cba87a-23ce-4f15-a918-97645c05cde7"  # RhinoCodePlugin hosts the panel
KEY = "claude_rhino_panel."  # scriptcontext.sticky prefix: survives re-runs in one Rhino session
SUPPORT = os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "claude-rhino-panel")

T = clr.GetClrType


def host_type():
    """A real .NET Eto panel type with a GuidAttribute, which Rhino's panel system requires
    and Python classes cannot carry. Its constructor calls the static `Created` callback, where
    Python fills in the content. Built once per Rhino session with Reflection.Emit."""
    t = sc.sticky.get(KEY + "type")
    if t is not None:
        return t
    from System.Reflection import AssemblyName, CallingConventions, FieldAttributes, MethodAttributes, TypeAttributes
    from System.Reflection.Emit import AssemblyBuilder, AssemblyBuilderAccess, CustomAttributeBuilder, OpCodes

    asm = AssemblyBuilder.DefineDynamicAssembly(AssemblyName("ClaudeRhinoPanel"), AssemblyBuilderAccess.Run)
    tb = asm.DefineDynamicModule("ClaudeRhinoPanel").DefineType(
        "ClaudeRhino.ClaudePanel", TypeAttributes.Public | TypeAttributes.Class, T(ef.Panel))
    guid_ctor = T(System.Runtime.InteropServices.GuidAttribute).GetConstructor(
        System.Array[System.Type]([T(System.String)]))
    tb.SetCustomAttribute(CustomAttributeBuilder(guid_ctor, System.Array[System.Object]([PANEL_ID])))
    action = T(System.Action[System.Object])
    created = tb.DefineField("Created", action, FieldAttributes.Public | FieldAttributes.Static)
    il = tb.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard, System.Type.EmptyTypes).GetILGenerator()
    il.Emit(OpCodes.Ldarg_0)
    il.Emit(OpCodes.Call, T(ef.Panel).GetConstructor(System.Type.EmptyTypes))
    skip = il.DefineLabel()
    il.Emit(OpCodes.Ldsfld, created)
    il.Emit(OpCodes.Brfalse_S, skip)
    il.Emit(OpCodes.Ldsfld, created)
    il.Emit(OpCodes.Ldarg_0)
    il.Emit(OpCodes.Callvirt, action.GetMethod("Invoke"))
    il.MarkLabel(skip)
    il.Emit(OpCodes.Ret)
    t = tb.CreateType()
    sc.sticky[KEY + "type"] = t
    return t


def ui(fn):
    """Run fn on Rhino's UI thread (CLI events arrive on a worker thread)."""
    ef.Application.Instance.AsyncInvoke(System.Action(fn))


class ChatView:
    """The panel content. One conversation per backend; switching backend starts a new one."""

    def __init__(self, panel):
        self.panel = panel
        self.backends = core.available_backends()
        self.files = core.write_support_files(SUPPORT, REPO)
        self.conv = None
        self.speaker_open = False

        self.picker = ef.DropDown()
        for kind in self.backends:
            self.picker.Items.Add(core.LABELS[kind], kind)
        if self.backends:
            self.picker.SelectedIndex = 0
        self.picker.SelectedIndexChanged += lambda s, e: self.new_chat()

        self.new_btn = self._button("Nuova", "Nuova conversazione", lambda: self.new_chat())
        self.transcript = ef.TextArea()
        self.transcript.ReadOnly = True
        self.transcript.Wrap = True
        self.input = ef.TextArea()
        self.input.Wrap = True
        self.input.Size = ed.Size(-1, 60)
        self.input.KeyDown += self.on_key
        self.status = ef.Label()
        self.stop_btn = self._button("Stop", "Interrompi la risposta", lambda: self.stop())
        self.send_btn = self._button("Invia", "Invia (Invio). Maiusc+Invio va a capo", lambda: self.send())

        top = ef.TableLayout()
        top.Spacing = ed.Size(4, 0)
        top.Rows.Add(ef.TableRow(ef.TableCell(self.picker, True), ef.TableCell(self.new_btn)))
        bottom = ef.TableLayout()
        bottom.Spacing = ed.Size(4, 0)
        bottom.Rows.Add(ef.TableRow(ef.TableCell(self.status, True), ef.TableCell(self.stop_btn),
                                    ef.TableCell(self.send_btn)))
        layout = ef.TableLayout()
        layout.Padding = ed.Padding(4)
        layout.Spacing = ed.Size(4, 4)
        layout.Rows.Add(ef.TableRow(ef.TableCell(top)))
        grow = ef.TableRow(ef.TableCell(self.transcript))
        grow.ScaleHeight = True
        layout.Rows.Add(grow)
        layout.Rows.Add(ef.TableRow(ef.TableCell(self.input)))
        layout.Rows.Add(ef.TableRow(ef.TableCell(bottom)))
        panel.Content = layout

        if not self.backends:
            self.append("Nessuna CLI trovata. Installa Claude Code (`claude`) o Codex (`codex`) "
                        "ed esegui il login con il tuo piano, poi riapri il pannello.\n")
        self.new_chat()

    @staticmethod
    def _button(text, tip, fn):
        b = ef.Button()
        b.Text = text
        b.ToolTip = tip
        b.Click += lambda s, e: fn()
        return b

    # --- state -----------------------------------------------------------------------------
    def kind(self):
        return self.picker.SelectedKey if self.backends else None

    def new_chat(self):
        if self.conv is not None:
            self.conv.reset()
        kind = self.kind()
        self.conv = core.Conversation(kind, self.backends[kind], REPO, self.files, cwd=SUPPORT) if kind else None
        if kind:
            self.transcript.Text = ""
        self.set_busy(False, "Pronto" if kind else "")

    def set_busy(self, busy, text):
        self.status.Text = text
        self.send_btn.Enabled = bool(self.conv) and not busy
        self.stop_btn.Enabled = busy
        self.picker.Enabled = not busy
        self.new_btn.Enabled = not busy

    def append(self, text):
        self.transcript.Append(text, True)

    # --- actions -----------------------------------------------------------------------------
    def on_key(self, sender, e):
        if e.Key == ef.Keys.Enter and not e.Shift:
            e.Handled = True
            self.send()

    def send(self):
        prompt = (self.input.Text or "").strip()
        if not prompt or self.conv is None or self.conv.busy:
            return
        self.input.Text = ""
        self.append(("\n" if self.transcript.Text else "") + "Tu: " + prompt + "\n")
        self.speaker_open = False
        self.set_busy(True, "Sto pensando...")
        try:
            self.conv.send(prompt, lambda k, v: ui(lambda: self.on_event(k, v)))
        except Exception as ex:
            self.on_event("error", str(ex))
            self.on_event("done", {})

    def stop(self):
        if self.conv is not None:
            self.conv.stop()

    def on_event(self, kind, value):
        name = "Claude" if self.conv and self.conv.backend == "claude" else "ChatGPT"
        if kind == "text":
            self.append(("" if self.speaker_open else name + ": ") + value.strip() + "\n")
            self.speaker_open = True
        elif kind == "tool":
            self.append("  · " + value + "\n")
            self.status.Text = "Uso " + value + "..."
        elif kind == "error":
            self.append("Errore: " + value + "\n")
        elif kind == "done":
            cost = value.get("cost_usd") if isinstance(value, dict) else None
            self.set_busy(False, "Pronto" + (" (≈ $%.3f)" % cost if cost else ""))


def build(panel):
    try:
        view = ChatView(panel)
        sc.sticky[KEY + "view"] = view
    except Exception as ex:  # show the problem instead of an empty panel
        lbl = ef.Label()
        lbl.Text = "Pannello Claude: errore di avvio\n%s" % ex
        lbl.Wrap = ef.WrapMode.Word
        panel.Content = lbl


def dock_under_layers(panel_type):
    """Open the panel in its own dock bar and stack that bar right below the Layers panel.

    RhinoCommon can open a panel in a new dock bar but cannot place a bar under another one,
    so this uses Rhino 8's internal dock-site classes (Rhino.UI.Internal.TabPanels) through
    reflection. If they change in a later Rhino, the panel simply stays where Rhino put it."""
    bar_id = Panels.OpenPanel(System.Guid.NewGuid(), panel_type, True)
    try:
        return _stack_under(bar_id, Panels.PanelDockBar(PanelIds.Layers))
    except Exception as ex:
        print("ClaudePanel: aggancio sotto Layer non riuscito (%s); trascina la scheda dove vuoi." % ex)
        return False


def _stack_under(bar_id, layers_bar_id):
    from System.Reflection import BindingFlags as BF
    fl = BF.Public | BF.NonPublic | BF.Instance

    def call(obj, name, *args):
        return obj.GetType().GetMethod(name, fl).Invoke(obj, System.Array[System.Object](list(args)))

    def prop(obj, name):
        return obj.GetType().GetProperty(name, fl).GetValue(obj)

    asm = next(a for a in System.AppDomain.CurrentDomain.GetAssemblies() if a.GetName().Name == "Rhino.UI")
    bars = asm.GetType("Rhino.UI.Internal.TabPanels.TabPanelDockBars", True)
    find = bars.GetMethod("FromDockBarId")
    ours = find.Invoke(None, System.Array[System.Object]([bar_id]))
    layers = find.Invoke(None, System.Array[System.Object]([layers_bar_id]))
    doc = Rhino.RhinoDoc.ActiveDoc
    sn = System.UInt32(doc.RuntimeSerialNumber)
    ours.Dock(sn)  # out of its floating window, onto Rhino's default (right) dock site
    site = call(layers, "TryGetDockSite", sn) if layers is not None else None
    if site is None:  # Layers is floating or closed: docked on the right is the best we can do
        return False
    bands = prop(site, "Bands")
    for b in range(bands.Count):
        items = prop(bands[b], "Items")
        for i in range(items.Count):
            if prop(items[i], "DockBar").Id == layers_bar_id:
                if call(ours, "TryGetDockSite", sn) is not None:
                    call(call(ours, "TryGetDockSite", sn), "RemoveDockBar", ours)
                call(site, "InsertBarItem", ours, b, i + 1, True)
                return True
    return False


def ensure_alias():
    aliases = Rhino.ApplicationSettings.CommandAliasList
    macro = '! _-RunPythonScript "%s"' % os.path.abspath(__file__)
    if aliases.GetMacro(ALIAS) != macro:
        if aliases.IsAlias(ALIAS):
            aliases.Delete(ALIAS)
        aliases.Add(ALIAS, macro)
        print("Alias %s creato: scrivilo nella riga di comando per mostrare/nascondere il pannello." % ALIAS)


def ensure_cleanup():
    if sc.sticky.get(KEY + "closing"):
        return

    def on_closing(sender, e):
        view = sc.sticky.get(KEY + "view")
        if view is not None:
            view.stop()
    Rhino.RhinoApp.Closing += on_closing
    sc.sticky[KEY + "closing"] = True


def toggle():
    t = host_type()
    t.GetField("Created").SetValue(None, System.Action[System.Object](build))
    if not sc.sticky.get(KEY + "registered"):
        icon = System.Drawing.Icon(os.path.join(HERE, "claude.ico")) if os.path.isfile(
            os.path.join(HERE, "claude.ico")) else System.Drawing.SystemIcons.Information
        host = Rhino.PlugIns.PlugIn.Find(System.Guid(SCRIPT_EDITOR_PLUGIN))
        Panels.RegisterPanel(host, t, CAPTION, icon)
        sc.sticky[KEY + "registered"] = True
    ensure_alias()
    ensure_cleanup()
    pid = System.Guid(PANEL_ID)
    if Panels.IsPanelVisible(pid):
        Panels.ClosePanel(pid)
        return "hidden"
    if Panels.PanelDockBar(pid) == System.Guid.Empty and not sc.sticky.get(KEY + "placed"):
        dock_under_layers(t)
        sc.sticky[KEY + "placed"] = True
    else:
        Panels.OpenPanel(pid, True)
    return "shown"


if __name__ == "__main__":
    toggle()
