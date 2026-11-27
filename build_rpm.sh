#!/bin/bash
set -e

RPM_TOPDIR="$(pwd)/rpmbuild"
rm -rf "$RPM_TOPDIR"
mkdir -p "$RPM_TOPDIR"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

cp -r usr etc lib "$RPM_TOPDIR/SOURCES/"
cp py-autoclicker.spec "$RPM_TOPDIR/SPECS/"

rpmbuild --define "_topdir $RPM_TOPDIR" -bb "$RPM_TOPDIR/SPECS/py-autoclicker.spec"

mv "$RPM_TOPDIR"/RPMS/noarch/*.rpm ./
rm -rf "$RPM_TOPDIR"

echo "[+] RPM package built successfully!"
echo "Install with: sudo dnf install ./py-autoclicker-1.0.0-1.*.noarch.rpm"

