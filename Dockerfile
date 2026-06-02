FROM node:20-alpine

WORKDIR /app

RUN npm install -g pnpm@10.26.1

COPY . .

RUN pnpm install --frozen-lockfile
RUN pnpm --filter @workspace/dashboard run build
RUN pnpm --filter @workspace/api-server run build

EXPOSE 10000

CMD ["node", "--enable-source-maps", "artifacts/api-server/dist/index.mjs"]
