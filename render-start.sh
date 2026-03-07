#!/bin/bash
set -e

# Parse DATABASE_URL into individual components for Odoo config
eval $(python3 -c "
from urllib.parse import urlparse, unquote
import os
url = urlparse(os.environ['DATABASE_URL'])
print(f'DB_HOST={url.hostname}')
print(f'DB_PORT={url.port or 5432}')
print(f'DB_USER={url.username}')
print(f'DB_PASS={unquote(url.password)}')
print(f'DB_NAME={url.path.lstrip(\"/\")}')
")

PORT=${PORT:-8069}

# Generate odoo.conf at runtime with Render's database credentials
cat > /etc/odoo/odoo.conf << EOF
[options]
admin_passwd = ${ODOO_ADMIN_PASSWD:-admin}
db_host = $DB_HOST
db_port = $DB_PORT
db_user = $DB_USER
db_password = $DB_PASS
db_name = $DB_NAME
addons_path = /opt/odoo/odoo/addons,/opt/odoo/addons
data_dir = /var/lib/odoo
http_port = $PORT
proxy_mode = True
default_productivity_apps = True
workers = 0
log_level = info
list_db = False
EOF

# Start Odoo — initialize with base module on first run
exec python3 /opt/odoo/odoo-bin -c /etc/odoo/odoo.conf -i base
