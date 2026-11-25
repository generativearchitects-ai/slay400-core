---
title: Your first API
description: init, annotate, validate, generate and bundle, explained step by step, with a mistake and its fix.
section: tutorials
slug: your-first-api
order: 10
appliesTo: "0.1"
time: 20 min
---

# Your first API

At the end of this page you will understand what each step of the quickstart actually did: what `init` writes
and why, how `annotate` resolves a parameter PCML cannot place by itself, how a validation error is read and
fixed, and what `generate` and `bundle` produce.

Before you start, you need:

- A POSIX shell (Linux or macOS).
- Java 21 or later. Check with `java -version`.
- slay400 installed; see [/docs/get-started/quickstart/](/docs/get-started/quickstart/) if you have not done that yet.

This time the repository starts with only one PCML file, `apis/ORDSTATUS/ORDSTATUS.pcml`, no overlay at all. One
field, `P0RETRY` (how many times the caller has already retried), is declared `inputoutput` in the PCML: the
program both reads and writes it, and PCML alone cannot say which way slay400 should expose it.

If you have not installed slay400 yet:

<!-- snippet: examples/your-first-api/steps.sh#install -->
```sh
curl -fsSL https://raw.githubusercontent.com/generativearchitects-ai/slay400-core/main/install.sh | sh
export PATH="$HOME/.slay400/bin:$PATH"
```

See [/docs/get-started/quickstart/](/docs/get-started/quickstart/) for what this does.

## Write a first overlay

<!-- snippet: examples/your-first-api/steps.sh#init -->
```sh
slay400 init
```

`init` writes `gateway.yaml` (the repository's defaults) and, for every PCML file that has none yet, a first
`api.yaml`: one operation, `POST /ordstatus`, one line per parameter, each exposed under a name derived from the
PCML field name. Look at what it wrote:

<!-- snippet: examples/your-first-api/steps.sh#show-the-overlay -->
```sh
cat apis/ORDSTATUS/api.yaml
```

It prints:

<!-- snippet: examples/your-first-api/expected/show-the-overlay.out -->
```text
pcml: ORDSTATUS.pcml
version: 0.1.0
title: ORDSTATUS
operations:
  - id: ordstatus
    program: ORDSTATUS
    route: /ordstatus
    method: POST
    parameters:
      P0ENV: { name: p0env }
      P0ORDN: { name: p0ordn }
      P0RETRY: { name: p0retry }  # inputoutput: run annotate, or add direction: request | response | both | internal
      P0STAT: { name: p0stat }
      P0DATE: { name: p0date }
      P0ERR: { name: p0err }
      P0ERRC: { name: p0errc }
      P0XERR: { name: p0xerr }
```

`P0RETRY`'s line carries a comment instead of a `direction`: PCML says the field is `inputoutput`, but not
whether the API should treat it as part of the request, the response, both, or neither (`internal`, not exposed
at all). `gateway.yaml` sets `defaults.inputoutput` to `fail` by default, so the repository will not validate
until every such field has an answer.

## Answer with annotate

`annotate` asks, for each undirected field, which way it goes, and writes the answer into `api.yaml` without
touching anything else in the file: comments, blank lines, key order and quoting all stay as they are. Run it and
answer `internal` for `P0RETRY` -- it is bookkeeping the program needs, not something the caller or the response
should carry:

<!-- snippet: examples/your-first-api/steps.sh#annotate -->
```sh
printf 'internal\n' | slay400 annotate
```

## Break something on purpose

A route that does not start with `/` is a common mistake. Make it one:

<!-- snippet: examples/your-first-api/steps.sh#break-the-route -->
```sh
sed 's#route: /ordstatus#route: ordstatus#' apis/ORDSTATUS/api.yaml > apis/ORDSTATUS/api.yaml.new
mv apis/ORDSTATUS/api.yaml.new apis/ORDSTATUS/api.yaml
```

## Read the error

<!-- snippet: examples/your-first-api/steps.sh#validate-fails -->
```sh
slay400 validate || true
```

It prints:

<!-- snippet: examples/your-first-api/expected/validate-fails.out -->
```text
apis/ORDSTATUS/api.yaml:7:12: error OVL012: 'route' must start with '/': 'ordstatus'
1 error, 0 warnings, 0 notes
```

The diagnostic names a file, a line and a column, a code (`OVL012`, see the
[diagnostics catalogue](/docs/reference/diagnostics/)) and what is wrong. `validate` exits with status 1 and
writes nothing else.

## Fix it

<!-- snippet: examples/your-first-api/steps.sh#fix-the-route -->
```sh
sed 's#route: ordstatus#route: /ordstatus#' apis/ORDSTATUS/api.yaml > apis/ORDSTATUS/api.yaml.new
mv apis/ORDSTATUS/api.yaml.new apis/ORDSTATUS/api.yaml
```

## Validate again

<!-- snippet: examples/your-first-api/steps.sh#validate-again -->
```sh
slay400 validate
```

It prints:

<!-- snippet: examples/your-first-api/expected/validate-again.out -->
```text
apis/ORDSTATUS/api.yaml:5:5: warning OVL006: Operation ordstatus has no error mapping: a business error reported by the program is returned as a success
0 errors, 1 warning, 0 notes
```

## Generate and bundle

<!-- snippet: examples/your-first-api/steps.sh#generate -->
```sh
slay400 generate --out build
```

<!-- snippet: examples/your-first-api/steps.sh#bundle -->
```sh
slay400 bundle --name shop --version 1.0.0 --out build/shop-1.0.0.rpgapi
```

Both print the same warning as above (`ORDSTATUS` still has no error mapping, so a business error the program
reports comes back as a success) and write their files, exactly as in the quickstart -- the only difference this
time is that you built the overlay yourself, one answer and one fix at a time.
