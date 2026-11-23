# ── Stage 1: build ───────────────────────────────────────────
FROM node:24-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# NEXT_PUBLIC_* are inlined into the client bundle at build time, so they must
# be passed as build args — setting them at runtime has no effect on a
# production build.
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_DEMO_TENANT_ID
ARG NEXT_PUBLIC_DEMO_USER_ID
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_DEMO_TENANT_ID=$NEXT_PUBLIC_DEMO_TENANT_ID
ENV NEXT_PUBLIC_DEMO_USER_ID=$NEXT_PUBLIC_DEMO_USER_ID

RUN npm run build


# ── Stage 2: lean runtime ────────────────────────────────────
FROM node:24-alpine

WORKDIR /app
ENV NODE_ENV=production

COPY package*.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY --from=builder /app/.next ./.next
COPY --from=builder /app/next.config.mjs ./

USER node

EXPOSE 3000

CMD ["npx", "next", "start", "--port", "3000", "--hostname", "0.0.0.0"]
