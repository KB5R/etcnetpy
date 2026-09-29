#!/bin/bash
# Entry point run as root inside the alt:p10 container.
# Installs rpm-build tooling, creates an unprivileged builder user
# (ALT's rpmbuild refuses to run as root), and delegates the actual
# build to build-rpm-as-builder.sh.
set -euo pipefail

apt-get update
apt-get install -y rpm-build rpm-build-python3 tar

useradd -m builder
# builder only needs write access to dist/ for its output - /src itself
# stays as-is (world-readable is enough to read the sources), since this
# runs against a real bind-mounted host checkout and chown -R /src would
# reassign ownership of the whole repo on the host to the container's uid.
mkdir -p /src/dist
chown builder:builder /src/dist

runuser -u builder -- bash /src/.github/scripts/build-rpm-as-builder.sh
