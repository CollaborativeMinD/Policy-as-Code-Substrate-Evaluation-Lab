"""Read-only notebook client of the governed run entry point."""
import marimo

__generated_with = "0.26.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import sqlite3
    import marimo as mo
    from lab import transact
    from admission import ROOT
    return ROOT, mo, sqlite3, transact


@app.cell
def _(ROOT, mo):
    mo.md("# Substrate Lab · admitted TOML scenarios")
    choices = {p.stem: p for p in sorted((ROOT / "policies").glob("*.toml"))}
    selection = mo.ui.dropdown(choices, value="pi-thermal", label="Policy")
    execute = mo.ui.run_button(label="Evaluate admitted policy")
    mo.vstack([selection, execute])
    return execute, selection


@app.cell
def _(mo, selection):
    mo.md(f"```toml\n{selection.value.read_text()}\n```")
    return


@app.cell
def _(ROOT, execute, mo, selection, sqlite3, transact):
    mo.stop(not execute.value)
    try:
        _receipt = transact("run", selection.value, ROOT / "state.sqlite")
        _view = mo.vstack([mo.md("### " + _receipt["effect"]["disposition"]),
                           mo.json(_receipt)])
    except (OSError, ValueError, sqlite3.Error) as _exc:
        _view = mo.md(f"Admission required: {_exc}")
    _view
    return


if __name__ == "__main__":
    app.run()
