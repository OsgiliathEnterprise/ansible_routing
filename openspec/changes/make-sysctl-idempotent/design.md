# Design: idempotent prereq sysctl tasks

## Context

See proposal.md for motivation. Current state that shapes the approach:

- `tasks/prereq.yml` has one `community.general.modprobe` task (`br_netfilter`, `state: present`, `persistent: present`) and six `ansible.posix.sysctl` tasks (`sysctl_set` + `state: present` + `reload`, writing to the default `/etc/sysctl.conf`). All are guarded by `when: not ansible_facts.virtualization_type == "container"`.
- Verified against the installed `ansible.posix.sysctl` module source:
  - Change detection = persistent-file entry missing/mismatched **or** runtime value missing/mismatched (when `sysctl_set`/`reload` are set).
  - When a key is **absent at runtime** (the module exposing it is not loaded), the module reports `changed: true` on every run while performing no work, and the `sysctl -p` reload it triggers then fails on the missing key (`fail_json`).
  - When the key exists and the file entry + runtime value match, the task reports unchanged and runs no `sysctl -p` (the module reloads only when it actually changed something).
- `nf_conntrack` is never loaded by the role, so `net.netfilter.nf_conntrack_max` may not exist. The task is currently masked with `failed_when: false` + `changed_when: false` + a `# TODO improve this, it is not idempotent on some distro` comment.
- The `net.bridge.bridge-nf-call-*` keys are exposed by `br_netfilter`, which the role already loads (pre-existing assumption).
- Verification reality (verified empirically in a running scenario container): podman 6.0.2 sets the container env var `container=oci` (not `container=podman`), and systemd reports `oci` in `/run/systemd/container`. Ansible's linux virtualization detector (verified in the installed ansible-core 2.21 `virtual/linux.py`) falls into the generic `^container=.` branch → `virtualization_type: container` → the `when` guards **skip all seven prereq tasks** in the molecule scenario. The idempotence gate was therefore passing trivially with zero coverage of these tasks.
- The platform cannot execute the tasks even without the guards: the scenario image lacks the `sysctl` binary (`procps-ng` not installed; the module does `get_bin_path('sysctl', required=True)`), and `/lib/modules` is empty in the image (so `modprobe` has no module files), while the podman machine (aarch64, kernel `7.1.3-200.fc44.aarch64`) has the matching modules (`nf_conntrack.ko.xz`, `br_netfilter`) in its own `/lib/modules`.
- The platform container is fully privileged (`privileged: True`, CapEff `000001ffffffffff`), so once the tools and module files are available, `sysctl -w` and `modprobe` act on the podman machine's kernel.
- Network namespace scoping (found by running the tasks): with the default podman bridge network the container has its **own** netns. Per-netns sysctls (`net.bridge.*`, `net.ipv4.ip_forward` as observed) accept writes from the container's netns but only affect that netns — the machine's values stay at module defaults — and the global `net.netfilter.nf_conntrack_max` is rejected with `Operation not permitted` from a non-init netns, while the same write succeeds from the machine's root shell. The role's prereq tasks are explicitly about the host NIC and the machine's kernel, so the platform must share the machine's netns.

## Goals / Non-Goals

**Goals:**

- All six prereq sysctl tasks report `changed` only when real state changed (persistent entry or runtime value).
- Remove `failed_when: false` / `changed_when: false` and the TODO from the `nf_conntrack_max` task; the conntrack limit is genuinely applied — and idempotently — on hosts where the module was not previously loaded.
- `tox -e idempotence` passes with these tasks executing.

**Non-Goals:**

- No change to target values, the sysctl file (`/etc/sysctl.conf` default), or role variables.
- No per-key existence probing (`sysctl -n` before apply) — with the modules loaded, all six keys exist on the supported distros (RHEL/Fedora family).
- No changes to other roles' sysctl usage.
- No `rmmod`/module-unload bookkeeping in the scenario teardown — loaded modules remain loaded on the podman machine after a test (see D7).

## Decisions

### D1: Guarantee key existence by loading `nf_conntrack` alongside `br_netfilter`

Add `nf_conntrack` to the existing modprobe loop in `prereq.yml` (same `state: present`, `persistent: present`, same container guard). The modprobe task is the first task in the file, so the keys are exposed before any sysctl task runs.

- `br_netfilter` (already loaded) exposes the three `net.bridge.bridge-nf-call-*` keys — the role already relies on this.
- `nf_conntrack` exposes `net.netfilter.nf_conntrack_max`.
- With all six keys present at runtime, the module-native comparison becomes accurate:
  - first converge: writes the file entry if missing and runs `sysctl -w` if the runtime value differs → `changed` (real transition);
  - re-converge: file entry present + runtime value matches → unchanged, and no `sysctl -p` fires (the module only reloads when it changed something).
