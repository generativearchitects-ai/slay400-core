#!/usr/bin/env bash
# Builds the artifacts that would be published twice, each time from a clean tree, and compares the checksum of every file.
# Two builds of the same commit must give the same bytes (project.build.outputTimestamp in pom.xml, kickoff 12).
#
# Run from anywhere: scripts/check-reproducible.sh [VERSION]. Needs nothing but Java and the Maven Wrapper; it signs nothing
# and uploads nothing. It installs the modules into your local Maven repository first (the test jars that some modules
# share are only built by an ordinary build, and the release profile leaves them out of the deployment).
#
# VERSION, if given, is set with versions:set before each of the two builds (kickoff 20 point 5: a build from a tag by hand
# gives the same version) and put back with versions:revert afterwards, even on failure; with no VERSION, the two builds use
# whatever version is already checked in (a snapshot, ordinarily). Exit code 0: same bytes. 1: a difference, listed. The
# staging folder of the second build stays in target/.
set -euo pipefail

cd "$(dirname "$0")/.."

VERSION="${1:-}"
work="$(mktemp -d)"
if [ -n "$VERSION" ]; then
  # -DgenerateBackupPoms defaults to true: every pom.xml gets a .versionsBackup file, which "versions:revert" puts
  # back in place of the version just set, unconditionally, so the working tree is exactly as it was on exit --
  # on failure too, since this runs in a trap.
  trap './mvnw -q versions:revert || true; rm -rf "$work"' EXIT
  echo "Setting the version to $VERSION for this check (put back when this script exits)..."
  ./mvnw -B -q versions:set -DnewVersion="$VERSION" -DprocessAllModules=true
else
  trap 'rm -rf "$work"' EXIT
fi

# The same arguments as the CI job that checks the files (scripts/check_staged_artifacts.py): no tests, no signature, no upload.
build() {
  ./mvnw -B -q -Prelease -Dgpg.skip=true -DskipUpload=true -DskipTests -Dinvoker.skip=true clean deploy
  # A snapshot is staged in central-deferred, a release in central-staging; the plugin leaves the other one behind
  # too, empty, so the choice has to be the first one that actually holds a file, not the first that exists.
  local staged
  for staged in target/central-deferred target/central-staging; do
    if [ -d "$staged" ] && [ -n "$(find "$staged" -type f ! -name 'maven-metadata*' -print -quit)" ]; then
      (cd "$staged" && find . -type f ! -name 'maven-metadata*' -print0 | sort -z | xargs -0 sha256sum) > "$1"
      return
    fi
  done
  echo "No staging folder in target/ has a file: the build did not stage anything." >&2
  exit 1
}

echo "Installing the modules (their test jars are needed, and are not part of what is compared)..."
./mvnw -B -q install -DskipTests -Dinvoker.skip=true

echo "First build..."
build "$work/first.sha256"
echo "Second build..."
build "$work/second.sha256"

files="$(wc -l < "$work/first.sha256" | tr -d ' ')"
if [ "$files" -eq 0 ]; then
  echo "No file was staged." >&2
  exit 1
fi

if diff -u "$work/first.sha256" "$work/second.sha256"; then
  echo "Reproducible: $files files, the same checksums in both builds."
else
  echo "NOT reproducible: the two builds differ (see above)." >&2
  exit 1
fi
