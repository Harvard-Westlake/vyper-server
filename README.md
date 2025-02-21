# vyper-server

Use venv:

```bash
python -m venv vypenv
source vypenv/bin/activate


pip install -r requirements.txt

```

## Run server locally
python3 ./server.py


## Run on remove machine (https_server.py with https and nginx proxy)
python3 ./https_server.py


## Nginx server setup
Install nginx proxy on your server if not running locally:

```bash
sudo apt-get install nginx
```

Add the following "/etc/nginx/sites-enabled/default"

```bash
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name vyper.******.net; # managed by Certbot

    ssl_certificate /etc/letsencrypt/live/vyper.******.net/fullchain.pem; # managed by Certbot
    ssl_certificate_key /etc/letsencrypt/live/vyper.******.net/privkey.pem; # managed by Certbot
    include /etc/letsencrypt/options-ssl-nginx.conf; # managed by Certbot
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem; # managed by Certbot


    # Reverse proxy to your Python server
    location / {
            # Handle preflight requests directly in Nginx
        if ($request_method = 'OPTIONS') {
           add_header 'Access-Control-Allow-Origin' '*' always;
           add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS, PUT, DELETE' always;
           add_header 'Access-Control-Allow-Headers' 'Content-Type, X-Requested-With' always;
           add_header 'Access-Control-Max-Age' 86400 always;
           add_header 'Content-Length' 0;
           add_header 'Content-Type' 'text/plain; charset=UTF-8';
           return 204;
        }

        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```





