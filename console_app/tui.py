"""Live resource inventory, policy editor and scoped task runner."""
import argparse
import json
from pathlib import Path
import tomllib

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Footer, Header, Input, Select, Static, TextArea

from .client import Remote


class Console(App):
    TITLE = "Component Console"
    BINDINGS = [("ctrl+r", "refresh_now", "Refresh"), ("ctrl+q", "quit", "Quit")]
    CSS = """
    #inventory {height: 2fr; min-height: 5;}
    #editor {height: 1fr; min-height: 4;}
    #controls {height: auto;}
    #feedback {height: auto; max-height: 6; overflow-y: auto;}
    #context, #status, #feedback {padding: 0 1;}
    #tasks {width: 1fr;}
    """

    def __init__(self, remote):
        super().__init__()
        self.remote = remote
        self.rows = {}
        self.selected = None
        self.edit = None
        self.grants = set()
        self.poll_timer = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Connecting to local MCP", id="status", markup=False)
        yield Input(placeholder="Filter by resource or admission state", id="filter")
        yield DataTable(cursor_type="row", id="inventory")
        yield Static("", id="context", markup=False)
        with Horizontal(id="controls"):
            yield Button("Open draft", id="open")
            yield Button("Apply TOML", id="apply", variant="primary")
            yield Select([], prompt="Select task", id="tasks")
            yield Button("Run task", id="run", variant="primary")
        yield TextArea(id="editor", soft_wrap=True)
        yield Static("", id="feedback", markup=False)
        yield Footer()

    async def on_mount(self):
        self.query_one(DataTable).add_columns("Resource", "Admission", "Component state", "Running", "Last task (UTC)")
        self.controls()
        await self.action_refresh_now()
        self.interval = getattr(self, "interval", 3)
        self.poll_timer = self.set_interval(self.interval, self.action_refresh_now)

    def feedback(self, value):
        self.query_one("#feedback", Static).update(value)

    async def action_refresh_now(self):
        try:
            frame = await self.remote.call("inventory.read")
            if not self.query("#status"):
                return
            interval = frame["poll_seconds"]
            if self.poll_timer and interval != self.interval:
                self.poll_timer.stop()
                self.poll_timer = self.set_interval(interval, self.action_refresh_now)
            self.interval = interval
            self.grants = set(frame["tools"])
            before = self.rows
            self.rows = {r["resource"]: r for r in frame["rows"]}
            self.sub_title = frame["component"] + " · " + frame["role"].capitalize()
            count = sum(r["state"] == "active" for r in self.rows.values())
            self.query_one("#status", Static).update(f"{count} active   ·   {len(self.rows)} in inventory")
            if self.rows != before:
                self.render_rows()
            self.controls()
        except Exception:
            if not self.query("#status"):
                return
            self.rows = {}
            self.grants.clear()
            self.query_one("#status", Static).update("Observation unavailable · check service and credential")
            self.render_rows()
            self.controls()

    def render_rows(self):
        query = self.query_one("#filter", Input).value.casefold()
        table = self.query_one(DataTable)
        matches = [r for r in self.rows.values() if query in (r["resource"] + " " + r["state"]).casefold()]
        names = [r["resource"] for r in matches]
        selection = self.selected if self.selected in names else next(iter(names), None)
        table.clear()
        for row in matches:
            latest = row["latest"]
            effect = f"{latest['task']}  {latest['at'][11:19]}" if latest else ""
            table.add_row(row["resource"], row["state"], row["detail"], str(row["running"]), effect, key=row["resource"])
        if selection:
            table.move_cursor(row=names.index(selection))
        self.select_resource(selection)

    def select_resource(self, resource):
        if resource != self.selected:
            self.selected, self.edit = resource, None
            self.query_one(TextArea).load_text("")
            self.feedback("")
        self.controls()

    def controls(self):
        row = self.rows.get(self.selected, {})
        admin = "policy.open" in self.grants
        agent = "task.execute" in self.grants
        self.query_one("#open").display = admin
        self.query_one("#open").disabled = not row or row.get("state") == "unverified"
        self.query_one("#apply").display = "policy.apply" in self.grants
        stale = self.edit is not None and self.edit["revision"] != row.get("revision")
        self.query_one("#apply").disabled = not self.edit or stale or row.get("state") == "unverified"
        tasks = row.get("tasks", {})
        select = self.query_one("#tasks", Select)
        options = (self.selected, json.dumps(tasks, sort_keys=True), row.get("revision"))
        if options != getattr(self, "_options", None):
            self._options = options
            select.set_options([(name, name) for name in tasks])
            if tasks:
                select.value = next(iter(tasks))
                self.load_inputs(tasks[select.value])
        select.display = agent and bool(tasks)
        self.query_one("#run").display = agent
        self.query_one("#run").disabled = not tasks
        self.query_one(TextArea).display = bool(admin and self.edit or agent and tasks)
        label = self.selected or "No matching resource"
        if stale:
            label += "   ·   Draft is stale. Open the current revision."
        elif row.get("revision"):
            label += "   ·   " + row["revision"].split("/")[-1][:12]
        self.query_one("#context", Static).update(label)

    def on_data_table_row_highlighted(self, event):
        table = self.query_one(DataTable)
        if table.row_count and table.coordinate_to_cell_key(table.cursor_coordinate).row_key == event.row_key:
            self.select_resource(event.row_key.value)

    def on_input_changed(self, event):
        if event.input.id == "filter":
            self.render_rows()

    def on_select_changed(self, event):
        task = self.rows.get(self.selected, {}).get("tasks", {}).get(event.value)
        if task:
            self.load_inputs(task)

    def load_inputs(self, task):
        self.query_one(TextArea).load_text("\n".join(f"{k} = {json.dumps(v)}" for k, v in task["inputs"].items()))

    async def on_button_pressed(self, event):
        editor = self.query_one(TextArea)
        try:
            if event.button.id == "open":
                self.edit = await self.remote.call("policy.open", resource=self.selected)
                editor.load_text(self.edit["toml"])
                self.feedback("Edit the TOML, then apply.")
            elif event.button.id == "apply" and self.edit:
                result = await self.remote.call("policy.apply", resource=self.selected, source=editor.text,
                                                draft_sha256=self.edit["draft_sha256"], revision=self.edit["revision"])
                self.feedback("Published " + result["revision"])
                self.edit = result
            elif event.button.id == "run":
                receipt = await self.remote.call("task.execute", name=self.query_one(Select).value,
                                                 inputs=tomllib.loads(editor.text), revision=self.rows[self.selected]["revision"])
                self.feedback(f'{receipt["disposition"]}   ·   result {receipt["result"]}   ·   receipt {receipt["id"]}')
        except Exception as exc:
            self.feedback(f"Request failed. {exc}")
        self.controls()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=Path("console.toml"))
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    port = tomllib.loads(args.policy.read_text())["port"] if args.port is None else args.port
    Console(Remote(port, args.token)).run()

if __name__ == "__main__":
    main()
