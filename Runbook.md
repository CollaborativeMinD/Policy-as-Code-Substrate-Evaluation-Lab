# Operator runbook

1. Copy the closest file in `policies/`. Give a new experiment a distinct name. For a revision of an active name, increase its generation.
2. Declare all parameters and observations. Each parameter inherits its value and provenance from the pinned catalog unless its name appears in `overrides`. To change one, declare its value and add its name to that list. The original contract validates the override. For a source injection, give the source reference and payload together. A payload and a manual override cannot own the same field.
3. Choose `teaching-fixture` for exact v2.0.0 example observations. Choose `operator-supplied` for explicit experimental inputs. Supply units when using the original value/unit representation. Each disturbance declares its target, severity, onset, rise, end, and recovery. Use `end_s = "open"` for an open-ended disturbance.
4. Review the candidate and retain its SHA-256 independently. Use the README commands to admit and run. Admission evaluates the analytical candidate before replacing active state. A denial exits with code 2. An unchanged admitted file can run repeatedly. A superseded file requires a new higher-generation admission.
5. Keep the resulting receipt digest with the experiment. SQLite stores admitted TOML bytes by digest and effect receipts by digest. A transaction checks the active revision and commits the receipt. Identical runs share a receipt. Protect the runtime installation and ledger with host permissions. A local hash alone supplies no user authentication.

To reproduce release qualification, use a fresh Python 3.13 environment. Install `requirements-verification.txt` and run `python qualify.py`. The verifier extracts the original archive in a temporary directory, replays its reference gates, invokes the governed CLI in new processes, and compares complete configurations and effect receipts. See `Reconciliation.md` for the comparison scope.

## Start the MCP server

Use Python 3.13 in an isolated environment. Install `requirements-mcp.txt`. Admit the desired TOML documents with `lab.py admit` and the reviewed scenario hashes. The server opens this same ledger on each call.

Create a credentials directory restricted to the workstation account that operates the server. Each role needs a separate randomly generated token. For an initial local demonstration in a private workspace:

```powershell
python -c "from pathlib import Path; import secrets; p=Path('local-credentials'); p.mkdir(mode=0o700); [(p/(r+'.token')).write_text(secrets.token_urlsafe(32)) for r in ('reader','evaluator')]"
$digest = (Get-FileHash -Algorithm SHA256 mcp-policy.toml).Hash.ToLowerInvariant()
python lab_mcp.py --policy mcp-policy.toml --sha256 $digest --state state.sqlite --credentials local-credentials
```

Use an independently approved transport digest for a deployment. Windows inherits the containing directory's ACL. Keep tokens out of client logs and version control. Configure the client for Streamable HTTP and supply the selected role token through its Authorization bearer header. An official Python client example is in `verify_mcp.py`.

The tool result contains the original effect and durable receipt digest. A repeated evaluation of identical bytes reuses the same receipt. After a higher generation is admitted, the old transport pin stops matching. Update the relevant scenario digest in the transport TOML and restart with the newly approved transport digest. Credential rotation takes effect on the next request. Changing the transport port also changes its digest.

Run `python verify_mcp.py` to regenerate `evidence/mcp-workstation.json` against a disposable local server, isolated SQLite ledger and temporary role credentials. The witness uses an ephemeral port. Run `python qualify.py` with the verification dependencies to reproduce the separate v2.0.0 reconciliation.

## Live operator console

Use the [console guide](Console.md) to observe inventory, publish scoped TOML changes, run admitted tasks and verify their receipts.

## From policy change to release

Start with [policies/pi-thermal.toml](policies/pi-thermal.toml) for this component and [console.toml](console.toml) for terminal access. Write down the requested effect and one case that must be denied. Change the TOML first.

1. Apply the candidate to disposable state. An unknown field or unbound operation must fail admission before an effect. Keep that denial.
2. For supported behavior, continue with the existing runtime. For new behavior, implement the missing typed field and the method that enforces it. Run the same candidate again.
3. Run `python qualify.py` in the project environment. Exercise the normal entry point and the denial. Review the scenario disposition and active policy digest. Reconcile discrepancies and repeat.
4. Qualify the exact commit on local Forgejo. Review the package, image, security scan and receipt for each release target. Ship the reviewed artifacts and record their digests.

The version 2 `[runtime]` table in `console.toml` sets request size, concurrency and client deadlines. Version 1 files inherit the shipped budget. Reissue them as version 2 to pin these choices in the admitted document.
