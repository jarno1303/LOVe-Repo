# Deployment-ohjeet - LOVe Enhanced

Tämä dokumentti kuvaa kuinka LOVe Enhanced viedään tuotantoon.

## 📋 Sisällysluettelo

- [Esivalmistelut](#esivalmistelut)
- [PostgreSQL-asennus](#postgresql-asennus)
- [Sovelluksen asennus](#sovelluksen-asennus)
- [Gunicorn ja Nginx](#gunicorn-ja-nginx)
- [SSL-sertifikaatti](#ssl-sertifikaatti)
- [Automaattinen käynnistys](#automaattinen-käynnistys)
- [Monitoring ja Logging](#monitoring-ja-logging)
- [Backup](#backup)
- [Päivitykset](#päivitykset)

---

## Esivalmistelut

### Palvelinvaatimukset

**Minimivaatimukset:**
- 2 CPU-ydintä
- 2 GB RAM
- 20 GB levytilaa
- Ubuntu 22.04 LTS tai uudempi

**Suositellut:**
- 4 CPU-ydintä
- 4 GB RAM
- 50 GB levytilaa

### Hosting-vaihtoehdot

1. **DigitalOcean** (suositeltu)
   - Droplet: $24/kk (4GB RAM)
   - Helppo skaalata
   - Hyvä dokumentaatio

2. **AWS EC2**
   - t3.medium: ~$30/kk
   - Laaja ekosysteemi
   - Monimutkainen hinnoittelu

3. **Render**
   - $25/kk (Standard)
   - Helppo käyttää
   - Automaattinen deployment

4. **Azure**
   - B2s: ~$30/kk
   - Hyvä yritysasiakkaille

### Domain ja DNS

1. **Hanki domain:** loveenhanced.fi
   - Nimipalvelut: Namecheap, Cloudflare

2. **DNS-asetukset:**
   ```
   A     @     123.45.67.89    (palvelimen IP)
   A     www   123.45.67.89
   ```

---

## PostgreSQL-asennus

### 1. Asenna PostgreSQL

```bash
# Päivitä paketit
sudo apt update
sudo apt upgrade -y

# Asenna PostgreSQL
sudo apt install postgresql postgresql-contrib -y

# Tarkista status
sudo systemctl status postgresql
```

### 2. Luo tietokanta ja käyttäjä

```bash
# Kirjaudu PostgreSQL:ään
sudo -u postgres psql

# PostgreSQL-konsolissa:
CREATE DATABASE loveenhanced;
CREATE USER loveuser WITH PASSWORD 'vahva-salasana-tähän';
GRANT ALL PRIVILEGES ON DATABASE loveenhanced TO loveuser;

# Poistu
\q
```

### 3. Salli etäyhteydet (jos tarpeen)

```bash
# Muokkaa PostgreSQL-asetuksia
sudo nano /etc/postgresql/14/main/postgresql.conf

# Etsi ja muuta:
listen_addresses = 'localhost'  # Tai '*' etäyhteyksiä varten

# Muokkaa pg_hba.conf
sudo nano /etc/postgresql/14/main/pg_hba.conf

# Lisää:
host    loveenhanced    loveuser    127.0.0.1/32    md5

# Käynnistä uudelleen
sudo systemctl restart postgresql
```

---

## Sovelluksen asennus

### 1. Luo sovelluskäyttäjä

```bash
# Luo käyttäjä sovellukselle
sudo adduser loveapp --disabled-password

# Vaihda käyttäjäksi
sudo su - loveapp
```

### 2. Kloonaa repository

```bash
# Asenna git
sudo apt install git -y

# Kloonaa
cd /home/loveapp
git clone https://github.com/yourusername/love-enhanced.git
cd love-enhanced
```

### 3. Python-ympäristö

```bash
# Asenna Python ja pip
sudo apt install python3.11 python3.11-venv python3-pip -y

# Luo virtuaaliympäristö
python3.11 -m venv venv
source venv/bin/activate

# Asenna riippuvuudet
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn psycopg2-binary
```

### 4. Ympäristömuuttujat

```bash
# Luo .env-tiedosto
nano .env
```

**.env-tiedosto:**
```bash
# Flask
FLASK_ENV=production
SECRET_KEY=<generoitu-vahva-salasana>
DEBUG=False

# Database
DATABASE_URL=postgresql://loveuser:vahva-salasana-tähän@localhost:5432/loveenhanced

# Security
SESSION_COOKIE_SECURE=True
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SAMESITE=Lax

# HTTPS
PREFERRED_URL_SCHEME=https
```

**Generoi vahva SECRET_KEY:**
```python
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 5. Alusta tietokanta

```bash
# Aktivoi virtuaaliympäristö
source venv/bin/activate

# Aja alustusscripti
python init_db.py

# Tarkista että taulut luotiin
psql -U loveuser -d loveenhanced -h localhost

# PostgreSQL:ssä:
\dt  # Näytä taulut
\q   # Poistu
```

### 6. Testaa sovellus

```bash
# Käynnistä development-palvelin
python app.py

# Toisessa terminaalissa testaa:
curl http://localhost:5000
```

---

## Gunicorn ja Nginx

### 1. Gunicorn-asennus

```bash
# Jo asennettu riippuvuuksien kanssa
pip install gunicorn
```

**Luo Gunicorn-konfiguraatio:**
```bash
nano /home/loveapp/love-enhanced/gunicorn_config.py
```

```python
# gunicorn_config.py
bind = "127.0.0.1:8000"
workers = 4
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Logging
accesslog = "/home/loveapp/love-enhanced/logs/access.log"
errorlog = "/home/loveapp/love-enhanced/logs/error.log"
loglevel = "info"

# Daemon
daemon = False
pidfile = "/home/loveapp/love-enhanced/gunicorn.pid"
```

### 2. Nginx-asennus

```bash
# Asenna Nginx
sudo apt install nginx -y

# Luo sivustokonfiguraatio
sudo nano /etc/nginx/sites-available/loveenhanced
```

**Nginx-konfiguraatio:**
```nginx
upstream love_app {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name loveenhanced.fi www.loveenhanced.fi;
    
    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name loveenhanced.fi www.loveenhanced.fi;
    
    # SSL Certificates (asenna Let's Encrypt ensin)
    ssl_certificate /etc/letsencrypt/live/loveenhanced.fi/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/loveenhanced.fi/privkey.pem;
    
    # SSL Configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    
    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Max upload size
    client_max_body_size 10M;
    
    # Logs
    access_log /var/log/nginx/loveenhanced_access.log;
    error_log /var/log/nginx/loveenhanced_error.log;
    
    # Static files
    location /static {
        alias /home/loveapp/love-enhanced/static;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
    
    # Proxy to Gunicorn
    location / {
        proxy_pass http://love_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

**Aktivoi sivusto:**
```bash
# Luo symbolinen linkki
sudo ln -s /etc/nginx/sites-available/loveenhanced /etc/nginx/sites-enabled/

# Poista oletus-sivusto
sudo rm /etc/nginx/sites-enabled/default

# Testaa konfiguraatio
sudo nginx -t

# Käynnistä uudelleen
sudo systemctl restart nginx
```

---

## SSL-sertifikaatti

### Let's Encrypt (Certbot)

```bash
# Asenna Certbot
sudo apt install certbot python3-certbot-nginx -y

# Hanki sertifikaatti
sudo certbot --nginx -d loveenhanced.fi -d www.loveenhanced.fi

# Seuraa ohjeita:
# 1. Anna sähköpostiosoite
# 2. Hyväksy käyttöehdot
# 3. Valitse HTTPS-uudelleenohjaus (suositeltu)

# Testaa automaattinen uusiminen
sudo certbot renew --dry-run
```

**Sertifikaatti uusiutuu automaattisesti 90 päivän välein.**

---

## Automaattinen käynnistys

### Systemd-palvelu

**Luo systemd service -tiedosto:**
```bash
sudo nano /etc/systemd/system/loveenhanced.service
```

```ini
[Unit]
Description=LOVe Enhanced Gunicorn Application
After=network.target postgresql.service

[Service]
Type=notify
User=loveapp
Group=loveapp
WorkingDirectory=/home/loveapp/love-enhanced
Environment="PATH=/home/loveapp/love-enhanced/venv/bin"
EnvironmentFile=/home/loveapp/love-enhanced/.env
ExecStart=/home/loveapp/love-enhanced/venv/bin/gunicorn \
    --config gunicorn_config.py \
    app:app
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

**Aktivoi ja käynnistä:**
```bash
# Lataa uudelleen systemd
sudo systemctl daemon-reload

# Käynnistä palvelu
sudo systemctl start loveenhanced

# Tarkista status
sudo systemctl status loveenhanced

# Ota käyttöön automaattinen käynnistys
sudo systemctl enable loveenhanced

# Käynnistä uudelleen
sudo systemctl restart loveenhanced
```

---

## Monitoring ja Logging

### 1. Lokien seuranta

```bash
# Sovelluksen lokit
tail -f /home/loveapp/love-enhanced/logs/error.log
tail -f /home/loveapp/love-enhanced/logs/access.log

# Nginx-lokit
sudo tail -f /var/log/nginx/loveenhanced_error.log
sudo tail -f /var/log/nginx/loveenhanced_access.log

# Systemd-lokit
sudo journalctl -u loveenhanced -f
```

### 2. Sentry (Virheenseuranta)

**Asenna Sentry SDK:**
```bash
pip install sentry-sdk[flask]
```

**Lisää app.py:hyn:**
```python
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

sentry_sdk.init(
    dsn="https://your-sentry-dsn@sentry.io/project",
    integrations=[FlaskIntegration()],
    traces_sample_rate=1.0,
    environment="production"
)
```

### 3. Uptime monitoring

**UptimeRobot** (ilmainen):
- https://uptimerobot.com
- Tarkistaa sivuston saatavuuden 5 min välein
- Lähettää hälytykset sähköpostilla

**Setup:**
1. Luo tili UptimeRobotissa
2. Lisää monitori: loveenhanced.fi
3. Aseta hälytykset sähköpostiin

---

## Backup

### 1. Tietokanta-backup

**Luo backup-script:**
```bash
sudo nano /home/loveapp/backup_db.sh
```

```bash
#!/bin/bash

# Määritä muuttujat
DB_NAME="loveenhanced"
DB_USER="loveuser"
BACKUP_DIR="/home/loveapp/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_${DATE}.sql.gz"

# Luo backup-hakemisto jos ei ole
mkdir -p $BACKUP_DIR

# Tee backup
pg_dump -U $DB_USER -h localhost $DB_NAME | gzip > $BACKUP_FILE

# Poista yli 7 päivää vanhat backupit
find $BACKUP_DIR -name "*.sql.gz" -mtime +7 -delete

echo "Backup created: $BACKUP_FILE"
```

**Tee suoritettavaksi:**
```bash
chmod +x /home/loveapp/backup_db.sh
```

**Ajoita cron:lla (joka yö klo 02:00):**
```bash
crontab -e

# Lisää rivi:
0 2 * * * /home/loveapp/backup_db.sh >> /home/loveapp/logs/backup.log 2>&1
```

### 2. Palauta backup

```bash
# Pura ja palauta
gunzip -c /home/loveapp/backups/loveenhanced_20251024_020000.sql.gz | \
psql -U loveuser -h localhost loveenhanced
```

### 3. Kokonainen backup (tiedostot)

```bash
# Tee täydellinen backup
tar -czf loveenhanced_full_backup_$(date +%Y%m%d).tar.gz \
  /home/loveapp/love-enhanced \
  --exclude='*.pyc' \
  --exclude='__pycache__' \
  --exclude='venv'

# Siirrä turvalliseen paikkaan (esim. S3)
```

---

## Päivitykset

### 1. Koodin päivitys

```bash
# Vaihda käyttäjäksi
sudo su - loveapp

# Mene sovellushakemistoon
cd /home/loveapp/love-enhanced

# Vedä uusin koodi
git pull origin main

# Aktivoi virtuaaliympäristö
source venv/bin/activate

# Päivitä riippuvuudet
pip install -r requirements.txt --upgrade

# Aja mahdolliset migraatiot
python migrate.py  # jos olemassa

# Käynnistä sovellus uudelleen
sudo systemctl restart loveenhanced
```

### 2. Tietokannan migraatiot

**Käytä Flask-Migrate:**
```bash
pip install Flask-Migrate

# Alusta migraatiot
flask db init

# Luo migraatio
flask db migrate -m "Add new column"

# Suorita migraatio
flask db upgrade
```

### 3. Zero-downtime deployment

**Blue-Green Deployment:**
```bash
# Käynnistä uusi Gunicorn-instanssi eri portissa
gunicorn --bind 127.0.0.1:8001 --config gunicorn_config.py app:app

# Testaa uusi instanssi
curl http://localhost:8001

# Päivitä Nginx osoittamaan uuteen porttiin
sudo nano /etc/nginx/sites-available/loveenhanced
# Muuta: proxy_pass http://127.0.0.1:8001;

# Lataa Nginx uudelleen
sudo nginx -t && sudo systemctl reload nginx

# Sammuta vanha instanssi
kill <old-gunicorn-pid>
```

---

## Palomuurin asetukset

```bash
# Asenna UFW
sudo apt install ufw

# Salli SSH
sudo ufw allow 22/tcp

# Salli HTTP ja HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Salli PostgreSQL (vain localhost)
# Ei tarvitse sallia ulkopuolelta

# Aktivoi palomuuri
sudo ufw enable

# Tarkista status
sudo ufw status
```

---

## Performance-optimointi

### 1. Gunicorn workers

**Laskelma:**
```
workers = (2 x CPU_CORES) + 1
```

Esim. 4 CPU → 9 workers

### 2. PostgreSQL-optimointi

```bash
sudo nano /etc/postgresql/14/main/postgresql.conf
```

```ini
# Memory
shared_buffers = 1GB              # 25% RAM:sta
effective_cache_size = 3GB        # 75% RAM:sta
work_mem = 16MB
maintenance_work_mem = 256MB

# Checkpoints
checkpoint_completion_target = 0.9
wal_buffers = 16MB

# Planner
random_page_cost = 1.1
effective_io_concurrency = 200

# Connections
max_connections = 100
```

```bash
sudo systemctl restart postgresql
```

### 3. Nginx caching

```nginx
# Lisää server-lohkoon:

# Cache static files
location ~* \.(jpg|jpeg|png|gif|ico|css|js|woff|woff2)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}
```

---

## Troubleshooting

### Sovellus ei käynnisty

```bash
# Tarkista lokit
sudo journalctl -u loveenhanced -n 50

# Tarkista portti
sudo netstat -tulpn | grep 8000

# Tarkista prosessit
ps aux | grep gunicorn
```

### Tietokantayhteys ei toimi

```bash
# Testaa yhteys
psql -U loveuser -h localhost -d loveenhanced

# Tarkista PostgreSQL status
sudo systemctl status postgresql

# Tarkista lokit
sudo tail -f /var/log/postgresql/postgresql-14-main.log
```

### 502 Bad Gateway

```bash
# Tarkista että Gunicorn toimii
sudo systemctl status loveenhanced

# Tarkista Nginx-lokit
sudo tail -f /var/log/nginx/loveenhanced_error.log

# Tarkista portti
curl http://localhost:8000
```

---

## Checklist ennen tuotantoa

- [ ] PostgreSQL asennettu ja konfigurattu
- [ ] Tietokanta luotu ja alustettu
- [ ] Vahva SECRET_KEY generoitu
- [ ] .env-tiedosto oikein konfigurattu
- [ ] Gunicorn asennettu ja toimii
- [ ] Nginx asennettu ja konfigurattu
- [ ] SSL-sertifikaatti asennettu (Let's Encrypt)
- [ ] Systemd-palvelu luotu ja aktivoitu
- [ ] Palomuuri (UFW) konfigurattu
- [ ] Backup-scripti luotu ja ajoitettu
- [ ] Monitoring (Sentry, UptimeRobot) konfigurattu
- [ ] DNS-asetukset oikein
- [ ] Testisovellus toimii tuotannossa
- [ ] Dokumentaatio päivitetty

---

## Yhteystiedot

**DevOps-tuki:** devops@loveenhanced.fi  
**Kiireelliset:** +358 40 123 4567

**Versio:** 1.0.0  
**Viimeksi päivitetty:** 24.10.2025
