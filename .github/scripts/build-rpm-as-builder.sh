#!/bin/bash
# Runs as the unprivileged 'builder' user inside the alt:p10 container
# (ALT's rpmbuild refuses to run as root).
set -euo pipefail

cd /src
VERSION=$(awk '/^Version:/{print $2}' etcnetpy.spec)

mkdir -p ~/RPM/{BUILD,RPMS,SRPMS,SPECS,SOURCES}
tar -cf ~/RPM/SOURCES/etcnetpy-$VERSION.tar --transform "s,^,etcnetpy-$VERSION/," main.py README.md LICENSE
cp etcnetpy.spec ~/RPM/SPECS/

cd ~/RPM/SPECS
rpmbuild -ba etcnetpy.spec

mkdir -p /src/dist
find ~/RPM/RPMS ~/RPM/SRPMS -name '*.rpm' -exec cp {} /src/dist/ \;
