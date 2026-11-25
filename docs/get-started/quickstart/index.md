---
title: Quickstart
description: From a PCML file to a checked bundle and an OpenAPI document, without an IBM i.
section: get-started
slug: quickstart
order: 10
appliesTo: "0.1"
time: 10 min
---

# Quickstart

At the end of this page you will have validated two invented APIs, generated their OpenAPI documents, and packed
everything into one bundle file -- without an IBM i, and without choosing anything along the way.

Before you start, you need:

- A POSIX shell (Linux or macOS) or PowerShell (Windows).
- Java 21 or later on your machine. Check with `java -version`.

## Install slay400

<!-- snippet: examples/quickstart/steps.sh#install -->
```sh
curl -fsSL https://raw.githubusercontent.com/generativearchitects-ai/slay400-core/main/install.sh | sh
export PATH="$HOME/.slay400/bin:$PATH"
```

This downloads the latest release, checks it, and unpacks it to `~/.slay400`. The second line puts it on your
`PATH` for this session; add it to your shell profile to keep it there. Check it worked:

<!-- snippet: examples/quickstart/steps.sh#check -->
```sh
slay400 --version
```

It prints the version you installed, for example:

<!-- snippet: examples/quickstart/expected/check.out -->
```text
slay400 <version>
```

(On Windows, download and run `install.ps1` instead; see the Install section of the README for both.)

## Look at the repository

A repository of APIs is a folder with a PCML file and an overlay (`api.yaml`) per API, under `apis/`. This one
already has both, for two invented programs of a small shop: `ORDSTATUS` (order status) and `ITEMQTY` (item
quantity). Create it, with the files below (or copy them from
[docs/examples/quickstart/input](https://github.com/generativearchitects-ai/slay400-core/tree/main/docs/examples/quickstart/input)).

## Write gateway.yaml

<!-- snippet: examples/quickstart/steps.sh#init -->
```sh
slay400 init
```

It prints:

<!-- snippet: examples/quickstart/expected/init.out -->
```text
0 errors, 0 warnings, 0 notes
```

`init` never overwrites or deletes a file: since both `api.yaml` files already exist, it only writes
`gateway.yaml`, the repository's defaults. It does not yet cross-check an API against the others, which is why
the warning below only shows up once you `validate`.

## Validate

<!-- snippet: examples/quickstart/steps.sh#validate -->
```sh
slay400 validate
```

It prints:

<!-- snippet: examples/quickstart/expected/validate.out -->
```text
apis/ITEMQTY/api.yaml:1:1: warning OVL006: Operation itemqty has no error mapping: a business error reported by the program is returned as a success
0 errors, 1 warning, 0 notes
```

## Generate the OpenAPI document

<!-- snippet: examples/quickstart/steps.sh#generate -->
```sh
slay400 generate --out build
```

It prints:

<!-- snippet: examples/quickstart/expected/generate.out -->
```text
apis/ITEMQTY/api.yaml:1:1: warning OVL006: Operation itemqty has no error mapping: a business error reported by the program is returned as a success
0 errors, 1 warning, 0 notes
```

This writes `build/openapi/ordstatus.yaml` and `build/openapi/itemqty.yaml` (one OpenAPI 3.1 document per API), and
the runtime descriptor and mock definitions beside them.

## Bundle it

<!-- snippet: examples/quickstart/steps.sh#bundle -->
```sh
slay400 bundle --name shop --version 1.0.0 --out build/shop-1.0.0.rpgapi
```

It prints:

<!-- snippet: examples/quickstart/expected/bundle.out -->
```text
apis/ITEMQTY/api.yaml:1:1: warning OVL006: Operation itemqty has no error mapping: a business error reported by the program is returned as a success
0 errors, 1 warning, 0 notes
```

`build/shop-1.0.0.rpgapi` now holds everything a gateway needs to serve these two APIs: the descriptor, the OpenAPI
documents, the PCML and overlay files, and the mock definitions, all checksummed.

## Next

Serve that bundle and call it, with no IBM i and no program, using a mock: see
[/docs/get-started/serve-with-a-mock/](/docs/get-started/serve-with-a-mock/) in the gateway's documentation.
