<p align="center">
  <img src="docs/assets/slay400-banner.svg" alt="slay400. RPG slay: turn your IBM i programs into REST, async and AI-ready APIs." width="100%">
</p>

# slay400-core

The project was called glow400 until 2026-11-16.

The generator behind slay400: it reads the PCML definition of an RPG program, merges a hand-written overlay, validates the result and emits API contracts (OpenAPI, runtime descriptor, mocks, MCP and more).

**Status: early development.** The call model, the PCML parser, the overlay loader with the API model, the codec and the static validation exist so far. Nothing here is released.

Licence: Apache-2.0. The slay400 name and logo are not licensed under Apache-2.0; see `docs/assets/README.md`.

## Modules

| Module | Content |
|---|---|
| `pcml-model` | Immutable call model of a PCML document, the API model, and the diagnostic types (JDK only) |
| `pcml-parser` | PCML XML to call model, with source positions and diagnostics |
| `pcml-overlay` | Reads `gateway.yaml` and the overlay files (format v0.6), merges them with the PCML into the API model; publishes the JSON Schemas for both file types |
| `pcml-codec` | Converts between API values and the values of a program call (scalars, structs, arrays); depends on `pcml-model` and the JDK only |
| `pcml-validation` | Static validation of an API model: encodability (`OVL003`) and the advisory warnings `OVL005` and `OVL006` |
| `pcml-contract` | The consumer-visible surface of an API (fields, types, limits, statuses), shared by the OpenAPI emitter and the comparison of releases |
| `pcml-diff` | Breaking-change detection between a released and a current repository (`API002` to `API006`) |
| `pcml-emit-descriptor` | Writes `descriptor.json` (schema version 1), the file the gateway reads, and reads it back into the API model; uses the streaming API of Jackson (`jackson-core`) to read |
| `pcml-report` | Writes diagnostics as text for people, JSON for scripts (`reportSchemaVersion` 1) or SARIF 2.1.0 for pull-request annotations |
| `pcml-mock` | Mock definitions (`apis/<FOLDER>/mock/<operation id>.yaml`): `MockProgram`, the evaluator that stands in for a program call between `encode` and `decode`; the `mock` emitter, which writes `mock/<api>.json` (`mockSchemaVersion` 1); and `MockReader`, which reads it back. No HTTP server and no sleeping: the delay is data |
| `pcml-scaffold` | Writes a first `api.yaml` from PCML and the `gateway.yaml` of `init`, and edits parameter entries of an `api.yaml` in place (`direction`, `type`, `name`) without rewriting the file, checking the result by loading it again (`SCF001` to `SCF003`). Text in, text out: no I/O |
| `pcml-cli` | The command-line tool: `init`, `annotate`, `validate`, `generate`, `bundle` and `diff`, in one runnable jar (`java -jar pcml-cli/target/pcml-cli-<version>.jar`) |
| `pcml-launcher` | The `slay400` distribution archive (`.tar.gz` and `.zip`): `bin/slay400` and `bin/slay400.cmd`, wrapping `pcml-cli`'s jar unchanged (see "Install") |
| `pcml-bundle` | Packs the descriptor, the OpenAPI documents and the PCML and overlay files into one deterministic, checksummed `.rpgapi` zip file, and reads it back as untrusted input (`BDL001` to `BDL006`) |
| `pcml-emit-openapi` | Writes one OpenAPI 3.1 document per API, `openapi/<api name>.yaml` |
| `pcml-http` | The HTTP binding, without a web framework: routes (`RouteTable`), reading a request into API values and writing the JSON response (`HttpBinding`), and RFC 9457 problem details (`ProblemDetails`), all agreeing with the OpenAPI document |
| `pcml-tasks` | The four pipeline tasks (`validate`, `generate`, `bundle`, `diff`) that the command-line tool and the Maven plugin both call |
| `pcml-maven-plugin` | The Maven plugin, goal prefix `pcml`: `pcml:validate`, `pcml:generate`, `pcml:bundle`, `pcml:diff` |
| `pcml-bom` | The bill of materials: one import that sets the version of every module above (see "Use the artifacts") |

