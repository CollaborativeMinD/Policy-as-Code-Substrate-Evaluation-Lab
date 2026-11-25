# Substrate Evaluation Lab operator console

Run these commands from the checkout in a dedicated Python environment. Start the native lab MCP server and admit the scenarios listed in `console.toml`. Create `.local/lab-upstream.toml` with an integer `port` and the strings `reader_file` and `evaluator_file` pointing to the corresponding native token paths relative to that file. Inventory uses the reader. Execution uses the evaluator and checks its policy digest.

```sh
python -m pip install -r requirements-console.txt
python -m console_app.server credentials .local/console-keys
python -m console_app.server serve --policy console.toml --sha256 APPROVED_SHA256 --credentials .local/console-keys --state .local/console-state
```

Replace `APPROVED_SHA256` with the reviewed SHA-256 of the exact host TOML bytes. Launch a second terminal in the same environment.

```sh
python -m console_app.tui --policy console.toml --token .local/console-keys/viewer.token
```

| Token | Workflow |
|---|---|
| Viewer | Filter the live inventory. Read native status, running tasks and the latest receipt. |
| Admin | Select a resource and open its TOML draft. Edit `enabled` or its validated inputs. Apply it. If the revision changed, reopen the draft and reconcile the edit. |
| Agent | Select an active resource and a listed task. Enter admitted TOML inputs, run it, and inspect its result and receipt. |

Choose the corresponding token file when launching the TUI. Keep the service account, state directory and upstream credentials private. Provision each operator with only their role's token. On Windows enforce this with filesystem ACLs. Role credentials are checked on each loopback HTTP POST. Rotate a role token by atomically replacing its file with a new securely generated URL-safe token. A new credential directory can be created with the command above.

## Change a capability

Edit `console.toml` to select supported operations, service-owned native sources, permitted input overrides and role grants. Review the change, qualify it on Forgejo, then restart the server with the approved digest. A new host policy digest starts a fresh namespace for task drafts and receipts. An admin can publish a task policy inside that namespace while the service runs. Native admission, credentials and deployment policy stay under the component's existing workflow.

The service checks the task revision again before execution and stores successful receipts in its SQLite ledger. If a client loses its response, inspect the latest receipt and native state before retrying. Polling an unavailable native source shows an unverified resource and disables execution.

## Verify

Run `python -B -m console_app.verify` from the configured environment. The witness starts isolated local services, drives Textual in all three roles, checks denials, publishes a TOML edit and checks the native effect. Forgejo publishes the witness and exact revision as the `component-console` artifact.
