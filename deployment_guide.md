# AWS Lightsail Deployment Guide: Whatomate WhatsApp Signup Flow

This guide outlines how to deploy your WhatsApp Embedded Signup Flask application alongside your existing **Whatomate** setup on an **AWS Lightsail** instance with **Nginx** acting as a reverse proxy.

---

## Deployment Architecture Overview

Your existing Whatomate application is running on AWS Lightsail (often dockerized), and its PostgreSQL database runs inside a Docker container.

To deploy the Flask WhatsApp Signup app on the same server, we configure it to run on a local port (e.g., `5001`) via **Gunicorn** managed by **Systemd**. We then configure your existing **Nginx** server to act as a reverse proxy, forwarding traffic for the `/auth` (onboarding) and `/admin` routes to Gunicorn.

```
                  +----------------------------------------------+
                  |                 AWS Lightsail                |
                  |                                              |
                  |                +-----------+                 |
                  |  Port 80/443   |   Nginx   |                 |
  HTTPS Traffic --+--------------->|  Reverse  |                 |
                  |                |   Proxy   |                 |
                  |                +-----+-----+                 |
                  |                      |                       |
                  |          +-----------+-----------+           |
                  |          |                       |           |
                  |    /auth & /admin               Other        |
                  |          |                       |           |
                  |          v                       v           |
                  |    +-----------+           +-----------+     |
                  |    | Flask App |           | Whatomate |     |
                  |    | Gunicorn  |           | Main App  |     |
                  |    | Port 5001 |           +-----------+     |
                  |    +-----+-----+                             |
                  |          |                                   |
                  |          v (psycopg2 direct connection)      |
                  |    +-----------------------------+           |
                  |    | PostgreSQL Docker Container |           |
                  |    +-----------------------------+           |
                  +----------------------------------------------+
```

---

## Step 1: Copy Application Code to AWS Lightsail

Log in to your Lightsail instance via SSH and copy your `insert_flask_app` folder to a deployment directory, such as `/var/www/whatsapp-signup`:

```bash
sudo mkdir -p /var/www/whatsapp-signup
sudo chown -R $USER:$USER /var/www/whatsapp-signup
# Copy all workspace files into /var/www/whatsapp-signup
```

---

## Step 2: Establish Python Virtual Environment & Dependencies

Inside your Lightsail deployment folder, initialize a clean Python environment and install the required production tools:

```bash
cd /var/www/whatsapp-signup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn
```

---

## Step 3: Configure Database & Meta Env Variables

Create your production `.env` file inside `/var/www/whatsapp-signup/.env`:

```bash
nano .env
```

Add your database parameters:
```env
SECRET_KEY=generate_a_secure_long_secret_key_here
FLASK_APP=app.py
FLASK_ENV=production

# DB Host: If PostgreSQL is in Docker, map it to localhost:5432
DB_HOST=127.0.0.1
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your_actual_whatomate_database_password
DB_NAME=whatomate_production

# Target organization setup
TARGET_ORGANIZATION_NAME=Shiva Developers

# Meta credentials
META_APP_ID=your_actual_fb_app_id
META_APP_SECRET=your_actual_fb_app_secret
META_CONFIG_ID=your_actual_embedded_signup_config_id
REDIRECT_URI=https://your-domain.com/auth/oauth-callback
```

### Docker Network Note:
If your PostgreSQL container's port `5432` is **not** exposed to the host system, you can connect the Flask app directly inside the Docker network.
1. Get your database container name: `docker ps` (e.g., `whatomate-db`).
2. Run your Flask app inside a docker container connected to the same network, or set `DB_HOST` to the database container's Docker bridge IP (found via `docker inspect <db-container-name> | grep IPAddress`).

---

## Step 4: Configure Gunicorn & Systemd Service

We use a Systemd service to ensure that your Flask app runs in the background and auto-restarts if the system reboots.

Create the service file:
```bash
sudo nano /etc/systemd/system/whatsapp-signup.service
```

Paste the following configurations (adjust user group and paths if necessary):
```ini
[Unit]
Description=Gunicorn instance to serve WhatsApp Signup Flow
After=network.target

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=/var/www/whatsapp-signup
Environment="PATH=/var/www/whatsapp-signup/venv/bin"
ExecStart=/var/www/whatsapp-signup/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:5001 "app:app"
Restart=always

[Install]
WantedBy=multi-user.target
```

Start and enable the service:
```bash
sudo systemctl daemon-reload
sudo systemctl start whatsapp-signup
sudo systemctl enable whatsapp-signup
```

Verify that the service is running successfully:
```bash
sudo systemctl status whatsapp-signup
```

---

## Step 5: Configure Nginx to Route Traffic

We now tell Nginx to forward requests for `/auth` and `/admin` to Gunicorn running on port `5001`, while leaving the rest of Whatomate untouched.

Open your active Nginx site configuration file (typically in `/etc/nginx/sites-enabled/default` or `/etc/nginx/conf.d/whatomate.conf`):

```bash
sudo nano /etc/nginx/sites-enabled/default
```

Inside the active `server` block (listening on port `443` for SSL), add the following `location` blocks:

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com; # Your Whatomate domain

    # SSL configs here... (Certbot details)

    # 1. WhatsApp Onboarding Signup Flow
    location /auth {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 2. WhatsApp Onboarding Admin review portal
    location /admin {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 3. Existing Whatomate routing configuration...
    location / {
        # Your existing proxy configurations for Whatomate main dashboard
        # proxy_pass http://localhost:your_whatomate_port;
        # ...
    }
}
```

Test your Nginx configurations for syntax errors:
```bash
sudo nginx -t
```

If it reports success, restart Nginx to apply the changes:
```bash
sudo systemctl restart nginx
```

---

## Step 6: Verify Deployment

1.  **Check connection**: Run your introspection diagnostic tool on Lightsail to verify database connectivity from the production folder:
    ```bash
    source venv/bin/activate
    python diagnose_db.py
    ```
2.  **Verify Web access**: Navigate to `https://your-domain.com/auth/embedded-signup` in your browser.
3.  **Confirm Admin Dashboard**: Access `https://your-domain.com/admin/login` and log in with your credentials to verify the administrative view.