Emitters are discovered with `java.util.ServiceLoader` (`Emitter` in `pcml-model`). More modules (a Java emitter) will follow, one increment at a time.

## Build

Requires Java 21. The Maven Wrapper is included, so no separate Maven install is needed:

```
./mvnw verify
```

## Use the artifacts

Every module is published to Maven Central (decision 91), and `pcml-bom` sets all their versions at once. Import it, then name
the modules you need without a version:

```xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>ai.generativearchitects.slay400</groupId>
      <artifactId>pcml-bom</artifactId>
      <version>VERSION</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>ai.generativearchitects.slay400</groupId>
    <artifactId>pcml-bundle</artifactId>
  </dependency>
</dependencies>
```

A `-SNAPSHOT` version is published to the Central snapshot repository after every build of `main`; to use one, add the
repository `https://central.sonatype.com/repository/maven-snapshots/` with snapshots enabled.

## Release

`main` always carries a snapshot version (`0.1.0-SNAPSHOT` now); a push to it runs the `snapshot` workflow, which publishes
that version to the Central snapshot repository. A release takes its version from a tag, `v<version>`, and nowhere else:
nothing is ever set by hand before or after one. To release:

1. **Name the version once**, by either path:
   - push a tag: `git tag v0.1.0 && git push origin v0.1.0` (on a commit already in `main`); or
   - use GitHub's "Draft a new release" page: fill in the tag (`v0.1.0`) and publish it, as a draft or not, before or
     after the workflow runs -- either order works.
2. Pushing the tag (or GitHub creating it for the release above) starts the `release` workflow, in the protected
   environment `release`. It checks that the tag can be released (`scripts/check_release_tag.py`: the tag's form, that
   its commit is in `main`, that its line matches the snapshot's, that every module agrees, that no other tag or
   version on Central already has this name), sets that version with `versions:set` in its own checkout only, builds,
   signs and uploads the release for validation, then attaches the distribution archives to the GitHub Release of the
   tag -- the one made in step 1, if there is one, or a new draft otherwise.
3. **If the check in step 2 fails**, nothing was built or uploaded: read the message, fix what it names (most often,
   `main` is still on the line of an earlier release -- see step 5) and push a new tag.
4. **Once the workflow succeeds**, open the deployment it made in the Central Portal, review it, and publish it there
   by hand; do the same for the GitHub Release (publish the draft, or leave it as a pre-release for a version with a
   pre-release part).
5. **Afterwards, if this was the last release of its line**, move `main` to the next snapshot with an ordinary pull
   request: `./mvnw versions:set -DnewVersion=<next>-SNAPSHOT -DprocessAllModules=true -DgenerateBackupPoms=false`.
   `main` must always carry a snapshot, or the next release's tag has no line to belong to.

Everything that can be checked without the accounts is checked in every build (`build` workflow), from an invented
version of the snapshot's own line (for example `0.1.0-ci.1`): the `release` profile stages all modules without signing
or uploading, `scripts/check_staged_artifacts.py` checks the files, the POM elements and the licence files, a small
project in `consumer-check/` is built against the staged files the way the gateway will, the archive's own
`slay400 --version` is checked, and `scripts/check-reproducible.sh` builds twice and compares the checksums. To build
from a tag by hand, the same way the `release` workflow does (one line, not committed):

```
./mvnw versions:set -DnewVersion=0.1.0 -DprocessAllModules=true -DgenerateBackupPoms=false && ./mvnw install -DskipTests
./mvnw -Prelease -Dgpg.skip=true -DskipUpload=true -DskipTests clean deploy
python3 scripts/check_staged_artifacts.py target/central-staging   # target/central-deferred instead, for a snapshot version
scripts/check-reproducible.sh 0.1.0   # with no argument, checks whatever version is already checked in
```

## Install

Download and run the install script for your platform, which fetches a release archive from GitHub Releases, verifies
its SHA-256 checksum, and unpacks it to `~/.slay400/<version>` (never with elevated rights, never editing a shell
profile):

```
curl -fsSL https://raw.githubusercontent.com/generativearchitects-ai/slay400-core/main/install.sh | sh
```