- `persistent: present` writes `/etc/modules-load.d/`, so the module is loaded at boot before `systemd-sysctl` applies `/etc/sysctl.conf` (`systemd-modules-load.service` runs first) — the persisted `nf_conntrack_max` entry is active from first boot. Consistent with the existing `br_netfilter` treatment.

*Alternatives considered:*

- `ignoreerrors: true` — still reports `changed` for a missing key (compares against an absent runtime value) and masks genuine configuration failures. Rejected.
- Per-key existence probing (`command: sysctl -n <key>` registered, gated with `when: rc == 0`) — six extra tasks, needed only if a key can legitimately be absent. With D1 the keys are guaranteed present on supported distros, and the `idempotence` capability's policy prefers module-native change detection. Rejected as over-engineering; revisit if a target distro turns out to lack a key.
- Splitting each setting into a persistent-file task (`sysctl_set: true`, `reload: false`) and a runtime task (`sysctl_set: false`) — redundant: `sysctl_set: true` already reconciles the runtime value via `sysctl -w` when it differs. Rejected.

### D2: Remove the change/failure suppression from the conntrack task

With D1 in place `net.netfilter.nf_conntrack_max` exists, so the task becomes an ordinary `sysctl_set: true` + `reload: true` task: drop `failed_when: false`, `changed_when: false`, and the TODO comment; change reporting comes from the module itself.

### D3: Keep `sysctl_set: true` + `reload: true` on all six tasks

- `sysctl_set: true` persists to `/etc/sysctl.conf` (default `sysctl_file`) and reconciles the runtime value in one task.
- `reload: true` is safe for idempotence: the module only runs `sysctl -p` when it actually changed something, so no-op re-converges trigger no reload.
- Normalize `yes` → `true` on the first two tasks for consistency (cosmetic; YAML `yes` is a boolean, no behavior change).

### D4: Remove the container guards from the prereq tasks

Delete the seven `when: not ansible_facts.virtualization_type == "container"` guards (modprobe task + six sysctl tasks) in `tasks/prereq.yml`.

- The guard's literal purpose — "don't touch the host kernel from a containerized run" — only misfires for the molecule podman platform in practice: production targets of this role are VMs (parallels topology), and the only container target that exists is the scenario container itself, where running the tasks is exactly what the idempotence gate needs.
- Trade-off: converging against a *real* docker/podman-managed node would now load the modules and set the sysctls on its kernel (previously skipped). Accepted: this role is not deployed against container nodes; if that ever changes, re-introduce a guard.
- The guards were the only thing standing between the tasks and the molecule scenario (Context: `virtualization_type: container` there), so this is what makes `tox -e idempotence` a genuine gate for these tasks.

### D5: Enable the molecule podman platform to run the tasks

Two platform fixes, both verified against the running machine/image:

- `molecule/common/Dockerfile.j2`: add `procps-ng` to the `dnf -y install` line. The `sysctl` module requires the `sysctl` binary (`get_bin_path('sysctl', required=True)`); it is absent from the base image. `modprobe` already exists (`kmod` is installed).
- `molecule/default/molecule.yml`: add platform volume `/lib/modules:/lib/modules:ro`. `modprobe` resolves modules under `/lib/modules/$(uname -r)/`; the image's directory is empty, while the machine's copy matches the shared kernel (`7.1.3-200.fc44.aarch64`, image is fedora:44). Read-only: the container never writes module files.
- `molecule/default/molecule.yml`: set `network: host` (replacing the now-meaningless `dns_servers`). With host networking the container shares the machine's netns, so the role's sysctl writes affect the machine's actual NIC/kernel state — including the global `nf_conntrack_max` key — and `modprobe`-loaded modules behave as on the host. The podman driver passes `item.network` straight to the podman container module, and `host` is a first-class value in its network creation exclusion list. The instance IP becomes the machine's IP (harmless: provisioner and verifier connect through the podman connection plugin, not the IP).
- No capability change is needed: the platform is already `privileged: True` (CapEff all), so `sysctl -w` / `modprobe` can act on the machine kernel.

### D6: Verification

- Primary gate: `tox -e idempotence` (`molecule idempotence`, default podman scenario) — with D4+D5 the prereq tasks actually execute there, so the double-converge check covers them directly. The first converge must show the prereq tasks **executed, not skipped**, and `sysctl -w net.netfilter.nf_conntrack_max=...` must succeed from inside the container (host netns).
- Full run: `tox -e test-exec` (`molecule test`) — includes the existing testinfra verify tests and the cleanup restore (D7).
- Lint: `tox -e lint` — yamllint/ansible-lint must stay clean after all edits.
- Machine-state check: capture the six key values on the machine (`podman machine ssh sysctl -n ...`) before the test and after `tox -e test-exec`; they must match (cleanup restored them).
- Manual spot-check on a VM (when a parallels VM is available): `lsmod | grep nf_conntrack`, `sysctl net.netfilter.nf_conntrack_max` equals `1000000`, `/etc/modules-load.d/nf_conntrack.conf` exists, and a double converge shows 0 changed prereq tasks.

