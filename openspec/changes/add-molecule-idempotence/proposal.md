# Proposal: add molecule idempotence testing

## Why

The molecule `default` scenario has its `idempotence` step commented out, so nothing guarantees that re-running converge on an already-converged host produces zero changed tasks. Change reporting in the role and scenario is also imprecise: the prepare wait task uses a blanket `changed_when: false`, and there is no rule preventing future tasks from suppressing change status blindly. Without an idempotence gate, regressions that make the role non-idempotent pass CI silently.

## What Changes

- Enable the `idempotence` step in `molecule/default/molecule.yml` test sequence (currently commented out), restoring the standard molecule order (`converge → idempotence → side_effect`).
- Make a second converge run report zero changed tasks: audit every task reachable from converge and fix inaccurate change reporting. Each fix must use an accurate `changed_when` expression derived from registered results or a prior-state check — never a blanket `false`, except for provably read-only tasks (documented as such).
- Replace the prepare wait task's blanket `changed_when: false` with an expression based on the actual systemd state observed in the command output.
- Fix the typo `foward_rule.to_ansible_host` → `forward_rule.to_ansible_host` in `tasks/port-forwarding.yml`, which breaks the `to_ansible_host` code path exercised by the scenario (recorded assumption: one-line fix on the same code path being tested).
- Ensure `tox -e idempotence` (`molecule idempotence`) passes and that `molecule test` includes the idempotence check.

## Capabilities

### New Capabilities

- `idempotence`: converging the role against an already-converged host is a no-op (zero changed tasks), all change reporting in the role and molecule scenario reflects actual state transitions, and the molecule scenario enforces this as a test gate.

### Modified Capabilities

(none — first spec for this project)

## Impact

- `molecule/default/molecule.yml` — test sequence gains the `idempotence` step.
- `molecule/default/prepare.yml` — wait task change reporting becomes output-derived.
- `tasks/*.yml` — tasks whose default change reporting is inaccurate get accurate `changed_when` expressions or prior-state checks (exact set determined by running `molecule idempotence`).
- CI/tox — the existing `idempotence` tox env becomes part of the regular test run via `molecule test`; no new dependencies.
- No role variable changes, no public interface change, no breaking changes.
