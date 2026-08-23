# Proposal: make the prereq sysctl tasks idempotent

## Why

The `ansible.posix.sysctl` tasks in `tasks/prereq.yml` are not idempotent. When a sysctl key does not exist at runtime because the kernel module that exposes it is not loaded, the module (with `sysctl_set: true` + `state: present`) reports `changed: true` on **every** run even though it performs no work, and its `sysctl -p` reload fails on the missing key. The role never loads the `nf_conntrack` module, so `net.netfilter.nf_conntrack_max` may not exist; the task is therefore papered over with blanket `failed_when: false` and `changed_when: false` plus a `# TODO improve this, it is not idempotent on some distro` comment. This violates the `idempotence` capability (accurate change reporting; no-op re-convergence) and leaves the conntrack limit silently unapplied on hosts where the module is not loaded.

## What Changes

- Load the `nf_conntrack` kernel module in the existing `prereq.yml` modprobe loop, alongside `br_netfilter` (`state: present`, `persistent: present`), so that every prerequisite sysctl key is guaranteed to exist before it is configured.
- Remove the `failed_when: false`, `changed_when: false` workarounds and the TODO comment from the `nf_conntrack_max` task: with the key guaranteed to exist, the module's native comparison (persistent file entry + runtime value) is accurate, so `changed` is reported only on a real state difference.
- Normalize boolean style in the existing sysctl tasks (`yes` → `true`) for consistency.
- Remove the `when: not ansible_facts.virtualization_type == "container"` guards from the prereq tasks so they also run on container platforms. Verified against the installed toolchain: podman 6.0.2 sets `container=oci` (not `container=podman`), so Ansible resolves `virtualization_type: container` and the guard silently skipped **every** prereq task in the molecule scenario — the idempotence gate had zero coverage of these tasks.
- Enable the molecule podman platform to actually execute these tasks: install `procps-ng` (the `sysctl` binary) in the scenario image, mount the podman machine's `/lib/modules` read-only so `modprobe` can find module files matching the machine kernel, and run the platform with `network: host` — with the default bridge network the container's own netns would scope per-netns sysctls to the container and reject the global `nf_conntrack_max` key (`Operation not permitted`), while the role's tasks are explicitly about the machine's NIC and kernel.
- Keep the podman machine's kernel state intact across test runs: `prepare.yml` captures the machine's original values of the six prerequisite keys before converge, and a new `cleanup.yml` (molecule 25 has no `posttest` step; the final `cleanup` sequence step runs after verify and before destroy) restores them after the test.

## Capabilities

### Modified Capabilities

- `idempotence`: prerequisite sysctl tasks must derive their changed status from the `sysctl` module's own comparison (no `failed_when`/`changed_when` suppression), and re-convergence against a host where the prerequisite kernel modules are loaded and the values already match MUST report zero changed tasks.

## Impact

- `tasks/prereq.yml`: modprobe loop gains `nf_conntrack`; six sysctl tasks lose their change/failure suppression and gain accurate, module-native change reporting.
- Host behavior: hosts that did not previously have `nf_conntrack` loaded will have it loaded at converge and persisted to `/etc/modules-load.d/`, so it is loaded at boot before `systemd-sysctl` applies `/etc/sysctl.conf` (the persisted `nf_conntrack_max` entry is then active from the first boot).
- `molecule/common/Dockerfile.j2`, `molecule/default/molecule.yml`, `molecule/default/prepare.yml`, and a new `molecule/default/cleanup.yml`: platform enablement and machine-state bookkeeping as described above.
- Host behavior on container targets: with the guards removed, converging against a container target now loads the modules and sets the sysctls on the host kernel (previously skipped). The only container target in practice is the molecule podman scenario; production targets are VMs.
- Verification: `tox -e idempotence` (molecule default scenario) now genuinely exercises these tasks (they run, they are not skipped), so the double-converge gate covers them directly.
