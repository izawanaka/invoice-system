# Frontend Next.js invoice web -- build DI DALAM image, JANGAN di host:
# host VM hanya punya Node 18, Next.js 16 butuh >= 20.9.
FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# NEXT_PUBLIC_* di-inline saat BUILD -- ganti URL API = rebuild image ini.
ARG NEXT_PUBLIC_API_BASE
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=builder /app ./
EXPOSE 3000
CMD ["npx", "next", "start", "-p", "3000"]
