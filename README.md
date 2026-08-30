# etcnetpy

A pure-Python, stdlib-only CLI for reading and writing [etcnet](https://en.altlinux.org/Etcnet)
(`/etc/net`) network configuration on ALT Linux — aiming for `nmcli`-level convenience,
without any third-party dependencies.

Personal learning project: hand-rolled `argparse`, no frameworks, no external libraries.

## Why

etcnet configures network interfaces through plain files under `/etc/net/ifaces/<iface>/`
(`options`, `ipv4address`, `ipv4route`, ...). Editing them by hand works, but there's no
`nmcli`-style tool to inspect, diff, or safely write them. etcnetpy is that tool.

## Usage

Commands follow an `nmcli`-style noun-verb structure:

```sh
# inspect interfaces
python3 main.py iface list                          # eth0 (static), eth1 (dhcp)
python3 main.py iface show eth0                      # options / ipv4address / ipv4route

# compare config on disk vs live kernel state
python3 main.py status                                # live addresses & routes (ip -j)
python3 main.py diff                                  # config vs live, per interface

# write config
python3 main.py address add eth0 192.168.1.10/24
python3 main.py address add eth0 192.168.1.20/24 --replace

python3 main.py route add eth0 default via 192.168.1.1
python3 main.py route add eth0 192.168.2.0/24 via 192.168.1.254 --replace
```

Writes validate input (`ipaddress` stdlib module), detect no-op duplicates, and reject
missing/invalid interfaces or addresses with a non-zero exit code.

`NETWORK` currently points at `testdata/ifaces/` for local development/testing rather
than the real `/etc/net/ifaces/`.

## Current features

- `iface list` / `iface show <iface>` — inspect parsed config
- `status` — live network state (`ip -j addr/route show`)
- `diff` — config vs live state, per interface
- `address add <iface> <ip>/<mask> [--replace]`
- `route add <iface> <dst> via <gateway> [--replace]`

## Roadmap

- `bond create <name> --slave <ifaces...>` — create a bonded interface (802.3ad / mode 4)
- `vlan create <iface> <vid>` — create a VLAN sub-interface
- `iface up` / `iface down` — apply config via `ifup`/`ifdown`
- `address del` / `route del`
- atomic writes + backup before overwriting config files
- `try` — apply + timed confirm + auto-rollback, netplan-style
