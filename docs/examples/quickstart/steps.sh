#!/bin/sh
# The quickstart, from the shop's PCML to a validated repository, an OpenAPI document and a bundle.
set -eu

# region: install
curl -fsSL https://raw.githubusercontent.com/generativearchitects-ai/slay400-core/main/install.sh | sh
export PATH="$HOME/.slay400/bin:$PATH"
# endregion

# region: check
slay400 --version
# endregion

# region: init
slay400 init
# endregion

# region: validate
slay400 validate
# endregion

# region: generate
slay400 generate --out build
# endregion

# region: bundle
slay400 bundle --name shop --version 1.0.0 --out build/shop-1.0.0.rpgapi
# endregion
