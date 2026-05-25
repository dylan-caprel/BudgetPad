# Déploiement BudgetPAD en production

Guide pratique pour passer de la démo locale au déploiement réel.

## 1. Pré-requis serveur

- Debian/Ubuntu 22.04+ (ou Windows Server 2019+)
- Python 3.12+ (Python 3.14 testé)
- MySQL 8 (ou MariaDB 10.6+)
- Nginx (reverse proxy + TLS)
- 2 vCPU / 4 Go RAM minimum
- Domaine + certificat SSL (Let's Encrypt)

## 2. Installation

```bash
# 1. Cloner le projet
git clone <repo> /opt/budgetpad
cd /opt/budgetpad

# 2. Environnement Python
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
pip install gunicorn sentry-sdk  # production extras

# 3. Configurer la base
mysql -u root -p <<SQL
CREATE DATABASE budgetpad CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'budgetpad'@'localhost' IDENTIFIED BY 'mot-de-passe-fort';
GRANT ALL PRIVILEGES ON budgetpad.* TO 'budgetpad'@'localhost';
SQL

# 4. Configurer l'environnement
cp .env.example .env
# Editer .env :
#   DJANGO_ENV=prod
#   DEBUG=False
#   SECRET_KEY=<generer>
#   ALLOWED_HOSTS=budgetpad.pad.cm
#   CSRF_TRUSTED_ORIGINS=https://budgetpad.pad.cm
#   ADMIN_URL=back-office-pad/
#   SENTRY_DSN=... (optionnel)

# 5. Migrations + statics
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser

# 6. Verifier la configuration de securite Django
python manage.py check --deploy
```

## 3. Gunicorn (service systemd)

`/etc/systemd/system/budgetpad.service` :

```ini
[Unit]
Description=BudgetPAD Gunicorn
After=network.target mysql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/budgetpad
Environment="PATH=/opt/budgetpad/env/bin"
EnvironmentFile=/opt/budgetpad/.env
ExecStart=/opt/budgetpad/env/bin/gunicorn budgetpad.wsgi:application \
    --workers 3 \
    --bind unix:/run/budgetpad.sock \
    --access-logfile /opt/budgetpad/logs/gunicorn-access.log \
    --error-logfile /opt/budgetpad/logs/gunicorn-error.log
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable budgetpad
sudo systemctl start budgetpad
```

## 4. Nginx

`/etc/nginx/sites-available/budgetpad` :

```nginx
server {
    listen 80;
    server_name budgetpad.pad.cm;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name budgetpad.pad.cm;

    ssl_certificate     /etc/letsencrypt/live/budgetpad.pad.cm/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/budgetpad.pad.cm/privkey.pem;

    # Securite TLS moderne
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    client_max_body_size 10M;

    location /static/ {
        alias /opt/budgetpad/staticfiles/;
        expires 30d;
    }

    location /media/ {
        alias /opt/budgetpad/media/;
        expires 30d;
    }

    location / {
        proxy_pass http://unix:/run/budgetpad.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/budgetpad /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

## 5. Tâches périodiques (cron)

```cron
# Audit chain - verif quotidienne
30 2 * * * cd /opt/budgetpad && env/bin/python manage.py verify_audit_chain >> logs/audit.log 2>&1

# Purge journal > 5 ans (RGPD) - mensuel
0 3 1 * * cd /opt/budgetpad && env/bin/python manage.py purge_journal --days 1825 --confirm >> logs/purge.log 2>&1

# Backup DB - quotidien (a chiffrer)
0 1 * * * mysqldump --single-transaction budgetpad | gzip | gpg --encrypt --recipient backup@pad.cm > /backup/budgetpad-$(date +\%F).sql.gz.gpg
```

## 6. Sauvegarde / restauration

### Backup quotidien chiffré

```bash
# Script /opt/budgetpad/scripts/backup.sh
#!/bin/bash
set -e
DATE=$(date +%Y-%m-%d)
DEST=/backup/budgetpad
mkdir -p $DEST
mysqldump --single-transaction --routines budgetpad \
    | gzip -9 \
    | gpg --encrypt --recipient backup@pad.cm \
    > $DEST/budgetpad-$DATE.sql.gz.gpg
# Conserver 30 jours
find $DEST -name "budgetpad-*.sql.gz.gpg" -mtime +30 -delete
```

### Restauration

```bash
gpg --decrypt budgetpad-2026-05-19.sql.gz.gpg | gunzip | mysql budgetpad
python manage.py verify_audit_chain   # verifier l'integrite apres restore
```

## 7. Mise à jour applicative

```bash
cd /opt/budgetpad
sudo -u www-data git pull
sudo -u www-data env/bin/pip install -r requirements.txt
sudo -u www-data env/bin/python manage.py migrate
sudo -u www-data env/bin/python manage.py collectstatic --noinput
sudo systemctl restart budgetpad
```

## 8. Monitoring

- **Sentry** : définir `SENTRY_DSN` dans `.env` (erreurs + performance)
- **Logs applicatifs** : `/opt/budgetpad/logs/budgetpad.log`
- **Logs sécurité** : `/opt/budgetpad/logs/security.log` (logins, axes)
- **Logs Gunicorn** : `/opt/budgetpad/logs/gunicorn-*.log`
- **Logs Nginx** : `/var/log/nginx/access.log`, `error.log`

### Alertes recommandées

| Métrique | Seuil | Outil |
|---|---|---|
| Erreurs 5xx > 5/min | Alerte | Sentry |
| Logins échoués > 50/h | Alerte | grep security.log |
| Espace disque < 20 % | Alerte | Prometheus node_exporter |
| Backup > 36 h sans succès | Alerte critique | cron job watchdog |
| `verify_audit_chain` KO | Alerte critique | cron mail |

## 9. Sécurité

- ✅ HTTPS obligatoire (HSTS 1 an, redirect 301 depuis HTTP)
- ✅ Cookies `Secure` + `HttpOnly` + `SameSite=Lax`
- ✅ ADMIN_URL non-deviné (pas `/admin/`)
- ✅ `django-axes` (anti brute-force) : 5 essais / IP+user
- ✅ Force changement mot de passe au 1er login
- ✅ Audit trail signé (SHA-256 chaîné)
- ✅ CSRF sur toutes les actions destructives
- ✅ Sentry sans PII (`send_default_pii=False`)
- ✅ Backup chiffré GPG

## 10. Checklist pré-prod

```bash
# Doit retourner 0 warning :
DJANGO_ENV=prod python manage.py check --deploy

# Tests doivent passer :
python -m pytest

# La chaîne d'audit doit être valide :
python manage.py verify_audit_chain
```
