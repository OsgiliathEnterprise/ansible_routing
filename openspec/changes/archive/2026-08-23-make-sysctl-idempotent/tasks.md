## 1. Kernel module loading

- [x] 1.1 Add `nf_conntrack` to the modprobe loop in `tasks/prereq.yml` (alongside `br_netfilter`, same `state: present`, `persistent: present`, and container guard), keeping the task first in the file so the keys exist before the sysctl tasks run. Verify: `ansible-playbook --syntax-check molecule/common/converge.yml` passes and the rendered loop contains both `br_netfilter` and `nf_conntrack`.

## 2. Sysctl task fixes

- [x] 2.1 Remove `failed_when: false`, `changed_when: false`, and the `# TODO improve this...` comment from the "Increase conntrack max" task, keeping `sysctl_set: true`, `state: present`, `reload: true`, `become: true`, and the `when` guard. Verify: `grep -nE "failed_when|changed_when" tasks/prereq.yml` returns no matches.
- [x] 2.2 Normalize `sysctl_set: yes` to `sysctl_set: true` on the first two sysctl tasks so all six tasks use the same boolean style. Verify: `grep -n "sysctl_set" tasks/prereq.yml` shows `true` for all six tasks.

## 3. Molecule platform enablement and machine-state bookkeeping

- [x] 3.1 Remove the seven `when: not ansible_facts.virtualization_type == "container"` guards from `tasks/prereq.yml` (modprobe task + six sysctl tasks) so the tasks run on container platforms. Verify: `grep -n "virtualization_type" tasks/prereq.yml` returns no matches.
- [x] 3.2 Add `procps-ng` to the `dnf -y install` line in `molecule/common/Dockerfile.j2` (provides the `sysctl` binary the module requires; `modprobe` already exists via `kmod`). Verify: after `molecule create`, `podman exec <container> sysctl -n net.ipv4.ip_forward` succeeds.
- [x] 3.3 Update the podman platform in `molecule/default/molecule.yml`: add volume `/lib/modules:/lib/modules:ro` (so `modprobe` finds module files matching the machine kernel) and set `network: host` (so the container shares the machine's netns — sysctl writes hit the machine, and global keys like `net.netfilter.nf_conntrack_max` are writable; remove the now-meaningless `dns_servers`). Verify: after `molecule create`, the container IP equals the machine IP, `podman exec <container> modprobe -n br_netfilter` (dry-run) succeeds, and `podman exec <container> sysctl -w net.netfilter.nf_conntrack_max=65536` succeeds.
- [x] 3.4 In `molecule/default/prepare.yml`, capture the machine's current values of the six role-managed keys (`sysctl -n <key>` inside the container, `failed_when: false`, documented read-only `changed_when: false`) and write `key=value` lines to `/etc/molecule-sysctl-backup.conf` inside the container, using an `__absent__` sentinel for keys that do not exist yet (empty `stdout` via `default(value, true)`).
- [x] 3.5 Create `molecule/default/cleanup.yml` (runs at molecule 25's final `cleanup` sequence step, after verify and before destroy; `ignore_unreachable: true` so the first cleanup position — before create — is a no-op): restore each non-sentinel `key=value` line via `sysctl -w` inside the container (best-effort: `failed_when: false`, a failed restore must not block `molecule destroy`), and remove the backup file.

## 4. Verification

- [x] 4.1 Run `tox -e lint` and verify yamllint, flake8, and ansible-lint all pass (re-run after the section 3 edits).
- [x] 4.2 Run `tox -e idempotence` (molecule double converge, default podman scenario) and verify the prereq tasks **execute, not skip** (the first converge shows them running) and the idempotence step reports 0 changed tasks.
- [x] 4.3 Run `tox -e test-exec` (full `molecule test` including testinfra verify and the cleanup restore) and verify all steps pass.
- [x] 4.4 Verify machine-state bookkeeping: capture the six key values via `podman machine ssh sysctl -n ...` before the test and after `tox -e test-exec` — the values must match (cleanup restored them).
- [x] 4.5 On a VM from the parallels topology (when available), verify after a double converge: `lsmod | grep nf_conntrack` shows the module loaded, `sysctl net.netfilter.nf_conntrack_max` equals `1000000`, `/etc/modules-load.d/nf_conntrack.conf` exists, and the second converge reports 0 changed prereq tasks.
