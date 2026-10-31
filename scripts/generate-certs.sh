#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CA_DIR="$ROOT_DIR/certs/ca"
OUT_DIR="$ROOT_DIR/certs/out"

umask 077

mkdir -p "$CA_DIR" "$OUT_DIR"

# Éviter de remplacer une PKI existante par erreur.
if find "$CA_DIR" "$OUT_DIR" -type f -print -quit | grep -q .; then
    echo "Erreur : certs/ca ou certs/out contient déjà des fichiers." >&2
    echo "Sauvegarde ou retire l'ancienne PKI avant de continuer." >&2
    exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "Création de l'autorité de certification..."

openssl genpkey \
    -algorithm RSA \
    -pkeyopt rsa_keygen_bits:3072 \
    -out "$CA_DIR/ca.key"

openssl req \
    -x509 \
    -new \
    -sha256 \
    -days 3650 \
    -key "$CA_DIR/ca.key" \
    -out "$OUT_DIR/ca.crt" \
    -subj "/CN=IIoT-Lab-CA" \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -addext "subjectKeyIdentifier=hash"

cat > "$TMP_DIR/server.ext" <<'EOF'
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:broker
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid,issuer
EOF

cat > "$TMP_DIR/client.ext" <<'EOF'
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature
extendedKeyUsage=clientAuth
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid,issuer
EOF

create_certificate() {
    local name="$1"
    local extensions="$2"

    echo "Création du certificat : $name"

    openssl genpkey \
        -algorithm RSA \
        -pkeyopt rsa_keygen_bits:3072 \
        -out "$OUT_DIR/$name.key"

    openssl req \
        -new \
        -sha256 \
        -key "$OUT_DIR/$name.key" \
        -out "$TMP_DIR/$name.csr" \
        -subj "/CN=$name"

    openssl x509 \
        -req \
        -sha256 \
        -days 365 \
        -in "$TMP_DIR/$name.csr" \
        -CA "$OUT_DIR/ca.crt" \
        -CAkey "$CA_DIR/ca.key" \
        -set_serial "0x$(openssl rand -hex 16)" \
        -extfile "$extensions" \
        -out "$OUT_DIR/$name.crt"
}

create_certificate broker "$TMP_DIR/server.ext"

for name in capteur-101 capteur-102 superviseur; do
    create_certificate "$name" "$TMP_DIR/client.ext"
done

chmod 600 "$CA_DIR/ca.key" "$OUT_DIR/"*.key
chmod 644 "$OUT_DIR/"*.crt

echo "Certificats générés dans : $OUT_DIR"
echo "Clé privée de l'autorité conservée dans : $CA_DIR"