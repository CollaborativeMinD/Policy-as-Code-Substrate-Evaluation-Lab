# Working in the substrate lab

Start with the scenario TOML and the expected model disposition. For a supported change, use the existing runtime and compare the resulting receipt. For an unsupported declaration, retain the denial before adding an enforcement rule. Keep the v2.0.0 source archive and kernel bytes intact. Review a changed governance implementation and update its release pins before qualification.

Run the release comparison from a clean unpack. Preserve open historical records, teaching-fixture labels, source provenance, and the distinction between a completed evaluation and its modeled disposition. [Runbook](Runbook.md) · [Scenario workflow](SKILL.md)

## Live operator console

Use the [console guide](Console.md) to observe inventory, publish scoped TOML changes, run admitted tasks and verify their receipts.

## From policy change to release

Start with [policies/pi-thermal.toml](policies/pi-thermal.toml) for this component and [console.toml](console.toml) for terminal access. Write down the requested effect and one case that must be denied. Change the TOML first.

1. Apply the candidate to disposable state. An unknown field or unbound operation must fail admission before an effect. Keep that denial.
2. For supported behavior, continue with the existing runtime. For new behavior, implement the missing typed field and the method that enforces it. Run the same candidate again.
3. Run `python qualify.py` in the project environment. Exercise the normal entry point and the denial. Review the scenario disposition and active policy digest. Reconcile discrepancies and repeat.
4. Qualify the exact commit on local Forgejo. Review the package, image, security scan and receipt for each release target. Ship the reviewed artifacts and record their digests.
