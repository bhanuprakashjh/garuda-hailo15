#!/bin/sh
# Execute on the 15L as root. Bench-only Ubuntu userspace; never replaces Yocto.
# Input assets are staged together in /opt/garuda-ros-assets. No FC connection.
set -eu
test "$(uname -m)" = aarch64
ROOTFS=/opt/garuda-ros-jazzy
ASSETS=/opt/garuda-ros-assets
test "$(sha256sum "$ASSETS/ubuntu-base-arm64.tar.gz" | cut -d ' ' -f 1)" = 04207713ece899c3740823d33690441ad3a7f0ded1101aca744e2b0f37ac7ff2
test "$(sha256sum "$ASSETS/egm96-5.tar.bz2" | cut -d ' ' -f 1)" = c46224f8f723dc915d97179f4e1580a98d6c742fe2b82cd8fef0ecaaad13e614
if [ -d "$ROOTFS" ] && [ ! -f "$ROOTFS/.garuda-bench-rootfs" ]; then
  echo 'Refusing an unowned rootfs directory' >&2; exit 1
fi
mkdir -p "$ROOTFS"
touch "$ROOTFS/.garuda-bench-rootfs"
if [ ! -x "$ROOTFS/usr/bin/apt-get" ]; then
  tar -xzf "$ASSETS/ubuntu-base-arm64.tar.gz" -C "$ROOTFS"
fi
# Standalone device nodes, not a bind of the board's cameras/NPU/serial devices.
test -c "$ROOTFS/dev/null" || mknod -m 666 "$ROOTFS/dev/null" c 1 3
test -c "$ROOTFS/dev/urandom" || mknod -m 666 "$ROOTFS/dev/urandom" c 1 9
test -c "$ROOTFS/dev/random" || mknod -m 666 "$ROOTFS/dev/random" c 1 8
install -m 644 "$ASSETS/ros.key" "$ROOTFS/usr/share/keyrings/ros-archive-keyring.gpg"
install -m 644 "$ASSETS/ros2.list" "$ROOTFS/etc/apt/sources.list.d/ros2.list"
install -m 755 "$ASSETS/policy-rc.d" "$ROOTFS/usr/sbin/policy-rc.d"
install -m 644 "$ASSETS/hosts" "$ROOTFS/etc/hosts"
mkdir -p "$ROOTFS/usr/share/GeographicLib"
tar -xjf "$ASSETS/egm96-5.tar.bz2" -C "$ROOTFS/usr/share/GeographicLib"
# The proxy uses an SSH reverse forward: no board default route or DNS changes.
chroot "$ROOTFS" /usr/bin/env DEBIAN_FRONTEND=noninteractive apt-get \
  -o Acquire::http::Proxy=http://127.0.0.1:18080 -o Acquire::Retries=2 update
chroot "$ROOTFS" /usr/bin/env DEBIAN_FRONTEND=noninteractive apt-get \
  -o Acquire::http::Proxy=http://127.0.0.1:18080 -o Acquire::Retries=2 \
  -o Dpkg::Use-Pty=0 install -y --no-install-recommends \
  ros-jazzy-ros-base ros-jazzy-rmw-cyclonedds-cpp ros-jazzy-mavros
chroot "$ROOTFS" dpkg-query -W
