# Tasks: add molecule idempotence testing

## 1. Enable the idempotence gate

- [x] 1.1 Uncomment `- idempotence` in `molecule/default/molecule.yml` test_sequence, at its standard position between `converge` and `side_effect` (design D1)

## 2. Accurate change reporting

- [x] 2.1 In `molecule/default/prepare.yml`, register the raw wait result as `systemd_status` and replace the blanket `changed_when: false` with `changed_when: "'running' not in systemd_status.stdout"` (design D2)
- [x] 2.2 Fix the typo in `tasks/port-forwarding.yml`: `foward_rule.to_ansible_host` → `forward_rule.to_ansible_host` in the when-clause that includes `port-forwarding-to-host.yml` (design D3)

## 3. Idempotence discovery loop

- [x] 3.1 Run `tox -e idempotence` and record every task that reports changed during the second converge run
- [x] 3.2 For each offender, apply the design D2 policy: prefer module-native change detection; for command-based tasks use a registered-output expression or an explicit prior-state check (e.g., `firewall-cmd --query-rich-rule`); allow blanket `changed_when: false` only for provably read-only tasks, with a comment documenting why
- [x] 3.3 Re-run `tox -e idempotence` until the second converge run reports zero changed tasks

*Discovery result (run of `molecule create converge idempotence`, fedora:44 podman platform): the second converge reported **zero** changed tasks — no offenders found, so 3.2 required no code changes. All first-run changes were legitimate one-time transitions (package installs, firewalld enable/start, rich rules, source, port). Note: standalone `molecule idempotence` requires prior create+converge state ("Instances not converged" otherwise); the full `tox` env_list order or `molecule test` provides that state.*

## 4. Verification

- [x] 4.1 Run `tox -e test-exec` (`molecule test`) — full sequence including the new idempotence step and the existing testinfra verify tests pass
- [x] 4.2 Run `tox -e lint` (yamllint, flake8, ansible-lint) with no new findings
