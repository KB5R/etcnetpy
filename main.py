import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import ipaddress

NETWORK = Path('testdata/ifaces/')
TRY_DIR = NETWORK.parent / "etcnetpy-try"

# etcnet reserves these directory names for its own templates/fallback config,
# they are not real network interfaces.
RESERVED_IFACES = {"default", "unknown"}


def iter_ifaces():
    for item in NETWORK.iterdir():
        if item.is_dir() and item.name not in RESERVED_IFACES:
            yield item


def main():
    parser = argparse.ArgumentParser(description="etcnetpy - network configuration for /etc/net")
    subparsers = parser.add_subparsers(dest="command")

    iface_parser = subparsers.add_parser("iface", help="interface config")
    iface_subparsers = iface_parser.add_subparsers(dest="action")
    iface_subparsers.add_parser("list", help="list interfaces from config")
    iface_show_parser = iface_subparsers.add_parser("show", help="show config for one interface")
    iface_show_parser.add_argument("iface", help="interface name, e.g. eth0")
    iface_subparsers.add_parser("init", help="create default config for live interfaces missing from /etc/net/ifaces")
    iface_up_parser = iface_subparsers.add_parser("up", help="apply interface config (ifup)")
    iface_up_parser.add_argument("iface", help="interface name, e.g. eth0")
    iface_down_parser = iface_subparsers.add_parser("down", help="bring interface down (ifdown)")
    iface_down_parser.add_argument("iface", help="interface name, e.g. eth0")

    address_parser = subparsers.add_parser("address", help="ipv4 address config")
    address_subparsers = address_parser.add_subparsers(dest="action")
    address_add_parser = address_subparsers.add_parser("add", help="add ipv4 address to interface config")
    address_add_parser.add_argument("iface", help="interface name, e.g. eth0")
    address_add_parser.add_argument("ip", help="ip address with mask, e.g. 192.168.1.10/24")
    address_add_parser.add_argument("--replace", action="store_true", help="replace existing addresses instead of appending")

    route_parser = subparsers.add_parser("route", help="ipv4 route config")
    route_subparsers = route_parser.add_subparsers(dest="action")
    route_add_parser = route_subparsers.add_parser("add", help="add ipv4 route to interface config")
    route_add_parser.add_argument("iface", help="interface name, e.g. eth0")
    route_add_parser.add_argument("dst", help="destination, e.g. default or 192.168.2.0/24")
    route_add_parser.add_argument("via", choices=["via"], help="literal 'via'")
    route_add_parser.add_argument("gateway", help="gateway ip, e.g. 192.168.1.1")
    route_add_parser.add_argument("--replace", action="store_true", help="replace existing routes instead of appending")

    bond_parser = subparsers.add_parser("bond", help="bond interface config")
    bond_subparsers = bond_parser.add_subparsers(dest="action")
    bond_create_parser = bond_subparsers.add_parser("create", help="create a bonded interface (802.3ad)")
    bond_create_parser.add_argument("name", help="bond interface name, e.g. bond0")
    bond_create_parser.add_argument("--slave", nargs="+", required=True, help="slave interfaces, e.g. eth0 eth1")

    vlan_parser = subparsers.add_parser("vlan", help="vlan interface config")
    vlan_subparsers = vlan_parser.add_subparsers(dest="action")
    vlan_create_parser = vlan_subparsers.add_parser("create", help="create a vlan sub-interface")
    vlan_create_parser.add_argument("iface", help="parent interface name, e.g. eth0")
    vlan_create_parser.add_argument("vid", type=int, help="vlan id, 1-4095")

    subparsers.add_parser("status", help="show current live network state")
    subparsers.add_parser("diff", help="compare config with live network state")

    try_parser = subparsers.add_parser("try", help="restart the whole network (service network restart), auto-revert to prior live state if not confirmed in time")
    try_parser.add_argument("--timeout", type=int, default=120, help="seconds before auto-revert (default 120)")
    subparsers.add_parser("confirm", help="confirm a pending 'try', keeping the change")

    args = parser.parse_args()

    if args.command == "iface":
        if args.action == "list":
            cmd_list()
        elif args.action == "show":
            cmd_show(args.iface)
        elif args.action == "init":
            cmd_iface_init()
        elif args.action == "up":
            cmd_iface_up(args.iface)
        elif args.action == "down":
            cmd_iface_down(args.iface)
        else:
            iface_parser.print_help()
    elif args.command == "address":
        if args.action == "add":
            cmd_address(args.iface, args.ip, args.replace)
        else:
            address_parser.print_help()
    elif args.command == "route":
        if args.action == "add":
            cmd_route(args.iface, args.dst, args.gateway, args.replace)
        else:
            route_parser.print_help()
    elif args.command == "bond":
        if args.action == "create":
            cmd_bond_create(args.name, args.slave)
        else:
            bond_parser.print_help()
    elif args.command == "vlan":
        if args.action == "create":
            cmd_vlan_create(args.iface, args.vid)
        else:
            vlan_parser.print_help()
    elif args.command == "status":
        cmd_status()
    elif args.command == "diff":
        cmd_diff()
    elif args.command == "try":
        cmd_try(args.timeout)
    elif args.command == "confirm":
        cmd_confirm()
    else:
        parser.print_help()


