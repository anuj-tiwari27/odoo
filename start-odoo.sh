#!/bin/bash
# Start Odoo 19.0 test instance
# Requires: PostgreSQL running locally, Python deps installed

set -e

# Start PostgreSQL if not running
if ! pg_isready -q 2>/dev/null; then
    echo "Starting PostgreSQL..."
    sudo service postgresql start
fi

# Check if database exists, if not initialize
DB_EXISTS=$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='odoo'" 2>/dev/null || echo "0")
if [ "$DB_EXISTS" != "1" ]; then
    echo "Creating database and installing modules..."
    sudo -u postgres psql -c "CREATE USER odoo WITH SUPERUSER PASSWORD 'odoo';" 2>/dev/null || true
    sudo -u postgres psql -c "CREATE DATABASE odoo OWNER odoo;" 2>/dev/null
    python3 odoo-bin -d odoo --db_host=localhost --db_user=odoo --db_password=odoo \
        --addons-path=odoo/addons,addons \
        -i sale,crm,stock,account \
        --stop-after-init --without-demo=all
fi

echo "Starting Odoo on http://localhost:8069"
python3 odoo-bin -d odoo --db_host=localhost --db_user=odoo --db_password=odoo \
    --addons-path=odoo/addons,addons --http-port=8069
