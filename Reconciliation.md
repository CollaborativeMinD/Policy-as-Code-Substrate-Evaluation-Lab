# Reconciliation with Substrate Lab v2.0.0

The original archive supplied the reference oracle. Qualification extracted it into a temporary directory and ran its reference verifier there. The governed CLI used a separate copy of the pinned kernel and a fresh database. The oracle independently constructed each of the 25 expected scenarios through the original Python interface.

| Case | Observed result |
| --- | --- |
| All 20 nominal configurations | Complete resolved configurations and complete v2 effect receipts matched canonical JSON byte for byte. |
| Jackal with Pi and traction loss | WITHIN_DECLARED_MODEL, including the original ground stopping latency coupling. |
| Jackal with total traction loss | CAPABILITY_LOST. |
| Pi thermal disturbance | POLICY_DEGRADED. |
| Pi with supplied loop time and a revised budget | LIMIT_EXCEEDED. |
| Panda with source-supplied torque limits | LIMIT_EXCEEDED. |
| Original reference gates | All 725 replayed gate identities and dispositions matched the saved records. 720 passed. Five historical reference records remain open. |

## Intentional changes

The new operator entry points accept TOML. Declaration fields are closed. Scenario files carry the complete parameter inventory and observations. Referenced catalog defaults retain their original provenance. Changing a catalog value requires explicit override ownership. The release also scopes four profiles to their baseline fixture. The original research notebooks and builder remain available in the preserved archive.

The outer receipt adds the release, original archive and policy hashes, policy generation, and input provenance. Its embedded configuration and effect preserve the v2 data. The SQLite ledger records admission and receipt bytes. The comparison concerns analytical output, provenance and disposition for the listed cases. It supplies no new physical calibration.

Thirteen denial cases exercised unknown or missing fields, undeclared parameter changes, unit and type errors, scope restrictions, wrong pins, altered bytes, rollback, and stale revisions. The verifier also activated a valid successor, observed its changed temperature, and checked the total receipt count. See the [machine-readable report](evidence/reconciliation.json) for each reason and digest.
