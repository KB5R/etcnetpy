from pathlib import Path

NETWORK = Path('testdata/ifaces/')

def main():
    print('Etcnetpy - settings network for altlinux and other')
    init()

def init():
    print('++INIT NETWORKS SETTINGS++')
    for item in NETWORK.iterdir():
        print(f"Directory: {item}")
        files = ("options", "ipv4address", "ipv4route")
        for i in files:
            pathf = item / i
            if pathf.is_file():
                print(f"file: {pathf}")
            else:
                print("no file")

if __name__ == "__main__":
    main()