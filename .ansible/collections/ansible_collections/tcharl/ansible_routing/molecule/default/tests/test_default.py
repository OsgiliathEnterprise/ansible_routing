"""Role testing files using testinfra."""


def test_masquerade_enabled(host):
    with host.sudo():
        command = """firewall-cmd --zone=public --query-masquerade | \
        grep -c yes"""
        cmd = host.run(command)
    assert '1' in cmd.stdout


def test_redirect_rule_set(host):
    with host.sudo():
        command = """firewall-cmd --query-rich-rule=\"rule family=\"ipv4\" \
        forward-port port=\"6752\" \
        protocol=\"tcp\" to-port=\"22\" to-addr=\"192.168.1.10\" \
        log prefix=\"ssh-to-guest\"\" | \
        grep -c yes"""
        cmd = host.run(command)
    assert '1' in cmd.stdout


def test_redirect_rule_to_host_set(host):
    with host.sudo():
        command = """firewall-cmd --query-rich-rule=\"rule family=\"ipv4\" \
        forward-port port=\"6755\" \
        protocol=\"tcp\" to-port=\"22\" to-addr=\"127.0.0.1\" \
        log prefix=\"host-forwarding\"\" | \
        grep -c yes"""
        cmd = host.run(command)
    assert '1' in cmd.stdout


def test_port_is_opened(host):
    with host.sudo():
        command = """firewall-cmd --zone=public --query-port=\"6753/tcp\" \
        | grep -c yes"""
        cmd = host.run(command)
    assert '1' in cmd.stdout
