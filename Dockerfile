FROM python:3.11-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV LC_ALL=C.UTF-8

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    libsasl2-dev \
    libldap2-dev \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    libmagic1 \
    libusb-1.0-0 \
    wkhtmltopdf \
    xfonts-75dpi \
    xfonts-base \
    && rm -rf /var/lib/apt/lists/*

# Create odoo user and directories
RUN useradd -m -d /opt/odoo -s /bin/bash odoo \
    && mkdir -p /var/lib/odoo /etc/odoo \
    && chown odoo:odoo /var/lib/odoo /etc/odoo

# Install Python dependencies
COPY requirements.txt /opt/odoo/requirements.txt
RUN pip install --no-cache-dir -r /opt/odoo/requirements.txt

# Copy source code
COPY --chown=odoo:odoo . /opt/odoo

# Copy deployment config
COPY --chown=odoo:odoo odoo.deploy.conf /etc/odoo/odoo.conf

# Copy render startup script
COPY --chown=odoo:odoo render-start.sh /opt/odoo/render-start.sh
RUN chmod +x /opt/odoo/render-start.sh

VOLUME ["/var/lib/odoo"]
EXPOSE 8069 8072

USER odoo
ENTRYPOINT ["python3", "/opt/odoo/odoo-bin"]
CMD ["-c", "/etc/odoo/odoo.conf"]
