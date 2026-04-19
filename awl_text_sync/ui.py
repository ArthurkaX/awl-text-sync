from __future__ import annotations

import json
import os
import queue
import webbrowser
import threading
import traceback
from pathlib import Path
from typing import Callable

try:
    from . import APP_NAME
    from .call_graph import build_call_graph, default_call_graph_report_path, write_call_graph_report
    from .builder import build_monolith, build_split_import
    from .config import (
        WorkspacePaths,
        resolve_exported_monolith_path,
        resolve_exported_symbols_path,
        resolve_project_symbols_path,
        resolve_workspace,
    )
    from .parser import ParseError
    from .splitter import split_exported_workspace
    from .validator import validate_workspace
    from .writer import ensure_workspace_gitignore
except ImportError:  # pragma: no cover - script/PyInstaller fallback
    from awl_text_sync import APP_NAME
    from awl_text_sync.call_graph import build_call_graph, default_call_graph_report_path, write_call_graph_report
    from awl_text_sync.builder import build_monolith, build_split_import
    from awl_text_sync.config import (
        WorkspacePaths,
        resolve_exported_monolith_path,
        resolve_exported_symbols_path,
        resolve_project_symbols_path,
        resolve_workspace,
    )
    from awl_text_sync.parser import ParseError
    from awl_text_sync.splitter import split_exported_workspace
    from awl_text_sync.validator import validate_workspace
    from awl_text_sync.writer import ensure_workspace_gitignore

DEFAULT_WINDOW_WIDTH = 760
MIN_COLLAPSED_HEIGHT = 280
MIN_EXPANDED_HEIGHT = 520
WORKSPACE_REFRESH_MS = 1000


def _run_split(paths: WorkspacePaths) -> str:
    count = split_exported_workspace(paths)
    return f"Split {count} blocks into {paths.project_blocks_dir}"


def _run_validate(paths: WorkspacePaths) -> str:
    parsed = validate_workspace(paths)
    return f"Validated {len(parsed)} blocks in {paths.project_blocks_dir}"


def _run_build_split(paths: WorkspacePaths) -> str:
    count = build_split_import(paths)
    return f"Built split import set with {count} blocks in {paths.build_split_dir}"


def _run_build_monolith(paths: WorkspacePaths) -> str:
    count = build_monolith(paths)
    return f"Built monolith with {count} blocks at {paths.build_all_blocks}"


def _run_call_graph(paths: WorkspacePaths) -> str:
    parsed = validate_workspace(paths)
    graph = build_call_graph(parsed)
    report_path = default_call_graph_report_path(paths)
    try:
        write_call_graph_report(graph, paths.root, report_path)
    except OSError as exc:
        return f"Call graph report not written: {exc}"
    try:
        webbrowser.open(report_path.resolve().as_uri())
    except Exception:
        pass
    return f"Wrote call graph report to {report_path}"


def _safe_import_tk():
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk

    return tk, filedialog, messagebox, scrolledtext, ttk


def _normalize_workspace_selection(selected: str | Path) -> Path:
    path = Path(selected).resolve()
    if path.name.lower() == "exported":
        return path.parent
    return path


def _ui_state_path() -> Path:
    appdata = os.getenv("APPDATA")
    base_dir = Path(appdata) if appdata else Path.home() / ".config"
    return base_dir / APP_NAME / "ui_state.json"


def _load_ui_state() -> dict[str, object]:
    path = _ui_state_path()
    if not path.exists():
        return {"last_workspace": "", "recent_workspaces": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"last_workspace": "", "recent_workspaces": []}
    if not isinstance(data, dict):
        return {"last_workspace": "", "recent_workspaces": []}
    last_workspace = data.get("last_workspace", "")
    recent_workspaces = data.get("recent_workspaces", [])
    if not isinstance(last_workspace, str):
        last_workspace = ""
    if not isinstance(recent_workspaces, list):
        recent_workspaces = []
    cleaned_recent = [item for item in recent_workspaces if isinstance(item, str) and item.strip()]
    return {"last_workspace": last_workspace, "recent_workspaces": cleaned_recent[:10]}


