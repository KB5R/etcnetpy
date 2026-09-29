Name: etcnetpy
Version: 0.2.0
Release: alt1

Summary: nmcli-style CLI for etcnet (/etc/net) network configuration
License: MIT
Group: System/Configuration/Networking
Url: https://github.com/KB5R/etcnetpy

Source: %name-%version.tar

BuildArch: noarch

Requires: /usr/bin/python3
Requires: /sbin/ifup
Requires: /sbin/ifdown
Requires: /sbin/service
Requires: /sbin/ip

%description
etcnetpy is a pure-Python, stdlib-only CLI for reading and writing etcnet
(/etc/net) network configuration on ALT Linux, aiming for nmcli-level
convenience without any third-party dependencies.

Features interface listing/inspection, address/route management, bond and
VLAN creation, and a netplan-try-style "try + confirm" workflow that applies
a network restart and automatically reverts it if not confirmed in time -
useful for making network changes on a remote machine without risking being
locked out.

%prep
%setup -q

%install
mkdir -p %buildroot%_sbindir
install -m755 main.py %buildroot%_sbindir/etcnetpy

%files
%_sbindir/etcnetpy
%doc README.md LICENSE

%changelog
* Tue Sep 29 2026 Freeman <mihail.ku.88@gmail.com> 0.2.0-alt1
- add interactive menu (run with no arguments, or 'menu')
- fix: address add now switches BOOTPROTO dhcp->static so ipv4address
  actually gets applied by etcnet (was silently ignored before)
- fix: route add no longer drops extra fields (metric, table, ...) from
  existing routes when appending a new one
- fix: bond create rejects slaves still on BOOTPROTO=dhcp
- fix: diff now compares full ip/mask instead of bare ip
- fix: try now checks the return code of 'service network restart'

* Tue Sep 02 2026 Freeman <mihail.ku.88@gmail.com> 0.1.0-alt1
- initial build
