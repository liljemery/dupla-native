#!/bin/bash
# ponytail: compile LibreDWG on Debian bookworm; python:*-slim (trixie) GCC fails with -Werror=alloc-size.
set -euo pipefail

LIBREDWG_VERSION="${LIBREDWG_VERSION:-0.13.4.8317}"
JOBS="${LIBREDWG_BUILD_JOBS:-2}"

apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  xz-utils \
  build-essential \
  autoconf \
  automake \
  libtool \
  pkg-config

workdir="$(mktemp -d)"
cd "$workdir"

archive="libredwg-${LIBREDWG_VERSION}.tar.xz"
github_url="https://github.com/LibreDWG/libredwg/releases/download/${LIBREDWG_VERSION}/${archive}"
gnu_url="https://ftp.gnu.org/gnu/libredwg/${archive}"

if curl -fsSL "$github_url" -o "$archive"; then
  :
elif curl -fsSL "$gnu_url" -o "$archive"; then
  :
else
  echo "Failed to download LibreDWG ${LIBREDWG_VERSION}" >&2
  exit 1
fi

tar xf "$archive"
srcdir="libredwg-${LIBREDWG_VERSION}"
if [[ ! -d "$srcdir" ]]; then
  srcdir="$(find . -maxdepth 1 -type d -name 'libredwg-*' | head -1)"
fi
cd "$srcdir"
./configure --disable-bindings --enable-release
make -j"${JOBS}"
make install
ldconfig

cd /
rm -rf "$workdir"
apt-get purge -y curl xz-utils autoconf automake libtool
apt-get autoremove -y --purge
rm -rf /var/lib/apt/lists/*

command -v dwg2dxf >/dev/null
dwgread -V 2>/dev/null || dwg2dxf --version 2>/dev/null || true
