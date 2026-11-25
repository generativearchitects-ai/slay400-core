#!/bin/sh
# Compiling one of the shop's invented programs with the PGMINFO option, to get its PCML. Needs a real IBM i;
# not run by docs:examples (spec section 5: "requires: ibmi"). Its recorded output is not available yet (open
# item, kickoff 16 pull request).
set -eu

# region: compile
# requires: ibmi
CRTBNDRPG PGM(DEMOLIB/ORDSTATUS) SRCSTMF('ordstatus.rpgle') PGMINFO(*PCML) INFOSTMF('ordstatus.pcml')
# endregion
