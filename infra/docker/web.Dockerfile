FROM node:20-alpine

WORKDIR /app

COPY apps/web/package*.json /app/
RUN npm ci

COPY apps/web /app

CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000"]
