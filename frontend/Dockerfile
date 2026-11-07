# syntax=docker/dockerfile:1
# AI-INFLUENCED: Use the committed frontend lockfile for reproducible container installs with Codex.
# Frontend dev container (Vite dev server). For production, add a build stage
# that runs `npm run build` and serves the static output via nginx (N2H).
FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
