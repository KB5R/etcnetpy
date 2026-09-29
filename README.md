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

# create default config for live interfaces missing from /etc/net/ifaces (bare metal after install)
python3 main.py iface init

# apply config for real (calls ifup/ifdown)
python3 main.py iface up eth0
python3 main.py iface down eth0

# compare config on disk vs live kernel state
python3 main.py status                                # live addresses & routes (ip -j)
python3 main.py diff                                  # config vs live, per interface

# write config
python3 main.py address add eth0 192.168.1.10/24
python3 main.py address add eth0 192.168.1.20/24 --replace

python3 main.py route add eth0 default via 192.168.1.1
python3 main.py route add eth0 192.168.2.0/24 via 192.168.1.254 --replace

# apply the change for real: restart the whole network, auto-revert if not
# confirmed in time (netplan-style safety net for remote changes)
python3 main.py try --timeout 120
python3 main.py confirm

# create bonded and vlan interfaces
python3 main.py bond create bond0 --slave eth0 eth1
python3 main.py vlan create bond0 77
```

Writes validate input (`ipaddress` stdlib module), detect no-op duplicates, and reject
missing/invalid interfaces or addresses with a non-zero exit code. When a write would
overwrite an existing `ipv4address`/`ipv4route` file (`--replace`), the previous content
is copied to `<file>.bak.<timestamp>` first.

`NETWORK` defaults to the real `/etc/net/ifaces/`. For local development/testing against
the bundled fixtures, set `ETCNETPY_NETWORK_DIR=testdata/ifaces`:

```sh
ETCNETPY_NETWORK_DIR=testdata/ifaces python3 main.py iface list
```

## Packaging (RPM)

`etcnetpy.spec` builds a `noarch` RPM for ALT Linux: a single stdlib-only script installed
as `/usr/sbin/etcnetpy`, `Requires: /usr/bin/python3 /sbin/ifup /sbin/ifdown /sbin/service /sbin/ip`
(i.e. the `etcnet` package). Build with `rpm-build` + `rpm-build-python3` (the latter is needed
for `find-provides`/`find-requires` to process the Python shebang):

```sh
mkdir -p ~/RPM/{BUILD,RPMS,SRPMS,SPECS,SOURCES}
tar -cf ~/RPM/SOURCES/etcnetpy-0.2.0.tar --transform 's,^,etcnetpy-0.2.0/,' main.py README.md LICENSE
cp etcnetpy.spec ~/RPM/SPECS/
cd ~/RPM/SPECS && rpmbuild -ba etcnetpy.spec
```

Built and smoke-tested inside a clean `alt:p10` container (avoids touching a real machine's
package database): install pulls in `etcnet` correctly via the `Requires`, `etcnetpy --help`
and `iface list` both work post-install, and `ETCNETPY_NETWORK_DIR` still overrides the
`/etc/net/ifaces` default for testing. Note: `rpmbuild` refuses to run as root on ALT — build
as a regular user.

## Current features

- `iface list` / `iface show <iface>` — inspect parsed config (etcnet's own `default`/`unknown`
  template directories are filtered out, only real interfaces are shown)
- `iface init` — create default (`BOOTPROTO=dhcp`) config for live interfaces with no directory under `/etc/net/ifaces` (common right after a bare-metal install, when a NIC stays down because etcnet has no config for it)
- `iface up <iface>` / `iface down <iface>` — apply one interface's config for real via `ifup`/`ifdown`
- `status` — live network state (`ip -j addr/route show`)
- `diff` — config vs live state, per interface (also skips `default`/`unknown`)
- `address add <iface> <ip>/<mask> [--replace]`
- `route add <iface> <dst> via <gateway> [--replace]`
- `bond create <name> --slave <ifaces...>` — create a bonded interface (802.3ad / mode 4 only)
- `vlan create <iface> <vid>` — create a VLAN sub-interface (`<iface>.<vid>`)
- `try [--timeout SEC, default 120]` — apply pending config changes for real via
  `service network restart` (whatever is currently written to every interface's files,
  not just one), after first recording the live address/route state of every interface.
  If `confirm` isn't run within the timeout, a background watcher (detached, survives the
  restart dropping your SSH session) reverts every interface back to the recorded state
  via `ip addr`/`ip route` — netplan-`try`-style safety net for remote changes. Reconnecting
  after a real restart routinely took 30-50s in testing, so the default leaves headroom;
  raise `--timeout` further for a slow link
- `confirm` — cancel the pending auto-revert, keeping the restarted network state as-is
  (the config files were already written by `address add`/`route add` etc. before `try` ran —
  `confirm` only stops the revert, it doesn't write anything itself)

`bond create` refuses if a slave is missing, already has an address/route, or already
belongs to another bond (writes `BONDOPTIONS='miimon=100'`, required by etcnet's own
`create-bond` script). `vlan create` validates the VLAN id is in 1-4095.

Tested end-to-end against a real ALT Linux VM:
- `iface init` + `iface up` brings a NIC with no prior etcnet config up with a DHCP lease.
- `bond create` + `iface up` produces a real kernel 802.3ad bond (`/proc/net/bonding/<name>`
  confirms slaves enslaved); `address add` + a down/up cycle applies a static IP to it.
- `vlan create` + `iface up` on top of that bond produces a real `<bond>.<vid>@<bond>`
  kernel VLAN device.
- `ifup` on an already-up interface exits 2 (not an error — etcnet's own convention);
  `iface up` treats that as a no-op instead of a failure.
- `try` + no `confirm`: ran `service network restart` on all 4 NICs, then let the timeout
  expire — every interface reverted to its exact pre-restart address, and the watcher
  cleaned up its own state files.
- `try` + `confirm` sent within the window: the restarted state was kept, and it was
  still there well past the original timeout — the revert never fired. The watcher
  process (`start_new_session=True`) survives `service network restart` dropping the
  SSH connection, which is the whole point — reconnecting after a real restart routinely
  took 30-50s, comfortably inside a `--timeout 120` window used for that test.

## Roadmap

- `address del` / `route del`
