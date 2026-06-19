FROM node:20-alpine AS build

# Vite bakes environment variables into the JS bundle at BUILD time, not
# runtime, so this must be a build arg rather than a regular ENV var.
# Default matches the standard docker-compose.yml setup (frontend on :3000,
# backend on :8000, same host). Override with:
#   docker build --build-arg VITE_API_URL=http://your-host:8000 .
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL

WORKDIR /app
COPY package.json .
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q -O- http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
