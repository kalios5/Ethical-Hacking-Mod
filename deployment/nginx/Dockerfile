FROM nginx:latest

# Install openssl to generate the self-signed cert at build time
RUN apt-get update && \
    apt-get install -y --no-install-recommends openssl && \
    rm -rf /var/lib/apt/lists/*

# Generate self-signed cert at build time
# Replace 192.168.10.42 with your EC2 IP or domain
RUN mkdir -p /etc/nginx/certs && \
    openssl req -x509 \
        -newkey rsa:4096 \
        -keyout /etc/nginx/certs/key.pem \
        -out    /etc/nginx/certs/cert.pem \
        -days   365 \
        -nodes  \
        -subj   "/C=SG/ST=Singapore/L=Singapore/O=Lab/CN=192.168.10.42" \
        -addext "subjectAltName=IP:192.168.10.42,IP:127.0.0.1,DNS:localhost"

# Copy nginx config
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80 443