def _save_ui_state(last_workspace: str, recent_workspaces: list[str]) -> None:
    path = _ui_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_workspace": last_workspace,
        "recent_workspaces": recent_workspaces[:10],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _summarize_workspace(paths: WorkspacePaths) -> tuple[str, bool]:
    exported_present = paths.exported_dir.exists()
    try:
        resolve_exported_monolith_path(paths)
        monolith_ready = True
    except (FileNotFoundError, FileExistsError):
        monolith_ready = False
    try:
        resolve_exported_symbols_path(paths)
        symbols_ready = True
    except (FileNotFoundError, FileExistsError):
        symbols_ready = False
    split_ready = exported_present and monolith_ready and symbols_ready

    project_blocks_present = paths.project_blocks_dir.exists()
    try:
        resolve_project_symbols_path(paths)
        project_symbols_present = True
    except (FileNotFoundError, FileExistsError):
        project_symbols_present = False
    build_ready = project_blocks_present and project_symbols_present

    if split_ready and build_ready:
        summary = "Ready for split, validate, and build."
    elif split_ready:
        summary = "Ready for split. Run Split to create Project/."
    elif exported_present:
        try:
            resolve_exported_monolith_path(paths)
            resolve_exported_symbols_path(paths)
            summary = "Exported/ looks good. Finish Project/ generation by running Split."
        except FileExistsError as exc:
            summary = str(exc)
        except FileNotFoundError:
            summary = "Exported/ found. Add exactly one .AWL file and one .sdf file."
    elif exported_present:
        summary = "Exported/ found. Add exactly one .AWL file and one .sdf file."
    else:
        summary = "Select a workspace root or use Help for the expected folder structure."
    return summary, split_ready


def _help_text() -> str:
    return (
        f"{APP_NAME} works with one workspace folder.\n\n"
        "Workspace folders:\n"
        "- Exported/: files exported from STEP 7\n"
        "- Project/: generated editable files\n"
        "- Build/: generated output files\n\n"
        "How to export from STEP 7:\n"
        "1. Generate source blocks and include all editable blocks.\n"
        "2. Use one source containing all selected blocks.\n"
        "3. Export symbols separately as one .sdf file.\n"
        "4. In the Generate Source Blocks dialog, pay attention to the Addresses option.\n"
        "5. Absolute addresses keep numeric headers.\n"
        "6. Symbolic addresses use symbolic block names.\n"
        f"7. {APP_NAME} supports both modes.\n\n"
        "How to use this app:\n"
        "1. Choose the workspace root folder.\n"
        "2. Put one exported .AWL file and one .sdf file into Exported/.\n"
        "3. Click Split.\n"
        "4. Edit files in Project/Blocks.\n"
        "5. Use Validate, Build Split, or Build Monolith.\n\n"
        "Tip:\n"
        "You may also select the Exported folder itself. The app will use its parent as the workspace root."
    )


def _help_steps() -> list[tuple[str, str]]:
    return [
        (
            "Welcome",
            f"{APP_NAME} works with one workspace folder.\n\n"
            "It helps you split a STEP 7 export into editable files, validate the result, "
            "and build output for import again.",
        ),
        (
            "Workspace",
            "A workspace normally contains three folders:\n\n"
            "- Exported/: files exported from STEP 7\n"
            "- Project/: generated editable files\n"
            "- Build/: generated output files\n\n"
            "You select the workspace root folder in the main window.",
        ),
        (
            "Export From STEP 7",
            "In STEP 7, generate source blocks and include all editable blocks.\n\n"
            "Use one source containing all selected blocks.\n"
            "Export symbols separately as one .sdf file.",
        ),
        (
            "Address Mode",
            "In the Generate Source Blocks dialog, pay attention to Addresses:\n\n"
            "- Absolute: numeric block headers\n"
            "- Symbolic: symbolic block headers\n\n"
            f"{APP_NAME} supports both modes.",
        ),
        (
            "Prepare Files",
            "Put one exported .AWL file and one .sdf file into Exported/.\n\n"
            "You may also select the Exported folder itself in the app. "
            "The app will use its parent as the workspace root.",
        ),
        (
            "Split",
            "Click Split.\n\n"
            "The app creates editable AWL block files in Project/Blocks and copies "
            "the symbol file into Project/Symbols.",
        ),
        (
            "Edit And Build",
            "Edit files in Project/Blocks.\n\n"
            "Then use:\n"
            "- Validate: check the workspace\n"
            "- Build Split: create split import output\n"
            "- Build Monolith: rebuild one ALL_BLOCKS.AWL file",
        ),
    ]