def cmd_list():
    for item in iter_ifaces():
        options = parse_options(item)
        bootproto = options.get("BOOTPROTO", "unset")
        print(f"{item.name} ({bootproto})")


def cmd_show(iface_name):
    item = NETWORK / iface_name
    if not item.is_dir():
        print(f"interface not found: {iface_name}")
        sys.exit(1)

    iface = read_iface(item)
    print(f"options: {iface['options']}")
    print(f"ipv4address: {iface['ipv4address']}")
    print(f"ipv4route: {iface['ipv4route']}")


def cmd_iface_init():
    live_links = get_live_links()
    existing = {item.name for item in iter_ifaces()}

    missing = [
        link for link in live_links
        if link["type"] != "loopback" and link["name"] not in existing
    ]

    if not missing:
        print("no missing interfaces found")
        return

    for link in missing:
        name = link["name"]
        item = NETWORK / name
        item.mkdir()
        lines = [
            "BOOTPROTO=dhcp",
            "TYPE=eth",
            "DISABLED=no",
        ]
        path = item / "options"
        path.write_text("\n".join(lines) + "\n", encoding='utf-8')
        print(f"created config for {name} (BOOTPROTO=dhcp)")


def cmd_iface_up(iface_name):
    item = NETWORK / iface_name
    if not item.is_dir():
        print(f"interface not found: {iface_name}")
        sys.exit(1)

    env = {**os.environ, 'VERBOSE': 'yes'}
    result = subprocess.run(['ifup', iface_name], capture_output=True, text=True, env=env)
    print(result.stdout, end='')
    print(result.stderr, end='', file=sys.stderr)

    if result.returncode == 2:
        # ifup uses exit code 2 for both "already up" and "disabled" - the
        # message above (printed via VERBOSE=yes) says which one it is.
        return
    if result.returncode != 0:
        sys.exit(result.returncode)

    print(f"{iface_name} up")


def cmd_iface_down(iface_name):
    item = NETWORK / iface_name
    if not item.is_dir():
        print(f"interface not found: {iface_name}")
        sys.exit(1)

    result = subprocess.run(['ifdown', iface_name], capture_output=True, text=True)
    print(result.stdout, end='')
    print(result.stderr, end='', file=sys.stderr)
    if result.returncode != 0:
        sys.exit(result.returncode)

    print(f"{iface_name} down")


def get_all_live_addrs():
    result = subprocess.run(
        ['ip', '-j', 'addr', 'show'],
        capture_output=True, text=True, check=True
    )
    interfaces = json.loads(result.stdout)
    addrs = {}
    for iface in interfaces:
        name = iface['ifname']
        if name == 'lo':
            continue
        addrs[name] = [
            f"{a['local']}/{a['prefixlen']}" for a in iface.get('addr_info', [])
            if a.get('family') == 'inet'
        ]
    return addrs


def get_all_live_routes():
    result = subprocess.run(
        ['ip', '-j', 'route', 'show'],
        capture_output=True, text=True, check=True
    )
    routes = json.loads(result.stdout)
    return [r for r in routes if r.get('dev') and r.get('dev') != 'lo']


