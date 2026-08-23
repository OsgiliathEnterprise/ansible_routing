# idempotence Specification (delta)

## MODIFIED Requirements

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

## ADDED Requirements

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
