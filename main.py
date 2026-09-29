#!/usr/bin/python3
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import ipaddress

NETWORK = Path(os.environ.get('ETCNETPY_NETWORK_DIR', '/etc/net/ifaces/'))
TRY_DIR = NETWORK.parent / "etcnetpy-try"

# etcnet reserves these directory names for its own templates/fallback config,
# they are not real network interfaces.
RESERVED_IFACES = {"default", "unknown"}


def iter_ifaces():
    for item in NETWORK.iterdir():
        if item.is_dir() and item.name not in RESERVED_IFACES:
            yield item


def main():
    parser = argparse.ArgumentParser(
        description="etcnetpy - network configuration for /etc/net",
        epilog="run with no arguments (or 'menu') for an interactive menu",
    )
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

    subparsers.add_parser("menu", help="interactive menu (also runs by default with no arguments)")

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
    elif args.command == "menu" or args.command is None:
        run_menu()
    else:
        parser.print_help()


def prompt(message, default=None):
    suffix = f" [{default}]" if default else ""
    try:
        value = input(f"{message}{suffix}: ").strip()
    except EOFError:
        return None
    return value or default


def prompt_yes_no(message, default_no=True):
    hint = "y/N" if default_no else "Y/n"
    answer = prompt(f"{message} ({hint})", "")
    if answer is None:
        return False
    return answer.strip().lower().startswith("y")


def choose_iface(message):
    ifaces = sorted(item.name for item in iter_ifaces())
    if not ifaces:
        print("нет настроенных интерфейсов (сначала 'iface init' или создайте вручную)")
        return None

    for i, name in enumerate(ifaces, 1):
        print(f"  {i}) {name}")
    choice = prompt(f"{message} (номер или имя)")
    if not choice:
        return None
    if choice.isdigit() and 1 <= int(choice) <= len(ifaces):
        return ifaces[int(choice) - 1]
    return choice


def menu_iface_show():
    iface = choose_iface("Какой интерфейс показать")
    if iface:
        cmd_show(iface)


def menu_iface_up():
    iface = choose_iface("Какой интерфейс поднять")
    if iface:
        cmd_iface_up(iface)


def menu_iface_down():
    iface = choose_iface("Какой интерфейс опустить")
    if iface:
        cmd_iface_down(iface)


def print_not_applied_notice():
    print("⚠ конфиг записан, но НЕ применён - используй 4) up или 12) try, чтобы применить")


def menu_address_add():
    iface = choose_iface("На какой интерфейс добавить адрес")
    if not iface:
        return
    ip = prompt("IP-адрес с маской, например 192.168.1.10/24")
    if not ip:
        print("отменено")
        return
    replace = prompt_yes_no("Заменить существующие адреса вместо добавления?")
    cmd_address(iface, ip, replace)
    print_not_applied_notice()


def menu_route_add():
    iface = choose_iface("На какой интерфейс добавить маршрут")
    if not iface:
        return
    dst = prompt("Назначение, например default или 192.168.2.0/24", "default")
    gateway = prompt("Шлюз, например 192.168.1.1")
    if not gateway:
        print("отменено")
        return
    replace = prompt_yes_no("Заменить существующие маршруты вместо добавления?")
    cmd_route(iface, dst, gateway, replace)
    print_not_applied_notice()


def menu_bond_create():
    name = prompt("Имя bond-интерфейса, например bond0")
    if not name:
        print("отменено")
        return

    ifaces = sorted(item.name for item in iter_ifaces())
    if not ifaces:
        print("нет интерфейсов для объединения в bond")
        return
    for i, n in enumerate(ifaces, 1):
        print(f"  {i}) {n}")
    raw = prompt("Интерфейсы-слейвы через пробел (номера или имена)")
    if not raw:
        print("отменено")
        return

    slaves = []
    for token in raw.split():
        if token.isdigit() and 1 <= int(token) <= len(ifaces):
            slaves.append(ifaces[int(token) - 1])
        else:
            slaves.append(token)
    cmd_bond_create(name, slaves)
    print_not_applied_notice()


def menu_vlan_create():
    iface = choose_iface("Родительский интерфейс")
    if not iface:
        return
    vid_raw = prompt("VLAN ID (1-4095)")
    if not vid_raw or not vid_raw.isdigit():
        print("отменено")
        return
    cmd_vlan_create(iface, int(vid_raw))
    print_not_applied_notice()


