#!/bin/sh
# Installs slay400 (kickoff 17): downloads a release archive and its SHA-256 file over HTTPS, verifies it, unpacks it
# to <folder>/<version>, and points <folder>/bin/slay400 at it. Never runs with elevated rights, never edits a shell
# profile: it prints the one PATH line to add, and how to check. Idempotent; a failed download or a wrong checksum
# leaves the previous installation untouched. "uninstall" removes only what this script created.
#
# Usage: install.sh [VERSION] [FOLDER]
#        install.sh uninstall [FOLDER]
#
# VERSION defaults to the latest GitHub release. FOLDER defaults to ~/.slay400. Needs curl or wget, sha256sum or
# shasum, and tar. Reads SLAY400_RELEASES_URL and SLAY400_RELEASES_API only to let tests point at a local stand-in
# instead of the real GitHub endpoints; leave both unset for a real install.
set -eu

REPO="generativearchitects-ai/slay400-core"
RELEASES_URL="${SLAY400_RELEASES_URL:-https://github.com/$REPO/releases}"
RELEASES_API="${SLAY400_RELEASES_API:-https://api.github.com/repos/$REPO/releases/latest}"
DEFAULT_FOLDER="$HOME/.slay400"

fail() {
  echo "install.sh: $1" >&2
  exit 1
}

fetch() {
  # fetch URL DEST
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL -o "$2" "$1"
  elif command -v wget >/dev/null 2>&1; then
    wget -q -O "$2" "$1"
  else
    fail "neither curl nor wget was found; cannot download $1"
  fi
}

fetch_text() {
  # fetch_text URL -- prints the body to stdout
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$1"
  elif command -v wget >/dev/null 2>&1; then
    wget -q -O - "$1"
  else
    fail "neither curl nor wget was found; cannot download $1"
  fi
}

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    fail "neither sha256sum nor shasum was found; cannot verify the download"
  fi
}

latest_version() {
  body="$(fetch_text "$RELEASES_API")" || fail "could not reach $RELEASES_API to find the latest version"
  tag="$(printf '%s\n' "$body" | sed -n 's/.*"tag_name": *"\(v[^"]*\)".*/\1/p' | head -n 1)"
  [ -n "$tag" ] || fail "could not read a tag_name from $RELEASES_API"
  printf '%s\n' "$tag" | sed 's/^v//'
}

do_uninstall() {
  folder="$1"
  if [ -d "$folder" ]; then
    for entry in "$folder"/*; do
      [ -d "$entry" ] && [ -f "$entry/VERSION" ] && rm -rf "$entry"
    done
    if [ -L "$folder/bin/slay400" ]; then
      rm -f "$folder/bin/slay400"
    fi
    rmdir "$folder/bin" 2>/dev/null || true
    rmdir "$folder" 2>/dev/null || true
  fi
  echo "slay400: removed the installation in $folder (anything else there was left untouched)."
}

do_install() {
  version="$1"
  folder="$2"
  [ -n "$version" ] || version="$(latest_version)"

  work="$(mktemp -d)"
  trap 'rm -rf "$work"' EXIT

  archive="slay400-$version.tar.gz"
  fetch "$RELEASES_URL/download/v$version/$archive" "$work/$archive" || fail "could not download $archive"
  fetch "$RELEASES_URL/download/v$version/$archive.sha256" "$work/$archive.sha256" || fail "could not download $archive.sha256"

  expected="$(awk '{print $1}' "$work/$archive.sha256")"
  actual="$(sha256_of "$work/$archive")"
  [ "$expected" = "$actual" ] || fail "checksum mismatch for $archive: expected $expected, got $actual"

  mkdir -p "$work/extracted"
  tar -xzf "$work/$archive" -C "$work/extracted"
  unpacked="$work/extracted/slay400-$version"
  [ -d "$unpacked" ] || fail "the archive did not contain slay400-$version/"

  mkdir -p "$folder"
  target="$folder/$version"
  rm -rf "$target"
  mv "$unpacked" "$target"

  mkdir -p "$folder/bin"
  ln -sf "$target/bin/slay400" "$folder/bin/slay400"

  echo "slay400 $version installed in $target"
  echo "Add this to your shell profile, or run it in your current shell:"
  echo "  export PATH=\"$folder/bin:\$PATH\""
  echo "Then check with: slay400 --version"
}

usage() {
  echo "Usage: install.sh [VERSION] [FOLDER]"
  echo "       install.sh uninstall [FOLDER]"
  echo
  echo "VERSION defaults to the latest GitHub release. FOLDER defaults to $DEFAULT_FOLDER."
}

folder="$DEFAULT_FOLDER"
case "${1:-}" in
  -h | --help)
    usage
    ;;
  uninstall)
    [ -n "${2:-}" ] && folder="$2"
    do_uninstall "$folder"
    ;;
  *)
    version="${1:-}"
    [ -n "${2:-}" ] && folder="$2"
    do_install "$version" "$folder"
    ;;
esac
