# Maintainer: l4nrete
pkgname=py-autoclicker
pkgver=1.0.0
pkgrel=1
pkgdesc="Native Wayland & X11 Auto-Clicker for Linux built with evdev/uinput and GTK4/Libadwaita"
arch=('any')
url="https://github.com/l4nrete/py-autoclicker"
license=('MIT')
depends=(
    'python'
    'python-evdev'
    'python-pydantic'
    'python-dasbus'
    'python-gobject'
    'libadwaita'
)
backup=('etc/py-autoclicker/config.toml')

package() {
    cd "$startdir"

    install -Dm755 usr/bin/py-autoclicker "$pkgdir/usr/bin/py-autoclicker"
    install -Dm644 etc/py-autoclicker/config.toml "$pkgdir/etc/py-autoclicker/config.toml"
    install -Dm644 lib/udev/rules.d/60-py-autoclicker.rules "$pkgdir/usr/lib/udev/rules.d/60-py-autoclicker.rules"
    install -Dm644 usr/lib/modules-load.d/py-autoclicker.conf "$pkgdir/usr/lib/modules-load.d/py-autoclicker.conf"
    install -Dm644 usr/share/applications/py-autoclicker.desktop "$pkgdir/usr/share/applications/py-autoclicker.desktop"

    install -d "$pkgdir/usr/share/py-autoclicker/autoclicker"
    install -m644 usr/share/py-autoclicker/autoclicker/*.py "$pkgdir/usr/share/py-autoclicker/autoclicker/"
}

