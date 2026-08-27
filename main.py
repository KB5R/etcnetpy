import argparse
import json
import subprocess
from pathlib import Path

NETWORK = Path('testdata/ifaces/')


def main():
    parser = argparse.ArgumentParser(description="etcnetpy - network configuration for /etc/net")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("list", help="list interfaces from config")

    show_parser = subparsers.add_parser("show", help="show config for one interface")
    show_parser.add_argument("iface", help="interface name, e.g. eth0")

    subparsers.add_parser("status", help="show current live network state")

    subparsers.add_parser("diff", help="compare config with live network state")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list()
    elif args.command == "show":
        cmd_show(args.iface)
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
        return

    iface = read_iface(item)
    print(f"options: {iface['options']}")
    print(f"ipv4address: {iface['ipv4address']}")
    print(f"ipv4route: {iface['ipv4route']}")


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
        ip, sep, mask = addr.partition("/")
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