```powershell
iwr https://raw.githubusercontent.com/generativearchitects-ai/slay400-core/main/install.ps1 -OutFile install.ps1; .\install.ps1
```

With no version, both scripts install the latest stable release; if there is none yet, the newest release that is
not a draft (which may be a pre-release), printing one line saying so. An explicit version skips that lookup:

```
curl -fsSL https://raw.githubusercontent.com/generativearchitects-ai/slay400-core/main/install.sh | sh -s -- 0.1.0-alpha.1
```

```powershell
iwr https://raw.githubusercontent.com/generativearchitects-ai/slay400-core/main/install.ps1 -OutFile install.ps1; .\install.ps1 -Version 0.1.0-alpha.1
```

Both scripts also take an install folder (default: `~/.slay400`) and an `uninstall` option; run them with `--help`
for details, or read `install.sh` / `install.ps1` directly, they are plain shell and PowerShell. At the end, each
prints the line to add to `PATH` and how to check the install (`slay400 --version`).

Or download and unpack the archive by hand: the `.tar.gz` or `.zip` of a version's
[GitHub Release](https://github.com/generativearchitects-ai/slay400-core/releases), unpacked anywhere, with its `bin`
folder on your `PATH`. Needs Java 21 or later, found from `JAVA_HOME` or `PATH`.

## Use

See the documentation: [Quickstart](https://slay400.dev/docs/get-started/quickstart/) (`init`, `validate`, `generate`,
`bundle`, about ten minutes, no IBM i), [Your first API](https://slay400.dev/docs/tutorials/your-first-api/) (the
same road slowly, with `annotate` and a validation error provoked and fixed), the
[command-line reference](https://slay400.dev/docs/reference/cli/) and the
[diagnostics catalogue](https://slay400.dev/docs/reference/diagnostics/).

Without the launcher, the same commands run from the plain jar: `java -jar pcml-cli-<version>.jar init`.

The JSON Schemas for editor completion are `api.schema.json` and `gateway.schema.json`, next to `OverlayLoader` in the
`pcml-overlay` jar; see the [api.yaml reference](https://slay400.dev/docs/reference/api-yaml/) and the
[repository defaults reference](https://slay400.dev/docs/reference/repository-defaults/).

### The library

```java
ParseResult result = PcmlParser.parse(Path.of("MYPROGRAM.pcml"));
result.diagnostics().forEach(System.out::println);
result.document().ifPresent(doc -> doc.programs().forEach(p -> System.out.println(p.name())));
```

The parser never throws for malformed input; problems are returned as diagnostics with stable codes (`PCML001` to `PCML007`).

A customer repository holds an optional `gateway.yaml` and one folder per API under `apis/`, each with its PCML file(s) and one overlay file, `api.yaml`:

```java
RepositoryResult result = OverlayLoader.loadRepository(Path.of("my-repository"));
result.diagnostics().forEach(System.out::println);          // OVL001 ... OVL021, with file, line and column
result.model().ifPresent(model -> model.operations().forEach(op -> System.out.println(op.id())));
```

```java
List<Diagnostic> findings = Validator.validate(result.model().orElseThrow());      // OVL003, OVL005, OVL006

OperationCodec codec = OperationCodec.of(operation);                               // refuses an operation with OVL003 errors
EncodeResult call = codec.encode(Map.of("orderNumber", new ApiValue.Text("1042")), Map.of("P0ENV", "PRD"));
DecodeResult response = codec.decode(programOutput);                                // problems VAL001 ... VAL103, never thrown
```

The codec never alters data silently: nothing is truncated, rounded or clamped, and a value that does not fit is a problem
whose message never contains the value. A char field's `length` counts bytes of the host encoding, so the codec supports
single-byte CCSIDs only for now.

## Quality checks

`./mvnw verify` runs the unit tests. `./mvnw -Pmutation verify` also runs mutation testing (PIT) and fails below the threshold set in the parent `pom.xml`.

## Authors

See [AUTHORS](AUTHORS). The list is generated from the git history after each merge into `main`, so contributors are added automatically.
