# etcnetpy
etcnet - Settings network for Alt Linux

## Status

CLI on argparse with three commands:
- `list` - interfaces from config (`testdata/ifaces/`)
- `show <iface>` - parsed config (options, ipv4address, ipv4route) for one interface
- `status` - live network state via `ip -j addr/route show`

## Next steps

- switch `NETWORK` from `testdata/ifaces/` to the real `/etc/net/ifaces/`
- `diff`/`compare` command: config vs live state
- parse `ipv4route` lines into fields (dst/via) instead of raw strings
