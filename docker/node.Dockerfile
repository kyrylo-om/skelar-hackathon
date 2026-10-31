FROM node:24-bookworm-slim

ARG APP_DIR
WORKDIR /app
COPY ${APP_DIR}/package.json ${APP_DIR}/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY --chown=node:node ${APP_DIR}/ ./
RUN chown node:node /app
USER node
