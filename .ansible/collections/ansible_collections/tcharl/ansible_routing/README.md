Routing
=========

* Galaxy: [![Ansible Galaxy](https://img.shields.io/badge/galaxy-tcharl.ansible_routing-660198.svg?style=flat)](https://galaxy.ansible.com/tcharl/ansible_routing)
* Lint & Tests: ![Molecule](https://github.com/OsgiliathEnterprise/ansible-routing/workflows/Molecule/badge.svg)
* Chat: [![Join the chat at https://gitter.im/OsgiliathEnterprise/platform](https://badges.gitter.im/OsgiliathEnterprise/platform.svg)](https://gitter.im/OsgiliathEnterprise/platform?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)

This role let you configure simple port or port/IP redirections using firewalld masquerade

Requirements
------------

Ansible :-), but also some [collections](./requirements-collections.yml) and some [roles](./requirements.yml)

Role Variables
--------------

```
firewalld_zones:
  - name: public # optional
    nics: # optional, will take all the network interfaces of the machine by default
      - eth0 # optional
    masquerade: true
    port_forward_rules:
      - port_forward_rule: ssh-to-guest-ip
        family: ipv4 # optional
        from_port: 6752
        protocol: tcp # optional
        to_address: 192.168.1.10
        to_port: 22
     - port_forward_rule: ssh-to-ansible-host-forward
        family: ipv4 # optional
        from_port: 6754
        protocol: tcp # optional
        to_host: myhost.osgiliath.test
        to_port: 22
    enabled_services:
      - service: ssh
    enabled_ports:
      - port: 6753
        protocol: tcp 
    enabled_port_ranges:
      - port_range: 6753-7000
        protocol: tcp 
```

License
-------

[Apache-2](https://www.apache.org/licenses/LICENSE-2.0)

Author Information
------------------

* Twitter [@tcharl](https://twitter.com/Tcharl)
* Github [@tcharl](https://github.com/Tcharl)
* LinkedIn [Charlie Mordant](https://www.linkedin.com/in/charlie-mordant-51796a97/)
