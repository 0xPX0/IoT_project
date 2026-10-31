# Supervision IoT industrielle

Prototype de supervision de deux équipements industriels. Des capteurs Python simulent des températures et les publient sur un broker Mosquitto. Un superviseur reçoit les mesures et génère les alertes.

## Fonctionnement

- `capteur-101` et `capteur-102` : une mesure toutes les 3 secondes, avec des pointes pour tester les alertes.
- `broker` : échanges MQTT sur le port 8883 avec authentification mTLS.
- `superviseur` : contrôle des messages, alerte à partir de 85 °C et après 15 secondes sans mesure valide.

Chaque capteur possède son certificat et ne peut publier que sur son propre topic. Les services utilisent deux réseaux Docker internes, sans port publié sur l’hôte.

## Stack

- Mosquitto `2.0.18`
- Python `3.12-slim`
- Paho MQTT `2.1.0`
- Docker Compose

## Lancement

Depuis la racine du projet, avec Docker classique sans remappage des UID :

```bash
# À faire uniquement lors de la première installation
bash scripts/generate-certs.sh

sudo chown 10001:10001 certs/out/capteur-{101,102}.key
sudo chown 10002:10002 certs/out/superviseur.key
sudo chown 10003:10003 certs/out/broker.key mosquitto/acl
sudo chmod 600 certs/out/*.key mosquitto/acl
chmod 644 certs/out/*.crt mosquitto/mosquitto.conf

docker compose build capteur-101 superviseur
docker compose up -d
```

Le script de génération refuse de remplacer des certificats déjà présents.

## Vérification

```bash
docker compose ps
docker compose logs -f superviseur
```

Pour tester l’absence puis le retour d’un capteur :

```bash
docker compose stop capteur-101
# Attendre l’alerte d’absence
docker compose start capteur-101
```

Les tests réalisés couvrent le rejet d’un client sans certificat, le refus d’une publication non autorisée et l’alerte d’objet inconnu. Les preuves sont conservées dans `preuves/`.

## Arrêt

```bash
docker compose down
```

Les clés privées ne doivent pas être ajoutées au dépôt ni à l’archive du rendu. Les températures et seuils utilisés servent à la démonstration.