### D7: Machine-state bookkeeping (capture in prepare, restore in cleanup)

Running the tasks in the scenario mutates the podman machine's global kernel state (forwarding flags, bridge-nf hooks, `nf_conntrack_max`, two modules loaded). To keep the machine pristine across runs:

- The podman driver connects provisioner tasks to the instance with the `podman` connection plugin (tasks execute inside the container), so the bookkeeping tasks use the container's own `sysctl` binary (added in D5) and target the machine's global kernel state directly.
- `molecule/default/prepare.yml` (runs after create, before converge): for each of the six role-managed keys, run `sysctl -n <key>` (`failed_when: false`, `changed_when: false` — provably read-only, documented) and write `key=value` lines to `/etc/molecule-sysctl-backup.conf` inside the container. Keys absent at capture time (bridge/conntrack keys before `modprobe` ran) are recorded with an `__absent__` sentinel (`default(value, true)` treats the empty `stdout` of a failed `sysctl -n` as absent).
- `molecule/default/cleanup.yml` (new; runs at the final `cleanup` step of molecule 25's default `test_sequence` — after verify, before destroy, while the container is still alive): molecule 25 has **no `posttest` step** (sequence steps map to named command classes; verified in molecule 25.12), so `cleanup.yml` is the built-in post-verify hook. It restores each non-sentinel line via `sysctl -w key=value` and removes the backup file. The play carries `ignore_unreachable: true` because the *first* cleanup sequence position runs before create (container absent → podman connection failure → host unreachable → ignored). The restore task is best-effort (`failed_when: false`): cleanup also runs at the start of `molecule destroy`, and a failed restore (e.g. restoring a global key from a non-host netns container) must never block the destroy.
- Restoring `__absent__` keys would require unloading modules (`rmmod`), which is not safe (modules are referenced by bridges/iptables) and not meaningful — loaded modules remain loaded after the test. Accepted: `br_netfilter`/`nf_conntrack` are standard modules on an active host.
- Caveats (documented, accepted): standalone `molecule converge`/`idempotence` do not run the cleanup step, so the machine stays mutated until the next full `molecule test`/`cleanup` — harmless on the disposable libkrun machine; if a run crashes between converge and cleanup, the next run's prepare captures the already-mutated values as the baseline (the original values are not recovered) — the mutated values are benign (forwarding on, conntrack max 1M, bridge-nf on).

## Risks / Trade-offs

- [Loading `nf_conntrack` on a host that did not have it loaded is a kernel state change] → Mitigation: `nf_conntrack` is core on RHEL/Fedora (built-in on many kernels, in which case `modprobe` is a no-op) and is pulled in by any conntrack-based bridge/firewall traffic anyway; the `modules-load.d` entry makes boot behavior explicit instead of incidental.
- [In the default podman scenario (privileged), `modprobe` and `sysctl -w` act on the podman machine's kernel, not an isolated environment] → Mitigation (D7): `prepare.yml` captures the six key values before converge and `cleanup.yml` restores them after verify (final cleanup step, before destroy). Loaded modules remain loaded (no `rmmod`). Standalone `converge`/`idempotence` invocations do not trigger the restore — accepted on the disposable libkrun machine.
- [A distro where a key is still absent (kernel built without the feature) would now fail loudly or report changed forever] → The `failed_when: false` masking is gone, so the idempotence gate surfaces it and forces an explicit decision (probe or skip) instead of silent suppression. Accepted: loud failure beats silent masking.
- [`sysctl -p` on a changed run re-applies every entry in `/etc/sysctl.conf`] → Pre-existing behavior (`reload` was already enabled); components sharing the file may have runtime values re-synced to file values when one of our keys changes. Accepted.

## Migration Plan

No user-facing migration. First converge on existing hosts: `modprobe nf_conntrack` (often a no-op), one `/etc/modules-load.d/nf_conntrack.conf` entry, and at most one runtime `sysctl -w` if the limit differs. The molecule scenario image is rebuilt once (gains `procps-ng`, gains the `/lib/modules` mount). Rollback is a straight revert of `tasks/prereq.yml` and the molecule files.

## Open Questions

- (Resolved during implementation) The guard question is settled by D4: the guards are removed. The original concern — that podman containers report `podman` and the tasks run in the scenario — was wrong for podman 6.0.2 (`container=oci` → `virtualization_type: container` → tasks skipped). The platform enablement (D5) plus machine-state bookkeeping (D7) replaces the guard's protective role for the test environment.
