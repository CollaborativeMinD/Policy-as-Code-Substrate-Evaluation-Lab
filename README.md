# Substrate Lab · Policy-as-Code

Choose the substrate. Declare the observations and disturbance in TOML. Admit the exact document, evaluate it, and keep the receipt.

The command line and notebook share one runtime. Both consume the same admitted TOML. The runtime resolves the v2.0.0 kernel, validates units and physical bounds, checks the active policy, and records the model effect in SQLite. Python 3.11 or later supplies everything needed for admission and evaluation.

## First run

From this directory, review `policies/pi-thermal.toml`. In a local demonstration the following PowerShell commands calculate its digest and admit it. For a release, obtain the approved digest from your review or CI record.

```powershell
$policy = 'policies/pi-thermal.toml'
$digest = (Get-FileHash -Algorithm SHA256 $policy).Hash.ToLowerInvariant()
python lab.py admit $policy --sha256 $digest --state state.sqlite
python lab.py run $policy --state state.sqlite
```

The run returns `PASS` for evaluation and `POLICY_DEGRADED` for the modeled Pi. The two fields answer different questions. The first records whether the governed evaluation completed. The second describes what happened in the scenario.

For notebook use, install marimo and run `python -m marimo run notebook.py`. Choose an admitted file from `policies/` and select **Evaluate admitted policy**. The notebook uses the state database beside the launcher. Save an edited scenario as TOML and admit its new digest before evaluating it.

## Release scope

The distribution includes 20 baseline teaching configurations and five worked variations. These cover coupled traction and compute latency, complete traction loss, Pi thermal degradation, a changed Pi budget with supplied observations, and a sourced Panda torque envelope. Four entries ship with their nominal teaching fixture as their qualified scope. Their canonical identities appear in `release.json` under `reference_only`.

The byte-preserved original archive contains the research, notebooks, reference ledgers, JSON examples, and replay tools. The new surface uses a TOML notebook and CLI, with the original compose and evaluate kernels underneath. The calculations run locally and produce model receipts. The lab does not actuate hardware.

[Runbook](Runbook.md) · [Reconciliation](Reconciliation.md) · [Machine-readable results](evidence/reconciliation.json) · [Agent workflow](SKILL.md)

## Stateless MCP on the workstation

The server uses MCP 2026-07-28 over Streamable HTTP at `http://127.0.0.1:8765/mcp`. Every POST requires a bearer credential. The reader can call `scenarios.list`. The evaluator can also call `scenario.evaluate` with a scenario name, for example `{"name":"pi-thermal"}`. Policy admission stays with the trusted local launcher. An evaluation can only use the intersection of the active ledger entries and the exact scenario digests in `mcp-policy.toml`.

Install `requirements-mcp.txt` in an isolated environment and follow the [MCP workstation runbook](Runbook.md#start-the-mcp-server). The [wire witness](verify_mcp.py) checks discovery, rejection, lifecycle changes, and the complete returned receipt against the v2 reconciliation. [Workstation results](evidence/mcp-workstation.json)

## Live operator console

Use the [console guide](Console.md) to observe inventory, publish scoped TOML changes, run admitted tasks and verify their receipts.
