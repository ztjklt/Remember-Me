FROM public.ecr.aws/docker/library/node:24-alpine
WORKDIR /app
ENV HOST=0.0.0.0 PORT=8000 NODE_ENV=production WEB_BACKEND_CA=/app/certs/backend.pem
COPY server.mjs package.json ./
COPY dist ./dist
COPY certs ./certs
USER node
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD node -e "const u=new URL(process.env.WEB_PUBLIC_ORIGIN);require('http').get({hostname:'127.0.0.1',port:process.env.PORT,path:'/healthz',headers:{Host:u.host}},r=>process.exit(r.statusCode===200?0:1)).on('error',()=>process.exit(1))"
CMD ["node", "server.mjs"]