def cmd_try(timeout):
    # Record the live state of every interface *before* restarting - this,
    # not any config file, is what gets restored if nobody confirms in time.
    baseline_addrs = get_all_live_addrs()
    baseline_routes = get_all_live_routes()

    TRY_DIR.mkdir(exist_ok=True)
    marker = TRY_DIR / "network.confirmed"
    marker.unlink(missing_ok=True)

    revert_lines = []
    for name, addrs in baseline_addrs.items():
        revert_lines.append(f'ip addr flush dev "{name}"')
        for addr in addrs:
            revert_lines.append(f'ip addr add {addr} dev "{name}"')
    revert_lines.append('ip route flush table main')
    for r in baseline_routes:
        if r.get("gateway"):
            revert_lines.append(f'ip route add {r["dst"]} via {r["gateway"]} dev "{r["dev"]}"')
        else:
            revert_lines.append(f'ip route add {r["dst"]} dev "{r["dev"]}"')

    watcher = TRY_DIR / "network.watch.sh"
    script = "\n".join([
        "#!/bin/bash",
        f'sleep {timeout}',
        f'if [ ! -f "{marker}" ]; then',
        *[f"  {line}" for line in revert_lines],
        'fi',
        f'rm -f "{marker}" "{watcher}"',
    ]) + "\n"
    watcher.write_text(script)

    # Launch the watcher *before* restarting, detached from this process and
    # this ssh session, so it still fires the revert even if the restart
    # itself drops our connection.
    subprocess.Popen(
        ['bash', str(watcher)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )

    result = subprocess.run(['service', 'network', 'restart'], capture_output=True, text=True)
    print(result.stdout, end='')
    print(result.stderr, end='', file=sys.stderr)

    print(f"network restarted - run 'confirm' within {timeout}s or it will be reverted")


def cmd_confirm():
    watcher = TRY_DIR / "network.watch.sh"
    if not watcher.is_file():
        print("no pending try")
        sys.exit(1)

    marker = TRY_DIR / "network.confirmed"
    marker.touch()
    print("confirmed, changes kept")


def cmd_address(iface_name, addr, replace=False):
    item = NETWORK / iface_name
    if not item.is_dir():
        print(f"interface not found: {iface_name}")
        sys.exit(1)

    write_address(item, addr, replace)


def backup_file(path):
    if not path.is_file():
        return

    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(f"{path.name}.bak.{timestamp}")
    shutil.copy2(path, backup_path)


def write_address(item, addr, replace=False):
    if "/" not in addr:
        print(f"invalid address: {addr} (mask required, e.g. 192.168.1.10/24)")
        sys.exit(1)

    try:
        ipaddress.ip_interface(addr)
    except ValueError:
        print(f"invalid address: {addr}")
        sys.exit(1)

    existing = parse_ipv4address(item)

    if replace:
        if existing == [addr]:
            print(f"address already present: {addr}")
            return
        lines = [addr]
    else:
        if addr in existing:
            print(f"address already present: {addr}")
            return
        lines = existing + [addr]

    path = item / "ipv4address"
    backup_file(path)
    path.write_text("\n".join(lines) + "\n", encoding='utf-8')

    print(f"added {addr} to {item.name}")


def cmd_route(iface_name, dst, gateway, replace=False):
    item = NETWORK / iface_name
    if not item.is_dir():
        print(f"interface not found: {iface_name}")
        sys.exit(1)

    write_route(item, dst, gateway, replace)


def write_route(item, dst, gateway, replace=False):
    if dst != "default":
        try:
            ipaddress.ip_network(dst, strict=False)
        except ValueError:
            print(f"invalid destination: {dst}")
            sys.exit(1)

    try:
        ipaddress.ip_address(gateway)
    except ValueError:
        print(f"invalid gateway: {gateway}")
        sys.exit(1)

    line = route_core({"dst": dst, "gateway": gateway})

    existing_routes = parse_ipv4route(item)
    existing_lines = [route_core(route) for route in existing_routes]

    if replace:
        if existing_lines == [line]:
            print(f"route already present: {line}")
            return
        lines = [line]
    else:
        if line in existing_lines:
            print(f"route already present: {line}")
            return
        lines = existing_lines + [line]

    path = item / "ipv4route"
    backup_file(path)
    path.write_text("\n".join(lines) + "\n", encoding='utf-8')

    print(f"added route '{line}' to {item.name}")


def cmd_bond_create(name, slaves):
    item = NETWORK / name
    if item.exists():
        print(f"interface already exists: {name}")
        sys.exit(1)

    if len(set(slaves)) != len(slaves):
        print(f"duplicate slave interfaces: {slaves}")
        sys.exit(1)

    for slave in slaves:
        slave_item = NETWORK / slave
        if not slave_item.is_dir():
            print(f"interface not found: {slave}")
            sys.exit(1)

        if parse_ipv4address(slave_item) or parse_ipv4route(slave_item):
            print(f"slave {slave} has address/route config, remove it first")
            sys.exit(1)

        master = find_bond_master(slave)
        if master:
            print(f"slave {slave} is already part of bond: {master}")
            sys.exit(1)

    item.mkdir()
    lines = [
        "TYPE=bond",
        "BONDMODE=4",
        "BONDOPTIONS='miimon=100'",
        f"HOST='{' '.join(slaves)}'",
        "BOOTPROTO=static",
    ]
    path = item / "options"
    path.write_text("\n".join(lines) + "\n", encoding='utf-8')

    print(f"created bond {name} with slaves: {', '.join(slaves)}")


def find_bond_master(slave):
    for item in iter_ifaces():
        options = parse_options(item)
        if options.get("TYPE") != "bond":
            continue
        host = options.get("HOST", "").strip("'\"")
        if slave in host.split():
            return item.name
    return None


def cmd_vlan_create(iface, vid):
    parent = NETWORK / iface
    if not parent.is_dir():
        print(f"interface not found: {iface}")
        sys.exit(1)

    if not 1 <= vid <= 4095:
        print(f"invalid vlan id: {vid} (must be 1-4095)")
        sys.exit(1)

    name = f"{iface}.{vid}"
    item = NETWORK / name
    if item.exists():
        print(f"interface already exists: {name}")
        sys.exit(1)

    item.mkdir()
    lines = [
        "TYPE=vlan",
        f"HOST={iface}",
        f"VID={vid}",
        "BOOTPROTO=static",
    ]
    path = item / "options"
    path.write_text("\n".join(lines) + "\n", encoding='utf-8')

    print(f"created vlan {name} on {iface}")


def cmd_status():
    addresses = get_live_addresses()
    routes = get_live_routes()

    print("-- addresses --")
    for name, addrs in addresses.items():
        print(f"{name}: {addrs}")

    print("-- routes --")
    for route in routes:
        print(format_route_line(route))


def cmd_diff():
    live_addresses = get_live_addresses()
    live_routes = get_live_routes()

    for item in iter_ifaces():
        name = item.name
        iface = read_iface(item)

        print(f"== {name} ==")
        diff_addresses(iface, live_addresses.get(name, []))
        diff_routes(iface, live_routes, name)




def diff_addresses(iface, live_addrs):
    config_ips = set()
    for addr in iface["ipv4address"]:
        ip, _, _ = addr.partition("/")
        config_ips.add(ip)

    live_ips = set(live_addrs)

    missing = config_ips - live_ips
    extra = live_ips - config_ips

    if not missing and not extra:
        print("  addresses match")
        return

    for ip in sorted(missing):
        print(f"  address in config but not live: {ip}")
    for ip in sorted(extra):
        print(f"  address live but not in config: {ip}")


def diff_routes(iface, live_routes, name):
    config_routes = set()
    for route in iface["ipv4route"]:
        config_routes.add(route_core(route))

    live_routes_for_iface = set()
    for route in live_routes:
        if route.get("dev") != name:
            continue
        live_routes_for_iface.add(route_core(route))

    missing = config_routes - live_routes_for_iface
    extra = live_routes_for_iface - config_routes

    if not missing and not extra:
        print("  routes match")
        return

    for line in sorted(missing):
        print(f"  route in config but not live: {line}")
    for line in sorted(extra):
        print(f"  route live but not in config: {line}")


def route_core(route):
    dst = route.get("dst", "unknown")
    gateway = route.get("gateway")

    line = f"{dst}"
    if gateway:
        line += f" via {gateway}"
    return line


def read_iface(item):
    return {
        "options": parse_options(item),
        "ipv4address": parse_ipv4address(item),
        "ipv4route": parse_ipv4route(item),
    }


def parse_options(item):
    path_options = item / "options"
    if not path_options.is_file():
        return {}

    result = {}
    text = path_options.read_text(encoding='utf-8')
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        key, sep, value = line.partition('=')
        if sep:
            result[key] = value
    return result


def parse_ipv4address(item):
    path_ipv4address = item / "ipv4address"
    if not path_ipv4address.is_file():
        return []

    result = []
    text = path_ipv4address.read_text(encoding='utf-8')
    for line in text.splitlines():
        line = line.strip()
        if line:
            result.append(line)
    return result


def parse_ipv4route(item):
    path_ipv4route = item / "ipv4route"
    if not path_ipv4route.is_file():
        return []

    result = []
    text = path_ipv4route.read_text(encoding='utf-8')
    for line in text.splitlines():
        line = line.strip()
        if line:
            result.append(parse_route_line(line))
    return result


def parse_route_line(line):
    tokens = line.split()
    dst = tokens[0]

    gateway = None
    if "via" in tokens:
        via_index = tokens.index("via")
        gateway = tokens[via_index + 1]

    return {"dst": dst, "gateway": gateway}


def get_live_links():
    result = subprocess.run(
        ['ip', '-j', 'link', 'show'],
        capture_output=True,
        text=True,
        check=True
    )
    links = json.loads(result.stdout)
    return [{"name": link["ifname"], "type": link["link_type"]} for link in links]


def get_live_addresses():
    result = subprocess.run(
        ['ip', '-j', 'addr', 'show'],
        capture_output=True,
        text=True,
        check=True
    )
    interfaces = json.loads(result.stdout)

    addresses = {}
    for iface in interfaces:
        name = iface['ifname']
        addresses[name] = [
            a['local'] for a in iface.get('addr_info', [])
            if a.get('family') == 'inet'
        ]
    return addresses


def get_live_routes():
    result = subprocess.run(
        ['ip', '-j', 'route', 'show'],
        capture_output=True,
        text=True,
        check=True
    )
    return json.loads(result.stdout)


def format_route_line(route):
    dev = route.get('dev', '?')
    metric = route.get('metric')

    line = route_core(route)
    line += f" dev {dev}"
    if metric is not None:
        line += f" metric {metric}"
    return line

if __name__ == "__main__":
    main()
