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

    args = parser.parse_args()

    if args.command == "list":
        cmd_list()
    elif args.command == "show":
        cmd_show(args.iface)
    elif args.command == "status":
        cmd_status()
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
    for line in routes:
        print(line)


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
            result.append(line)
    return result


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
    routes = json.loads(result.stdout)

    lines = []
    for route in routes:
        dst = route.get('dst', 'unknown')
        dev = route.get('dev', '?')
        gateway = route.get('gateway')
        metric = route.get('metric')

        line = f"{dst}"
        if gateway:
            line += f" via {gateway}"
        line += f" dev {dev}"
        if metric is not None:
            line += f" metric {metric}"

        lines.append(line)
    return lines


if __name__ == "__main__":
    main()
