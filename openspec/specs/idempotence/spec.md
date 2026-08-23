# idempotence Specification

## Purpose

Guarantees that converging the routing role against an already-converged host is a no-op, that every task reports change status accurately (derived from actual state, never blanket-suppressed), and that the molecule scenario enforces both as a test gate.

## Requirements

### Requirement: Re-convergence is a no-op
Converging the role against a host whose firewalld configuration already matches the desired state SHALL report zero changed tasks.

#### Scenario: Second converge run reports no changes
- **WHEN** the molecule scenario runs converge twice in a row on the same platform (the `idempotence` step)
- **THEN** the second run SHALL report 0 changed tasks and the idempotence check SHALL pass

#### Scenario: Firewall state is stable across re-convergence
- **WHEN** converge runs a second time against an already-converged host
- **THEN** the active and permanent firewalld configuration (zones, rich rules, ports, services, sources) SHALL be unchanged and subsequent verify tests SHALL still pass

### Requirement: Accurate change reporting
Every task that executes a command or can modify system state SHALL derive its changed status from actual state — module-native comparison, registered command output, or an explicit prior-state check. A blanket `changed_when: false` is permitted only for provably read-only tasks and MUST be documented as such in the task.

#### Scenario: Command-based wait task reports based on observed state
- **WHEN** the prepare wait command observes that systemd has already reached the running target before or during execution
- **THEN** the task SHALL report unchanged when no transition was needed, and changed only when it observed the system transitioning to running while waiting

#### Scenario: State-changing tasks are never blanket-suppressed
- **WHEN** a task can modify system state (packages, services, kernel parameters, firewall rules)
- **THEN** its changed status SHALL come from the module's own comparison or an explicit before/after check, and MUST NOT be hardcoded to `false`

#### Scenario: Kernel parameter tasks derive changed status from the sysctl module
- **WHEN** a prerequisite kernel parameter (sysctl) task executes on a host where the kernel modules exposing its target keys are loaded
- **THEN** the task's changed status SHALL come from the sysctl module's own comparison of the persistent configuration entry and the runtime value, and the task MUST NOT use `failed_when` or `changed_when` to suppress failures or change reporting

### Requirement: Idempotence is enforced as a test gate
The molecule scenario test sequence SHALL include the `idempotence` step between `converge` and `side_effect`, so that standard test runs fail when re-convergence produces changes.

#### Scenario: Non-idempotent change fails the test run
- **WHEN** any task reports changed during the second converge run
- **THEN** `molecule test` SHALL fail at the idempotence step, and `tox -e idempotence` (`molecule idempotence`) SHALL report the same failure

### Requirement: Host-targeted forwarding rules are applied
Port forward rules that target an Ansible-managed host via `to_ansible_host` (without `to_host` or `to_address`) SHALL be resolved to that host's IP and applied as a rich forward rule, exactly like `to_host` rules.

#### Scenario: Rule with only to_ansible_host is applied
- **WHEN** a zone's `port_forward_rules` entry defines `to_ansible_host` and neither `to_host` nor `to_address`
- **THEN** converge SHALL resolve the target host's IP, create the corresponding rich forward rule without error, and re-convergence SHALL not report it as changed

### Requirement: Prerequisite kernel parameters are applied idempotently
The role SHALL load the kernel modules that expose the prerequisite sysctl keys (`br_netfilter` and `nf_conntrack`) before configuring those keys, and SHALL persist the module loads so the keys exist across reboots. The role SHALL set each prerequisite kernel parameter both at runtime and in the persistent sysctl configuration file: IPv4 forwarding, IPv6 forwarding, bridge-nf-call-iptables, bridge-nf-call-ip6tables, bridge-nf-call-arptables, and the nf_conntrack connection-tracking limit. No prerequisite sysctl task SHALL fail or report change solely because a key was absent at runtime.

#### Scenario: Second converge reports no sysctl changes
- **WHEN** converge runs a second time against a host where the prerequisite kernel modules are loaded, the persistent configuration entries match, and the runtime values match
- **THEN** every prerequisite sysctl task SHALL report unchanged and no sysctl reload SHALL be triggered

#### Scenario: Kernel modules are loaded and persisted
- **WHEN** converge runs on a host where `nf_conntrack` or `br_netfilter` is not yet loaded
- **THEN** the role SHALL load the module and record it for loading at boot, and a subsequent re-convergence SHALL report the module loads as unchanged

#### Scenario: Conntrack limit is applied without suppression
- **WHEN** converge runs on a host where the `nf_conntrack` module was not previously loaded
- **THEN** the role SHALL load the module before configuring `net.netfilter.nf_conntrack_max`, apply the limit at runtime and persistently, and the task SHALL NOT rely on `failed_when` or `changed_when` to hide failures
