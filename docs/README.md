# Documentation

Pages for `slay400.dev/docs/`, built by the `slay400-docs` site from this folder and the same folder in the
gateway repository. See `specs/documentation.md` in `slay400-docs` for the full rules; this file is the short,
practical version.

## Layout

```
docs/
  get-started/<slug>/index.md
  tutorials/<slug>/index.md
  guides/<slug>/index.md
  reference/<slug>/index.md      # cli, api-yaml, repository-defaults, diagnostics are generated -- see below
  concepts/<slug>/index.md
  examples/<example>/            # steps.sh, input/, expected/, README.md -- what every page's code blocks come from
  images/
```

## Add a page

1. Pick a section and a slug, add `docs/<section>/<slug>/index.md` with front matter: `title` (<= 60 chars, no
   "slay400"), `description`, `section`, `slug` (unique within the section), `order`, `appliesTo`, and `time`
   (get-started/tutorials only). One `#` heading equal to the title. get-started and tutorials need a
   "Before you start" section.
2. Every command, its output, and any file content shown on the page must come from an example (see below) via
   a snippet marker -- nothing is typed by hand. Link to another page as `/docs/<section>/<slug>/`; link to a
   repository file as a full `https://github.com/...` address; never a relative link.
3. Run `python3 scripts/docs/check_front_matter.py` and `python3 scripts/docs/check_snippets.py`.

## Add or change an example

An example is a folder under `docs/examples/`: `steps.sh` (the commands, in `# region: <name>` / `# endregion`
blocks), optionally `input/` (files the script starts with), `expected/<region>.out` (each region's captured
output), and a `README.md` saying where it came from.

1. Write or edit `steps.sh`.
2. Reference a region from a page with `<!-- snippet: examples/<example>/steps.sh#<region> -->` immediately
   before a fenced block; `check_snippets.py --write` fills the block in from the script.
3. Run `python3 scripts/docs/run_examples.py --write` to capture real output into `expected/`. This builds and
   runs the tool from your current commit in a clean temporary folder and a fresh `$HOME` -- read the output,
   don't just accept it.
4. A step that needs a real IBM i goes in a region marked `# requires: ibmi`; it is never run automatically,
   and its output, if recorded, is added by hand with a note saying where it came from.

## Generated reference pages

`docs/reference/cli`, `diagnostics`, `api-yaml` and `repository-defaults` are written by
`scripts/docs/generate_*.py` from the built CLI and the overlay/gateway JSON Schemas; do not hand-edit them. A
hand-written note that should survive regeneration goes in the matching `docs/reference/_notes/<slug>/` folder.
Regenerate after a relevant code change: `python3 scripts/docs/generate_cli_reference.py` (needs `pcml-cli`
built), `generate_diagnostics_catalogue.py`, `generate_schema_reference.py`. Each has a `--check` mode that
fails if the committed page is stale.

## Running every check

```sh
python3 scripts/docs/check_front_matter.py
python3 scripts/docs/check_snippets.py
python3 scripts/docs/run_examples.py
python3 scripts/docs/generate_cli_reference.py --check
python3 scripts/docs/generate_diagnostics_catalogue.py --check
python3 scripts/docs/generate_schema_reference.py --check
```

All of these also run in CI on every pull request.
