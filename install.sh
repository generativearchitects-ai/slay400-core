#!/bin/sh
# Installs slay400 (kickoff 17): downloads a release archive and its SHA-256 file over HTTPS, verifies it, unpacks it
# to <folder>/<version>, and points <folder>/bin/slay400 at it. Never runs with elevated rights, never edits a shell
# profile: it prints the one PATH line to add, and how to check. Idempotent; a failed download or a wrong checksum
# leaves the previous installation untouched. "uninstall" removes only what this script created.
#
# Usage: install.sh [VERSION] [FOLDER]
#        install.sh uninstall [FOLDER]
#
# VERSION defaults to the latest stable release, or the newest pre-release if there is no stable one yet. FOLDER
# defaults to ~/.slay400. Needs curl or wget, sha256sum or shasum, and tar. Reads SLAY400_RELEASES_URL and
# SLAY400_RELEASES_API only to let tests point at a local stand-in instead of the real GitHub endpoints; leave both
# unset for a real install.
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

fetch_status_body() {
  # fetch_status_body URL -- prints "<status>\n<body>" to stdout for any HTTP response (2xx/4xx/5xx); returns
  # nonzero only when the request could not be made at all (DNS, connection refused, timeout). A file:// URL (used
  # only by tests, and by docs:examples' local stand-in for a release) has no HTTP status: reading it is reported
  # as "200", a missing file as a failure -- the same two outcomes curl/wget already give every other fetch here.
  url="$1"
  case "$url" in
    file://*)
      path="${url#file://}"
      [ -r "$path" ] || return 1
      printf '200\n%s' "$(cat "$path")"
      return 0
      ;;
  esac
  if command -v curl >/dev/null 2>&1; then
    raw="$(curl -sSL -w '\n%{http_code}' "$url")" || return 1
    status="$(printf '%s\n' "$raw" | tail -n 1)"
    body="$(printf '%s\n' "$raw" | sed '$d')"
  elif command -v wget >/dev/null 2>&1; then
    headers="$(mktemp)"
    body="$(wget -q -O - --server-response "$url" 2>"$headers")" || true
    status="$(awk '/HTTP\// { code = $2 } END { print code }' "$headers")"
    rm -f "$headers"
    [ -n "$status" ] || return 1
  else
    fail "neither curl nor wget was found; cannot download $url"
  fi
  printf '%s\n%s' "$status" "$body"
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

tag_from_json() {
  # tag_from_json BODY CONTEXT -- the version named by one JSON object's "tag_name" field, without its leading "v".
  tag="$(printf '%s\n' "$1" | sed -n 's/.*"tag_name": *"\(v[^"]*\)".*/\1/p' | head -n 1)"
  [ -n "$tag" ] || fail "could not read a tag_name from $2"
  printf '%s\n' "$tag" | sed 's/^v//'
}

first_non_draft_tag() {
  # first_non_draft_tag BODY -- the first "tag_name" in a JSON array of releases whose own "draft" is false, in
  # document order (GitHub's list endpoint returns releases sorted by creation time, descending -- newest first),
  # without its leading "v"; nothing if there is none. Not a real JSON parser, like the rest of this script's
  # reading of "tag_name": pairs each tag_name with the "draft" value that follows it and precedes the next
  # tag_name, which is how GitHub always serializes a release's own fields (never interleaved with another's).
  printf '%s' "$1" | tr '\n' ' ' | grep -oE '"tag_name" *: *"v[^"]*"|"draft" *: *(true|false)' |
    { pending=""
      while IFS= read -r line; do
        case "$line" in
          '"tag_name"'*)
            pending="$(printf '%s\n' "$line" | sed -n 's/.*"\(v[^"]*\)".*/\1/p')"
            ;;
          '"draft"'*)
            if [ -n "$pending" ]; then
              case "$line" in
                *false*)
                  printf '%s\n' "$pending" | sed 's/^v//'
                  break
                  ;;
                *)
                  pending=""
                  ;;
              esac
            fi
            ;;
        esac
      done
      true
    }
}

latest_non_draft_release() {
  # No stable release exists ($RELEASES_API answered 404): fall back to the newest release that is not a draft,
  # which may be a pre-release -- said so in one line, since a reader who asked for "the latest" should know which
  # kind they got. GitHub's own "latest" endpoint already excludes both drafts and pre-releases, so reaching here
  # at all means there is no stable release yet.
  list_api="${RELEASES_API%/latest}"
  response="$(fetch_status_body "$list_api")" || fail "could not reach $RELEASES_API to find the latest version"
  status="$(printf '%s\n' "$response" | head -n 1)"
  [ "$status" = "200" ] || fail "could not reach $RELEASES_API to find the latest version"
  body="$(printf '%s\n' "$response" | sed '1d')"
  tag="$(first_non_draft_tag "$body")"
  [ -n "$tag" ] || fail "no release exists yet at $list_api"
  echo "slay400: no stable release exists yet; installing the pre-release $tag" >&2
  printf '%s\n' "$tag"
}

latest_version() {
  response="$(fetch_status_body "$RELEASES_API")" || fail "could not reach $RELEASES_API to find the latest version"
  status="$(printf '%s\n' "$response" | head -n 1)"
  body="$(printf '%s\n' "$response" | sed '1d')"
  case "$status" in
    200) tag_from_json "$body" "$RELEASES_API" ;;
    404) latest_non_draft_release ;;
    *) fail "could not reach $RELEASES_API to find the latest version" ;;
  esac
}

# A sub-folder is one of our installs, beyond doubt, only when its name is the content of its own VERSION file and
# it holds bin/slay400 and a jar under lib/ -- not merely "has a file named VERSION", which any number of unrelated
# projects also do.
is_our_install() {
  entry="$1"
  name="$(basename "$entry")"
  [ -f "$entry/VERSION" ] || return 1
  [ "$(cat "$entry/VERSION")" = "$name" ] || return 1
  [ -f "$entry/bin/slay400" ] || return 1
  for jar in "$entry"/lib/*.jar; do
    [ -f "$jar" ] && return 0
  done
  return 1
}

do_uninstall() {
  folder="$1"
  if [ -d "$folder" ]; then
    for entry in "$folder"/*; do
      [ -d "$entry" ] || continue
      is_our_install "$entry" && rm -rf "$entry"
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
  # Covers a version given on the command line and one read from the releases API (both end up here, in $version),
  # before it is used to build a download address or a path: a stray "/" or ".." must not reach either.
  case "$version" in
    *[!A-Za-z0-9.+-]* | "") fail "'$version' does not look like a version (letters, digits, '.', '-', '+' only)" ;;
  esac

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
  echo "VERSION defaults to the latest stable release, or the newest pre-release if there is no stable one yet."
  echo "FOLDER defaults to $DEFAULT_FOLDER."
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
