#!/bin/bash
set -e

export COREPACK_ENABLE_STRICT=0
export npm_config_prefix=$HOME/.npm-global
npm install -g pnpm@10.26.1
export PATH=$HOME/.npm-global/bin:$PATH

pnpm install --frozen-lockfile
pnpm --filter @workspace/dashboard run build
pnpm --filter @workspace/api-server run build
