#!/bin/sh
set -eu

SYSTEM_CA="/etc/ssl/certs/ca-certificates.crt"
TARGET_CA="${MAX_CA_BUNDLE:-/tmp/max-ca-bundle.pem}"

if [ "$TARGET_CA" != "$SYSTEM_CA" ]; then
    cp "$SYSTEM_CA" "$TARGET_CA"
    for certificate in /certs/*.pem /certs/*.cer /certs/*.crt; do
        if [ -f "$certificate" ]; then
            if grep -q -- "-----BEGIN CERTIFICATE-----" "$certificate"; then
                printf '\n' >> "$TARGET_CA"
                sed -e 's/\r$//' "$certificate" >> "$TARGET_CA"
            else
                echo "Skipping non-PEM certificate: $certificate" >&2
            fi
        fi
    done
fi

exec "$@"
