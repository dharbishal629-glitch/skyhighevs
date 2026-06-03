FROM node:20-alpine

WORKDIR /app

RUN npm install -g pnpm@10.26.1

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.base.json tsconfig.json ./
COPY lib/ ./lib/
COPY artifacts/api-server/ ./artifacts/api-server/
COPY artifacts/dashboard/ ./artifacts/dashboard/

RUN pnpm install --frozen-lockfile
RUN pnpm --filter @workspace/dashboard run build
RUN pnpm --filter @workspace/api-server run build

EXPOSE 10000

CMD ["node", "--enable-source-maps", "artifacts/api-server/dist/index.mjs"]
