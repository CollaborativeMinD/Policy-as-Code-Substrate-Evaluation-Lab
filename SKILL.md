---
name: governed-substrate-lab
description: Select, admit, evaluate, and reconcile a Substrate Lab scenario using a TOML policy and its effect receipt.
---

Use the nearest released TOML scenario as the starting point. Declare explicit observations, units, parameter ownership, and disturbance timing. Use a new generation for a changed active name. Keep synthetic fixtures identified.

Run admission with the reviewed digest, then evaluate the same document against the same state database. Read the modeled disposition inside the effect and retain the receipt hash. For a runtime change, compare against the original kernel with the full release qualification before promotion. [Runbook](Runbook.md)

## Live operator console

Use the [console guide](Console.md) to observe inventory, publish scoped TOML changes, run admitted tasks and verify their receipts.

## From policy change to release

Start with [policies/pi-thermal.toml](policies/pi-thermal.toml) for this component and [console.toml](console.toml) for terminal access. Write down the requested effect and one case that must be denied. Change the TOML first.

1. Apply the candidate to disposable state. An unknown field or unbound operation must fail admission before an effect. Keep that denial.
2. For supported behavior, continue with the existing runtime. For new behavior, implement the missing typed field and the method that enforces it. Run the same candidate again.
3. Run `python qualify.py` in the project environment. Exercise the normal entry point and the denial. Review the scenario disposition and active policy digest. Reconcile discrepancies and repeat.
4. Qualify the exact commit on local Forgejo. Review the package, image, security scan and receipt for each release target. Ship the reviewed artifacts and record their digests.
