# Design: molecule idempotence testing

## Context

See proposal.md for motivation. Current state that shapes the approach:

- The role's tasks mostly use natively-idempotent modules (`package`, `service`, `modprobe`, `sysctl`, `firewalld`), so most change reporting is already accurate by default.
- `molecule/default/molecule.yml` defines one scenario (`default`: podman, fedora:44 image, systemd enabled) whose `test_sequence` has `- idempotence` commented out between `converge` and `side_effect`.
- `tox.ini` already declares an `idempotence` env running `molecule idempotence`, and `env_list` includes it — the gate exists but is never exercised by `molecule test`.
- `molecule/default/prepare.yml` waits for systemd with a raw command and blanket `changed_when: false`.
- `tasks/port-forwarding.yml` has a typo (`foward_rule.to_ansible_host`) in the when-clause that routes to `port-forwarding-to-host.yml`; zones using only `to_ansible_host` currently hit an undefined-variable error.

## Goals / Non-Goals

**Goals:**

- `molecule test` fails if re-convergence produces any changed task (gate inside the scenario sequence).
- Every task's changed status reflects actual state; no blanket `changed_when: false` on tasks that can change state.
- The `to_ansible_host` code path works and is idempotent.

**Non-Goals:**

- No changes to role variables, public interface, or supported distros.
- No new molecule scenarios (e.g., per-distro variants) — the existing `default` scenario is the gate.
- No custom testinfra tests for idempotence — molecule's built-in check (double converge + changed-count assertion) is the mechanism.

## Decisions

### D1: Enable the native molecule idempotence step in-place

Uncomment `- idempotence` at its standard position (after `converge`, before `side_effect`) in `molecule/default/molecule.yml`. Molecule's built-in check runs converge twice and asserts zero changed tasks on the second run.

- *Alternative considered:* keep it out of `test_sequence` and rely only on `tox -e idempotence`. Rejected: CI runs `molecule test` via `tox -e test-exec`, so a gate outside the sequence is never enforced in normal runs.
- No change to tox needed — the `idempotence` env already exists.

### D2: Change-reporting policy — accurate expressions, no blanket false

Policy applied to every task reachable from converge and to prepare:

1. Prefer module-native change detection (no `changed_when` at all) when the module compares state itself (`package`, `service`, `modprobe`, `sysctl`, `firewalld`).
2. For command/raw tasks, register the result and set `changed_when` to an expression over the registered output that is true only when a real transition occurred.
3. Blanket `changed_when: false` is allowed only for provably read-only tasks (pure queries/waits that cannot mutate state), with a short comment documenting why it is safe.

Concrete application:

- **prepare wait task** (`molecule/default/prepare.yml`): register the raw result as `systemd_status` and use
  `changed_when: "'running' not in systemd_status.stdout"`.
  Rationale: if systemd was already running, no transition happened during this task → unchanged; if it reached running while we waited (or timed out), a real state transition occurred within the task's window → changed. This replaces the blanket `false` with an output-derived expression per the user requirement.
- **Role tasks**: audit each file (`prereq.yml`, `install.yml`, `zone.yml`, `port-forwarding.yml`, `port-forwarding-to-host.yml`, `services-ports.yml`). Expected findings to confirm by running the gate:
  - `setup`/`debug`/`set_fact` tasks never report changed — no action.
  - If any `firewalld` rich-rule task reports changed on an identical re-run (rule-string normalization), add a prior-state check (`firewall-cmd --query-rich-rule` via `command`, registered, with accurate `changed_when`) and gate the apply task on it — never blanket `false`.
- **Discovery loop**: run `tox -e idempotence`, read which tasks report changed on the second converge, fix each per policy above, re-run until clean. The exact set of fixes is empirical; this decision fixes the *policy*, not the list.

### D3: Fix the `to_ansible_host` typo as part of this change

One-line fix in `tasks/port-forwarding.yml`: `foward_rule.to_ansible_host` → `forward_rule.to_ansible_host`. Behavior change is strictly a bug fix: zones using only `to_ansible_host` previously errored (undefined variable) and now get their rule applied. The scenario's existing `to_host` rule is unaffected, and the fixed path must itself be idempotent (covered by spec requirement "Host-targeted forwarding rules are applied").

### D4: Verification strategy

- Primary gate: `tox -e idempotence` (`molecule idempotence`) — double converge, zero changed.
- Full run: `tox -e test-exec` (`molecule test`) — includes the new sequence step plus existing testinfra verify tests (state assertions still hold after re-convergence).
- Lint: `tox -e lint` — yamllint/flake8/ansible-lint must stay clean; `changed_when` expressions and comments are lint-checked.

## Risks / Trade-offs

- [firewalld module reports changed on identical rich rules due to string normalization] → Mitigation: prior-state check via `firewall-cmd --query-rich-rule` with accurate `changed_when`, or normalize the rule string; confirmed by running the gate (D2 discovery loop).
- [prepare wait times out (systemd not ready within 30s)] → Pre-existing behavior unchanged (`|| true` masks rc); a late-ready system fails loudly in converge instead. The new expression only changes *reported* status, not control flow.
- [Extra converge run slows CI] → One additional converge (~1–2 min on the podman platform) per test run; accepted for the regression safety gained.
- [Container-specific quirks (privileged podman, cgroup mounts)] → Prereq tasks are already guarded by `virtualization_type == "container"`; no change to those guards in this work.

## Migration Plan

No user-facing migration: changes are internal to role task files and the molecule scenario. Rollback is a straight revert of the touched files (`molecule/default/molecule.yml`, `molecule/default/prepare.yml`, `tasks/port-forwarding.yml`, plus any task file adjusted by the D2 discovery loop).

## Open Questions

None blocking. The exact set of tasks needing `changed_when` adjustments is determined empirically during implementation (D2 discovery loop) — an implementation detail that does not change specs, approach, or task breakdown.
