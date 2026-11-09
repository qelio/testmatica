# Боевой образ веба (Next.js standalone). Локальная разработка — сервис web в compose.yaml (npm run dev).
#   docker build -t testmatica-web ./web

FROM node:24-alpine AS deps
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24-alpine AS build
WORKDIR /web
ENV NEXT_TELEMETRY_DISABLED=1
# Номер выкладки (решение №65): попадает в клиентский код при сборке.
ARG APP_VERSION=""
ENV NEXT_PUBLIC_APP_VERSION=$APP_VERSION
COPY --from=deps /web/node_modules ./node_modules
COPY . .
RUN npm run build \
    && cp -r public .next/standalone/ \
    && cp -r .next/static .next/standalone/.next/

FROM node:24-alpine
WORKDIR /web
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
COPY --from=build --chown=node:node /web/.next/standalone ./
USER node
EXPOSE 3000
CMD ["node", "server.js"]
