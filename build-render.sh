#!/bin/bash
set -e

export COREPACK_ENABLE_STRICT=0
export COREPACK_ENABLE=0

npx --yes pnpm@10.26.1 install --frozen-lockfile
npx pnpm@10.26.1 --filter @workspace/dashboard run build
npx pnpm@10.26.1 --filter @workspace/api-server run build
