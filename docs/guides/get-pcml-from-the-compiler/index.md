---
title: Get PCML from the compiler
description: Have the RPG compiler write your program's PCML, with PGMINFO(*PCML).
section: guides
slug: get-pcml-from-the-compiler
order: 10
appliesTo: "0.1"
---

# Get PCML from the compiler

slay400 reads PCML; it does not write it. The usual source of a PCML file is the ILE RPG compiler itself: pass
it `PGMINFO(*PCML)` and it writes one next to your program, built from your procedure's parameter list.

## Compile with PGMINFO(*PCML)

<!-- snippet: examples/get-pcml-from-the-compiler/steps.sh#compile -->
```sh
# requires: ibmi
CRTBNDRPG PGM(DEMOLIB/ORDSTATUS) SRCSTMF('ordstatus.rpgle') PGMINFO(*PCML) INFOSTMF('ordstatus.pcml')
```

`PGM` names the program object to create, `SRCSTMF` its source, and `INFOSTMF` where to write the PCML. The
compiler derives one `<program>` with one `<data>` element per parameter, in order, with the type and length it
compiled; it does not know which way data should flow for your API (see
[/docs/concepts/two-contracts/](/docs/concepts/two-contracts/)), only the call contract.

This step needs a real IBM i and is not run by this site's automated checks; its exact output is not recorded
here yet (open item, tracked in the kickoff that added this page).

## Next

Copy the PCML file next to where your repository expects it, under `apis/<NAME>/<NAME>.pcml`, and run
`slay400 init`: see [/docs/tutorials/your-first-api/](/docs/tutorials/your-first-api/).
