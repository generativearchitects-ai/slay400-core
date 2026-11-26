The files in this folder, and the code blocks of the documentation taken from them, are licensed under the Apache License 2.0 (decision 148); see `LICENSE` in this folder.

`runner.json` (schema: `runner.schema.json`) lists the tools `scripts/docs/run_examples.py` sets up before a clean
run, so the script itself names no repository, archive, URL or environment variable (kickoff 18, decision 150).
Each tool: its `name`; its `archive`, either a `path` in this repository with the version marked as `{version}`
(read from this repository's own `pom.xml`), or an `env` variable naming an archive built elsewhere; its
`releaseArchiveName` (also with `{version}` marked), the name under which the archive is laid out in the local
stand-in for the releases, exactly as the install script expects, and (for an `env` archive) the pattern its own
version is read back from; `installCommand`, the exact line a page shows, and `localScript`, the file run in its
place instead of reaching the real network; and `env.releasesUrl`/`env.releasesApi`, the two environment variables
through which that local script is pointed at the stand-in. `own: true` marks this repository's own tool, whose
version is normalised to the literal `<version>`; any other tool's version is normalised to `<name version>`, so
that two versions in one output stay apart.
