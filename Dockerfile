# Build static Astro site
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

# Serve the static output
FROM node:20-alpine
WORKDIR /app
RUN npm install -g serve
COPY --from=builder /app/dist ./dist
ENV PORT=3000
CMD ["sh", "-c", "serve -s dist -l tcp://0.0.0.0:$PORT"]
