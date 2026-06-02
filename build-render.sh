#!/bin/bash
set -e

npm install -g pnpm@10.26.1 --prefix=$HOME
export PATH=$HOME/bin:$PATH

pnpm install --frozen-lockfile
pnpm --filter @workspace/dashboard run build
pnpm --filter @workspace/api-server run build
