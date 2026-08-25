from pathlib import Path

NETWORK = Path('testdata/ifaces/')


def main():
    print('Etcnetpy - settings network for altlinux and other')
    for item in NETWORK.iterdir():
        iface = read_iface(item)
        print(item.name, iface)


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


if __name__ == "__main__":
    main()