def _workspace_structure_description(paths: WorkspacePaths) -> str:
    return (
        f"Create standard workspace folders in:\n{paths.root}\n\n"
        "Folders:\n"
        f"- Exported: put exactly one .AWL export and one .sdf symbols file here\n"
        f"- Project/Blocks: generated editable AWL block files\n"
        f"- Project/Symbols: copied symbol files used by validate/build\n"
        f"- Build/Monolith: rebuilt ALL_BLOCKS.AWL output\n"
        f"- Build/SplitImport: split import-ready output\n\n"
        "Do you want to create this folder structure now?"
    )


class SyncUiApp:
    def __init__(self, root, initial_workspace: Path):
        tk, filedialog, messagebox, scrolledtext, ttk = _safe_import_tk()
        self.tk = tk
        self.filedialog = filedialog
        self.messagebox = messagebox
        self.scrolledtext = scrolledtext
        self.ttk = ttk

        self.root = root
        self.root.title(APP_NAME)
        self.root.resizable(True, True)

        self.ui_state = _load_ui_state()
        self.recent_workspaces: list[str] = list(self.ui_state.get("recent_workspaces", []))
        initial_value = self._initial_workspace_value(initial_workspace)
        self.workspace_var = tk.StringVar(value=initial_value)
        self.status_var = tk.StringVar(value="Ready")
        self.workspace_state_var = tk.StringVar()
        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.is_busy = False
        self.log_visible = False
        self.buttons = []
        self.action_buttons: dict[str, object] = {}
        self.prompted_workspace_paths: set[Path] = set()

        self._build_layout()
        self._resize_window()
        self.workspace_var.trace_add("write", self._on_workspace_changed)
        self.root.bind("<FocusIn>", self._on_app_focus)
        self._refresh_workspace_state()
        self.root.after(WORKSPACE_REFRESH_MS, self._poll_workspace_state)
        self.root.after(100, self._poll_log_queue)

    def _build_layout(self) -> None:
        tk = self.tk
        ttk = self.ttk

        root_frame = tk.Frame(self.root, padx=12, pady=12)
        root_frame.pack(fill="both", expand=True)

        workspace_frame = tk.LabelFrame(root_frame, text="Workspace", padx=10, pady=10)
        workspace_frame.pack(fill="x")

        workspace_entry = ttk.Combobox(
            workspace_frame,
            textvariable=self.workspace_var,
            values=self.recent_workspaces,
        )
        workspace_entry.bind("<<ComboboxSelected>>", self._on_workspace_selected)
        workspace_entry.pack(side="left", fill="x", expand=True)
        self.workspace_entry = workspace_entry

        browse_button = tk.Button(workspace_frame, text="Browse", command=self._browse_workspace, width=10)
        browse_button.pack(side="left", padx=(8, 0))

        help_button = tk.Button(workspace_frame, text="Help", command=self._show_help, width=10)
        help_button.pack(side="left", padx=(8, 0))

        hint_frame = tk.Frame(root_frame, pady=6)
        hint_frame.pack(fill="x")
        tk.Label(
            hint_frame,
            text="Choose the workspace root folder.",
            anchor="w",
            justify="left",
        ).pack(fill="x")
        tk.Label(
            hint_frame,
            textvariable=self.workspace_state_var,
            anchor="w",
            justify="left",
            fg="#1f4e79",
        ).pack(fill="x", pady=(4, 0))

        actions_frame = tk.LabelFrame(root_frame, text="Actions", padx=10, pady=10)
        actions_frame.pack(fill="x", pady=(12, 0))

        actions = [
            ("Split", _run_split),
            ("Validate", _run_validate),
            ("Call Graph", _run_call_graph),
            ("Build Split", _run_build_split),
            ("Build Monolith", _run_build_monolith),
        ]
        for label, handler in actions:
            button = tk.Button(
                actions_frame,
                text=label,
                width=16,
                command=lambda action=handler, title=label: self._start_action(title, action),
            )
            button.pack(side="left", padx=(0, 8))
            self.buttons.append(button)
            self.action_buttons[label] = button

        status_frame = tk.Frame(root_frame)
        status_frame.pack(fill="x", pady=(12, 0))
        tk.Label(status_frame, text="Status:").pack(side="left")
        tk.Label(status_frame, textvariable=self.status_var, anchor="w").pack(side="left", padx=(8, 0))

        self.log_toggle_button = tk.Button(status_frame, text="Show Log", width=12, command=self._toggle_log)
        self.log_toggle_button.pack(side="right")

        log_frame = tk.LabelFrame(root_frame, text="Log", padx=10, pady=10)
        self.log_frame = log_frame

        self.log_widget = self.scrolledtext.ScrolledText(log_frame, wrap="word", state="normal")
        self.log_widget.pack(fill="both", expand=True)
        self.log_widget.bind("<Key>", self._block_log_edit)
        self.log_widget.bind("<Control-c>", self._copy_log_selection)
        self.log_widget.bind("<Control-C>", self._copy_log_selection)
        self.log_widget.bind("<Button-3>", self._show_log_context_menu)

        self.log_menu = tk.Menu(self.root, tearoff=False)
        self.log_menu.add_command(label="Copy", command=self._copy_log_selection)

        self._append_log("UI ready.\n")
        self.log_widget.configure(state="normal")

    def _browse_workspace(self) -> None:
        selected = self.filedialog.askdirectory(initialdir=self.workspace_var.get() or ".")
        if selected:
            normalized = _normalize_workspace_selection(selected)
            self.workspace_var.set(str(normalized))
            self._remember_workspace(normalized)
            try:
                self._maybe_offer_workspace_creation(resolve_workspace(normalized))
            except Exception:
                pass

    def _initial_workspace_value(self, initial_workspace: Path) -> str:
        resolved = initial_workspace.resolve()
        if resolved == Path(".").resolve():
            last_workspace = str(self.ui_state.get("last_workspace", "")).strip()
            if last_workspace:
                return last_workspace
        return str(resolved)

    def _remember_workspace(self, workspace: str | Path) -> None:
        normalized = str(_normalize_workspace_selection(workspace))
        recent = [item for item in self.recent_workspaces if item != normalized]
        self.recent_workspaces = [normalized, *recent][:10]
        self.ui_state["last_workspace"] = normalized
        self.ui_state["recent_workspaces"] = list(self.recent_workspaces)
        self.workspace_entry.configure(values=self.recent_workspaces)
        try:
            _save_ui_state(normalized, self.recent_workspaces)
        except OSError:
            pass

    def _on_workspace_selected(self, _event=None) -> None:
        workspace_text = self.workspace_var.get().strip()
        if workspace_text:
            self._remember_workspace(workspace_text)

    def _show_help(self) -> None:
        self.help_dialog = HelpDialog(self.root)

    def _set_busy(self, busy: bool) -> None:
        self.is_busy = busy
        self._refresh_workspace_state()

    def _toggle_log(self) -> None:
        self.log_visible = not self.log_visible
        if self.log_visible:
            self.log_frame.pack(fill="both", expand=True, pady=(12, 0))
            self.log_toggle_button.configure(text="Hide Log")
        else:
            self.log_frame.pack_forget()
            self.log_toggle_button.configure(text="Show Log")
        self._resize_window()

    def _resize_window(self) -> None:
        self.root.update_idletasks()
        min_height = MIN_EXPANDED_HEIGHT if self.log_visible else MIN_COLLAPSED_HEIGHT
        width = max(DEFAULT_WINDOW_WIDTH, self.root.winfo_reqwidth())
        height = max(min_height, self.root.winfo_reqheight())
        self.root.minsize(DEFAULT_WINDOW_WIDTH, min_height)
        self.root.geometry(f"{width}x{height}")

    def _on_workspace_changed(self, *_args) -> None:
        self._refresh_workspace_state()

    def _on_app_focus(self, _event=None) -> None:
        self._refresh_workspace_state()

    def _poll_workspace_state(self) -> None:
        if not self.is_busy:
            self._refresh_workspace_state()
        self.root.after(WORKSPACE_REFRESH_MS, self._poll_workspace_state)

    def _refresh_workspace_state(self) -> None:
        try:
            raw_workspace = self.workspace_var.get().strip()
            if not raw_workspace:
                raise ValueError("Workspace path is empty")

            normalized = _normalize_workspace_selection(raw_workspace)
            if str(normalized) != raw_workspace:
                self.workspace_var.set(str(normalized))
                self._remember_workspace(normalized)
                return

            paths = resolve_workspace(normalized)
            summary, split_ready = _summarize_workspace(paths)
            self.workspace_state_var.set(summary)

            build_ready = paths.project_blocks_dir.exists()
            try:
                resolve_project_symbols_path(paths)
            except (FileNotFoundError, FileExistsError):
                build_ready = False

            states = {
                "Split": split_ready,
                "Validate": build_ready,
                "Call Graph": build_ready,
                "Build Split": build_ready,
                "Build Monolith": build_ready,
            }
        except Exception as exc:
            self.workspace_state_var.set(f"Workspace problem: {exc}")
            states = {label: False for label in self.action_buttons}

        for label, button in self.action_buttons.items():
            enabled = states.get(label, False) and not self.is_busy
            button.configure(state="normal" if enabled else "disabled")

        for button in self.buttons:
            if button not in self.action_buttons.values():
                button.configure(state="disabled" if self.is_busy else "normal")

    def _workspace_paths(self) -> WorkspacePaths:
        workspace_text = self.workspace_var.get().strip()
        if not workspace_text:
            raise ValueError("Workspace path is empty")
        paths = resolve_workspace(_normalize_workspace_selection(workspace_text))
        self._maybe_offer_workspace_creation(paths)
        return paths

    def _has_any_workspace_structure(self, paths: WorkspacePaths) -> bool:
        return any(
            path.exists()
            for path in (
                paths.exported_dir,
                paths.project_dir,
                paths.build_dir,
            )
        )

    def _create_workspace_structure(self, paths: WorkspacePaths) -> None:
        ensure_workspace_gitignore(paths.root)
        for path in (
            paths.exported_dir,
            paths.project_blocks_dir,
            paths.project_symbols_dir,
            paths.build_monolith_dir,
            paths.build_split_blocks_dir,
            paths.build_split_symbols_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def _maybe_offer_workspace_creation(self, paths: WorkspacePaths) -> None:
        if self._has_any_workspace_structure(paths):
            return
        if paths.root in self.prompted_workspace_paths:
            return

        self.prompted_workspace_paths.add(paths.root)
        create_now = self.messagebox.askyesno(
            "Create workspace folders",
            _workspace_structure_description(paths),
        )
        if create_now:
            self._create_workspace_structure(paths)
            self._append_log(f"[info] Created workspace structure in {paths.root}\n")
            self.status_var.set("Workspace folders created")
            self._refresh_workspace_state()

    def _start_action(self, label: str, action: Callable[[WorkspacePaths], str]) -> None:
        if self.is_busy:
            return

        try:
            paths = self._workspace_paths()
        except Exception as exc:  # pragma: no cover - UI path
            self.messagebox.showerror("Invalid workspace", str(exc))
            return

        self._remember_workspace(paths.root)
        self._set_busy(True)
        self.status_var.set(f"{label} running...")
        if label in {"Validate", "Call Graph"}:
            self.log_widget.delete("1.0", "end")
        self._append_log(f"[start] {label} on {paths.root}\n")

        def worker() -> None:
            try:
                result = action(paths)
                self.log_queue.put(("success", result))
            except ParseError as exc:
                self.log_queue.put(("error", str(exc)))
            except Exception as exc:  # pragma: no cover - UI path
                self.log_queue.put(("error", f"{exc}", traceback.format_exc()))

        threading.Thread(target=worker, daemon=True).start()

    def _append_log(self, text: str) -> None:
        self.log_widget.insert("end", text)
        self.log_widget.see("end")

    def _block_log_edit(self, event) -> str | None:
        allowed_keys = {
            "Left",
            "Right",
            "Up",
            "Down",
            "Home",
            "End",
            "Prior",
            "Next",
        }
        if event.state & 0x4 and event.keysym.lower() in {"c", "a"}:
            return None
        if event.keysym in allowed_keys:
            return None
        return "break"

    def _copy_log_selection(self, _event=None) -> str | None:
        try:
            selected = self.log_widget.get("sel.first", "sel.last")
        except self.tk.TclError:
            return "break"
        self.root.clipboard_clear()
        self.root.clipboard_append(selected)
        return "break"

    def _show_log_context_menu(self, event) -> str:
        self.log_widget.focus_set()
        try:
            self.log_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.log_menu.grab_release()
        return "break"

    def _poll_log_queue(self) -> None:
        while True:
            try:
                item = self.log_queue.get_nowait()
            except queue.Empty:
                break

            if len(item) == 2:
                kind, message = item
                details = ""
            else:
                kind, message, details = item

            if kind == "success":
                self.status_var.set("Done")
                self._append_log(f"[ok] {message}\n")
            else:
                self.status_var.set("Failed")
                if not self.log_visible:
                    self._toggle_log()
                self._append_log(f"[error] {message}\n")
                if details:
                    self._append_log(f"{details}\n")
                self.messagebox.showerror(APP_NAME, message)
            self.is_busy = False
            self._refresh_workspace_state()

        self.root.after(100, self._poll_log_queue)


def launch_ui(initial_workspace: str | Path | None = None) -> None:
    tk, _filedialog, _messagebox, _scrolledtext, _ttk = _safe_import_tk()
    root = tk.Tk()
    SyncUiApp(root, Path(initial_workspace or "."))
    root.mainloop()


class HelpDialog:
    def __init__(self, parent):
        tk, _filedialog, _messagebox, _scrolledtext, _ttk = _safe_import_tk()
        self.tk = tk
        self.steps = _help_steps()
        self.index = 0

        self.window = tk.Toplevel(parent)
        self.window.title(f"{APP_NAME} Help")
        self.window.geometry("520x360")
        self.window.resizable(False, False)
        self.window.transient(parent)
        self.window.grab_set()

        self.title_var = tk.StringVar()
        self.progress_var = tk.StringVar()

        self._build_layout()
        self._render_step()

    def _build_layout(self) -> None:
        tk = self.tk

        root = tk.Frame(self.window, padx=16, pady=16)
        root.pack(fill="both", expand=True)

        header = tk.Frame(root)
        header.pack(fill="x")

        icon = tk.Label(
            header,
            text="i",
            width=2,
            font=("Segoe UI", 16, "bold"),
            fg="white",
            bg="#2b88d8",
            pady=6,
        )
        icon.pack(side="left", padx=(0, 12))

        title_wrap = tk.Frame(header)
        title_wrap.pack(side="left", fill="x", expand=True)

        tk.Label(
            title_wrap,
            textvariable=self.title_var,
            font=("Segoe UI", 11, "bold"),
            anchor="w",
            justify="left",
        ).pack(fill="x")

        tk.Label(
            title_wrap,
            textvariable=self.progress_var,
            anchor="w",
            justify="left",
            fg="#666666",
        ).pack(fill="x", pady=(2, 0))

        body_frame = tk.Frame(root, pady=16)
        body_frame.pack(fill="both", expand=True)

        self.body_label = tk.Label(
            body_frame,
            anchor="nw",
            justify="left",
            wraplength=470,
        )
        self.body_label.pack(fill="both", expand=True)

        footer = tk.Frame(root)
        footer.pack(fill="x")

        self.back_button = tk.Button(footer, text="Back", width=10, command=self._back)
        self.back_button.pack(side="left")

        self.next_button = tk.Button(footer, text="Next", width=10, command=self._next)
        self.next_button.pack(side="right", padx=(8, 0))

        self.close_button = tk.Button(footer, text="Close", width=10, command=self.window.destroy)
        self.close_button.pack(side="right")

    def _render_step(self) -> None:
        title, body = self.steps[self.index]
        self.title_var.set(title)
        self.progress_var.set(f"Step {self.index + 1} of {len(self.steps)}")
        self.body_label.configure(text=body)

        self.back_button.configure(state="normal" if self.index > 0 else "disabled")
        if self.index >= len(self.steps) - 1:
            self.next_button.configure(state="disabled")
        else:
            self.next_button.configure(state="normal")

    def _back(self) -> None:
        if self.index > 0:
            self.index -= 1
            self._render_step()

    def _next(self) -> None:
        if self.index < len(self.steps) - 1:
            self.index += 1
            self._render_step()


def main() -> int:
    launch_ui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
