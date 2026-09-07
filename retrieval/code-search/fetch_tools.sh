#!/usr/bin/env bash
# Fetch the pinned static binaries used by run.py into bin/.
# ripgrep 14.1.1 (musl) and Universal Ctags 6.2.0 nightly (linux-x86_64).
set -euo pipefail
cd "$(dirname "$0")/bin"

RG_URL="https://github.com/BurntSushi/ripgrep/releases/download/14.1.1/ripgrep-14.1.1-x86_64-unknown-linux-musl.tar.gz"
CTAGS_URL="https://github.com/universal-ctags/ctags-nightly-build/releases/download/2026.08.18%2Bb0615e08c94166267669bd2292647470fff5daac/uctags-2026.08.18-linux-x86_64.release.tar.gz"

if [ ! -x rg ]; then
    curl -sL -o rg.tgz "$RG_URL"
    tar xzf rg.tgz --strip-components=1 ripgrep-14.1.1-x86_64-unknown-linux-musl/rg
    rm rg.tgz
fi

if [ ! -x ctags ] || [ ! -x readtags ]; then
    curl -sL -o uctags.tgz "$CTAGS_URL"
    tar xzf uctags.tgz --strip-components=2 \
        uctags-2026.08.18-linux-x86_64.release/bin/ctags \
        uctags-2026.08.18-linux-x86_64.release/bin/readtags
    rm uctags.tgz
fi

./rg --version | head -1
./ctags --version | head -1
