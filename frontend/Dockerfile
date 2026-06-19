FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

EXPOSE 3000

CMD ["npx", "next", "dev", "--port", "3000", "--hostname", "0.0.0.0"]
