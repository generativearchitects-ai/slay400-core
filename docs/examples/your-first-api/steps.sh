#!/bin/sh
# Your first API: the same road as the quickstart, slowly, explained at each step.
set -eu

# region: install
curl -fsSL https://raw.githubusercontent.com/generativearchitects-ai/slay400-core/main/install.sh | sh
export PATH="$HOME/.slay400/bin:$PATH"
# endregion

# region: init
slay400 init
# endregion

# region: show-the-overlay
cat apis/ORDSTATUS/api.yaml
# endregion

# region: annotate
printf 'internal\n' | slay400 annotate
# endregion

# region: break-the-route
sed 's#route: /ordstatus#route: ordstatus#' apis/ORDSTATUS/api.yaml > apis/ORDSTATUS/api.yaml.new
mv apis/ORDSTATUS/api.yaml.new apis/ORDSTATUS/api.yaml
# endregion

# region: validate-fails
slay400 validate || true
# endregion

# region: fix-the-route
sed 's#route: ordstatus#route: /ordstatus#' apis/ORDSTATUS/api.yaml > apis/ORDSTATUS/api.yaml.new
mv apis/ORDSTATUS/api.yaml.new apis/ORDSTATUS/api.yaml
# endregion

# region: validate-again
slay400 validate
# endregion

# region: generate
slay400 generate --out build
# endregion

# region: bundle
slay400 bundle --name shop --version 1.0.0 --out build/shop-1.0.0.rpgapi
# endregion
