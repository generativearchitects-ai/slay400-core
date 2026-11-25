---
title: The two contracts
description: Why slay400 never edits your PCML, and what the overlay file is for.
section: concepts
slug: two-contracts
order: 10
appliesTo: "0.1"
---

# The two contracts

Every API slay400 builds rests on two separate files, each answering a different question, and neither one able
to answer the other's.

## The call contract: PCML

PCML describes how to call an RPG program: its parameters, in order, with their types, lengths and (when the
compiler wrote it with `PGMINFO(*PCML)`, see
[/docs/guides/get-pcml-from-the-compiler/](/docs/guides/get-pcml-from-the-compiler/)) whether a field is input,
output, or both. It says nothing about HTTP, JSON, or who is allowed to call the program and why.

slay400 never edits a PCML file, and never writes one. It is the one artifact in a repository that comes from
somewhere else -- the compiler, or a program's own author -- and is treated as a fact to read, not a file to
maintain. If it is wrong, the fix is to recompile or hand-edit it outside slay400, not to patch it from inside a
repository.

## The API contract: the overlay

`api.yaml`, one per PCML file, says how that call becomes an HTTP operation: its route and method, which
parameter goes in the request, the response, or neither, how a business error reported by the program becomes
an HTTP status, and more. This is the file `init` scaffolds, `annotate` fills in, and `validate` checks -- the
one a repository's author is meant to edit by hand.

The split exists because the two questions have different owners and different lifetimes. The call contract
changes when the program's signature changes, on whatever schedule RPG changes happen. The API contract changes
when what callers need changes -- a new route, a renamed field, a different error mapping -- on whatever
schedule an API's consumers need. Mixing them into one file would force every change to one to risk the other.

## Where this shows up

An `inputoutput` PCML field with no `direction` set in the overlay is the two contracts disagreeing: PCML says
the field flows both ways at the call level, but the overlay has not yet said which way it flows at the API
level. See [/docs/tutorials/your-first-api/](/docs/tutorials/your-first-api/) for this happening and being fixed.
