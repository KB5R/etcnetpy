import argparse
import json
import subprocess
import sys
from pathlib import Path
import ipaddress

NETWORK = Path('testdata/ifaces/')


def main():
    parser = argparse.ArgumentParser(description="etcnetpy - network configuration for /etc/net")
    subparsers = parser.add_subparsers(dest="command")

    iface_parser = subparsers.add_parser("iface", help="interface config")
    iface_subparsers = iface_parser.add_subparsers(dest="action")
    iface_subparsers.add_parser("list", help="list interfaces from config")
    iface_show_parser = iface_subparsers.add_parser("show", help="show config for one interface")
    iface_show_parser.add_argument("iface", help="interface name, e.g. eth0")

    address_parser = subparsers.add_parser("address", help="ipv4 address config")
    address_subparsers = address_parser.add_subparsers(dest="action")
    address_add_parser = address_subparsers.add_parser("add", help="add ipv4 address to interface config")
    address_add_parser.add_argument("iface", help="interface name, e.g. eth0")
    address_add_parser.add_argument("ip", help="ip address with mask, e.g. 192.168.1.10/24")

    subparsers.add_parser("status", help="show current live network state")
    subparsers.add_parser("diff", help="compare config with live network state")

    args = parser.parse_args()

    if args.command == "iface":
        if args.action == "list":
            cmd_list()
        elif args.action == "show":
            cmd_show(args.iface)
        else:
            iface_parser.print_help()
    elif args.command == "address":
        if args.action == "add":
            cmd_address(args.iface, args.ip)
        else:
            address_parser.print_help()
    elif args.command == "status":
        cmd_status()
    elif args.command == "diff":
        cmd_diff()
    else:
        parser.print_help()


def cmd_list():
    for item in NETWORK.iterdir():
        if item.is_dir():
            print(item.name)


def cmd_show(iface_name):
    item = NETWORK / iface_name
    if not item.is_dir():
        print(f"interface not found: {iface_name}")
        sys.exit(1)

    iface = read_iface(item)
    print(f"options: {iface['options']}")
    print(f"ipv4address: {iface['ipv4address']}")
    print(f"ipv4route: {iface['ipv4route']}")


def cmd_address(iface_name, addr):
    item = NETWORK / iface_name
    if not item.is_dir():
        print(f"interface not found: {iface_name}")
        sys.exit(1)

    write_address(item, addr)


def write_address(item, addr):
    try:
        ipaddress.ip_interface(addr)
    except ValueError:
        print(f"invalid address: {addr}")
        sys.exit(1)

    existing = parse_ipv4address(item)
    if addr in existing:
        print(f"address already present: {addr}")
        return

    path = item / "ipv4address"
    lines = existing + [addr]
    path.write_text("\n".join(lines) + "\n", encoding='utf-8')

    print(f"added {addr} to {item.name}")

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

    for item in NETWORK.iterdir():
        if not item.is_dir():
            continue

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
