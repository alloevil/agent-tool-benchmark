#!/usr/bin/env bash
# Rebuild corpus/ from scratch: psf/requests pinned at tag v2.32.3.
# The whole corpus/ directory is gitignored; this script is the source of truth.
set -euo pipefail
cd "$(dirname "$0")"

EXPECTED_SHA=0e322af87745eff34caffe4df68456ebc20d9068

rm -rf corpus
git clone --depth 1 --branch v2.32.3 https://github.com/psf/requests corpus
SHA=$(git -C corpus rev-parse HEAD)
if [ "$SHA" != "$EXPECTED_SHA" ]; then
    echo "ERROR: unexpected commit $SHA (expected $EXPECTED_SHA)" >&2
    exit 1
fi
echo "corpus ready at $SHA (requests v2.32.3)"
echo
echo "run.py builds the zg index automatically if corpus/.zvec-grep is missing;"
echo "to build it manually:"
echo "  cd corpus && PATH=\$HOME/.nvm/versions/node/v22.23.2/bin:\$PATH \\"
echo "    zg index --embedding local/potion-retrieval-32m -g 'src/requests/*.py'"
