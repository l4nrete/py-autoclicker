Name:           py-autoclicker
Version:        1.0.0
Release:        1%{?dist}
Summary:        Native Wayland & X11 Auto-Clicker for Linux
License:        MIT
BuildArch:      noarch

Requires:       python3 >= 3.12
Requires:       python3-evdev
Requires:       python3-pydantic
Requires:       python3-dasbus
Requires:       python3-gobject
Requires:       libadwaita
Requires:       systemd-udev
Requires:       kmod

%description
Low-level evdev/uinput auto-clicker built for GNOME / Mutter on Wayland and X11.
Features a native GTK4/Libadwaita UI, Gaussian temporal jitter, spatial
micro-drift, automatic user override, and zero-relogin uaccess permissions.

%install
mkdir -p %{buildroot}%{_bindir}
mkdir -p %{buildroot}%{_sysconfdir}/py-autoclicker
mkdir -p %{buildroot}%{_udevrulesdir}
mkdir -p %{buildroot}%{_modulesloaddir}
mkdir -p %{buildroot}%{_datadir}/applications
mkdir -p %{buildroot}%{_datadir}/py-autoclicker/autoclicker

install -m 0755 %{_sourcedir}/usr/bin/py-autoclicker %{buildroot}%{_bindir}/py-autoclicker
install -m 0644 %{_sourcedir}/etc/py-autoclicker/config.toml %{buildroot}%{_sysconfdir}/py-autoclicker/config.toml
install -m 0644 %{_sourcedir}/lib/udev/rules.d/60-py-autoclicker.rules %{buildroot}%{_udevrulesdir}/60-py-autoclicker.rules
install -m 0644 %{_sourcedir}/usr/lib/modules-load.d/py-autoclicker.conf %{buildroot}%{_modulesloaddir}/py-autoclicker.conf
install -m 0644 %{_sourcedir}/usr/share/applications/py-autoclicker.desktop %{buildroot}%{_datadir}/applications/py-autoclicker.desktop
install -m 0644 %{_sourcedir}/usr/share/py-autoclicker/autoclicker/*.py %{buildroot}%{_datadir}/py-autoclicker/autoclicker/

%post
modprobe uinput >/dev/null 2>&1 || :
udevadm control --reload-rules >/dev/null 2>&1 || :
udevadm trigger --subsystem-match=misc --name-match=uinput >/dev/null 2>&1 || :
udevadm trigger --subsystem-match=input >/dev/null 2>&1 || :

%postun
if [ $1 -eq 0 ]; then
    udevadm control --reload-rules >/dev/null 2>&1 || :
    udevadm trigger --subsystem-match=misc --name-match=uinput >/dev/null 2>&1 || :
    udevadm trigger --subsystem-match=input >/dev/null 2>&1 || :
fi

%files
%{_bindir}/py-autoclicker
%config(noreplace) %{_sysconfdir}/py-autoclicker/config.toml
%{_udevrulesdir}/60-py-autoclicker.rules
%{_modulesloaddir}/py-autoclicker.conf
%{_datadir}/applications/py-autoclicker.desktop
%{_datadir}/py-autoclicker/