def menu_try():
    timeout_raw = prompt("Таймаут авто-отката в секундах", "120")
    timeout = int(timeout_raw) if timeout_raw and timeout_raw.isdigit() else 120
    cmd_try(timeout)


def run_menu():
    actions = [
        ("Список интерфейсов", cmd_list),
        ("Показать интерфейс", menu_iface_show),
        ("Создать конфиги для интерфейсов без них (init)", cmd_iface_init),
        ("Поднять интерфейс (up)", menu_iface_up),
        ("Опустить интерфейс (down)", menu_iface_down),
        ("Добавить IP-адрес", menu_address_add),
        ("Добавить маршрут", menu_route_add),
        ("Создать bond", menu_bond_create),
        ("Создать vlan", menu_vlan_create),
        ("Текущее состояние сети (status)", cmd_status),
        ("Сравнить конфиг с реальным состоянием (diff)", cmd_diff),
        ("Применить с автооткатом (try)", menu_try),
        ("Подтвердить изменения (confirm)", cmd_confirm),
    ]

    while True:
        print("\n=== etcnetpy ===")
        for i, (label, _) in enumerate(actions, 1):
            print(f"  {i}) {label}")
        print("  0) Выход")

        try:
            choice = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if choice == "0":
            return
        if not choice.isdigit() or not (1 <= int(choice) <= len(actions)):
            print("нет такого пункта")
            continue

        _, action = actions[int(choice) - 1]
        try:
            action()
        except SystemExit:
            pass
        except KeyboardInterrupt:
            print("\nотменено")
        except Exception as e:
            print(f"ошибка: {e}")


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

    if result.returncode != 0:
        print(f"network restart FAILED (exit {result.returncode}) - safety watcher will still revert to the prior state in {timeout}s")
        sys.exit(result.returncode)

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

    # etcnet only reads ipv4address for BOOTPROTO=static (or a dhcp-static
    # fallback that never applies it while DHCP is working) - plain
    # BOOTPROTO=dhcp ignores the file entirely, so the address would never
    # actually get applied by ifup/try without this.
    if parse_options(item).get("BOOTPROTO") == "dhcp":
        set_bootproto_static(item)
        print(f"BOOTPROTO changed from dhcp to static on {item.name} (etcnet ignores ipv4address otherwise)")

    print(f"added {addr} to {item.name}")


def set_bootproto_static(item):
    path = item / "options"
    lines = path.read_text(encoding='utf-8').splitlines()
    lines = [
        "BOOTPROTO=static" if line.strip().startswith("BOOTPROTO=") else line
        for line in lines
    ]
    backup_file(path)
    path.write_text("\n".join(lines) + "\n", encoding='utf-8')


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

    # Duplicate-detection only compares dst+gateway (via parse_ipv4route/
    # route_core); the actual file content to keep comes from the raw lines
    # so extra fields on other routes (metric, table, ...) survive untouched.
    existing_lines_core = [route_core(route) for route in parse_ipv4route(item)]
    path = item / "ipv4route"
    existing_raw = read_raw_lines(path)

    if replace:
        if existing_lines_core == [line]:
            print(f"route already present: {line}")
            return
        lines = [line]
    else:
        if line in existing_lines_core:
            print(f"route already present: {line}")
            return
        lines = existing_raw + [line]

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

        # BOOTPROTO=dhcp interfaces never have an ipv4address/ipv4route file
        # (etcnet doesn't need one to run DHCP), so the check below would
        # miss a slave that's actively holding a live DHCP-assigned address.
        if "dhcp" in parse_options(slave_item).get("BOOTPROTO", ""):
            print(f"slave {slave} is BOOTPROTO=dhcp (still getting a live address) - set it to static first")
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
    # Compare full ip/mask, not just the bare ip - a config line can carry
    # trailing modifiers (e.g. "192.168.1.5/24 broadcast +"), so only the
    # first token is the actual address/mask.
    config_ips = {addr.split()[0] for addr in iface["ipv4address"]}
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


def read_raw_lines(path):
    if not path.is_file():
        return []
    return [line.strip() for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


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
            f"{a['local']}/{a['prefixlen']}" for a in iface.get('addr_info', [])
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
