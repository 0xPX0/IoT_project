import json
import logging
import math
import os
import signal
import ssl
import threading
import time

import paho.mqtt.client as mqtt


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("superviseur")

TOPICS = {
    "capteur-101": "industrie/etage-1/salle-01/temperature",
    "capteur-102": "industrie/etage-1/salle-02/temperature",
}

ALLOWED_CAPTEURS = {
    name.strip()
    for name in os.environ["ALLOWED_CAPTEURS"].split(",")
    if name.strip()
}

THRESHOLD = float(os.getenv("TEMPERATURE_THRESHOLD", "85"))
ABSENCE_TIMEOUT = float(os.getenv("ABSENCE_TIMEOUT", "15"))

stop = threading.Event()
subscribed = threading.Event()
state_lock = threading.Lock()

last_seen = {}
missing = set()


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        logger.error("Connexion refusée : %s", reason_code)
        return

    logger.info("Connexion MQTT établie")

    result, _ = client.subscribe("industrie/#", qos=1)

    if result != mqtt.MQTT_ERR_SUCCESS:
        logger.error("Impossible d'envoyer la demande d'abonnement")


def on_subscribe(client, userdata, mid, reason_codes, properties):
    if not reason_codes or any(code.is_failure for code in reason_codes):
        logger.error("Abonnement refusé : %s", reason_codes)
        return

    # Une nouvelle période de surveillance commence après l'abonnement.
    with state_lock:
        now = time.monotonic()

        for capteur in ALLOWED_CAPTEURS:
            last_seen[capteur] = now

        missing.clear()
        subscribed.set()

    logger.info("Abonnement confirmé : industrie/#")


def on_disconnect(client, userdata, flags, reason_code, properties):
    with state_lock:
        subscribed.clear()

    if not stop.is_set():
        logger.warning(
            "[ALERTE_LIAISON] Superviseur déconnecté du broker : %s",
            reason_code,
        )


def on_connect_fail(client, userdata):
    logger.warning("Broker injoignable : nouvelle tentative automatique")


def on_message(client, userdata, message):
    if len(message.payload) > 4096:
        logger.warning("[MESSAGE_INVALIDE] Message trop volumineux")
        return

    try:
        data = json.loads(message.payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        logger.warning("[MESSAGE_INVALIDE] JSON illisible")
        return

    if not isinstance(data, dict):
        logger.warning("[MESSAGE_INVALIDE] Un objet JSON est attendu")
        return

    capteur = data.get("capteur")

    if not isinstance(capteur, str):
        logger.warning("[MESSAGE_INVALIDE] Identifiant absent ou invalide")
        return

    if capteur not in ALLOWED_CAPTEURS:
        logger.warning(
            "[ALERTE_INTRUSION] Objet déclaré inconnu : %r topic=%s",
            capteur,
            message.topic,
        )
        return

    if message.topic != TOPICS[capteur]:
        logger.warning(
            "[ALERTE_INTRUSION] Identité et topic incohérents : "
            "capteur=%s topic=%s",
            capteur,
            message.topic,
        )
        return

    temperature = data.get("temperature_c")
    timestamp = data.get("timestamp")

    # bool est un sous-type de int en Python : on l'exclut explicitement.
    if type(temperature) not in (int, float):
        logger.warning("[MESSAGE_INVALIDE] Température invalide : %s", capteur)
        return

    if not -100 <= temperature <= 300:
        logger.warning(
            "[MESSAGE_INVALIDE] Température hors plage de simulation : %s",
            capteur,
        )
        return

    if type(timestamp) is not int:
        logger.warning("[MESSAGE_INVALIDE] Horodatage invalide : %s", capteur)
        return

    age = time.time() - timestamp

    if not -5 <= age <= 30:
        logger.warning(
            "[MESSAGE_INVALIDE] Mesure trop ancienne ou future : %s",
            capteur,
        )
        return

    with state_lock:
        last_seen[capteur] = time.monotonic()

        if capteur in missing:
            missing.remove(capteur)
            logger.info("[RETOUR_CAPTEUR] Mesures rétablies : %s", capteur)

    logger.info(
        "Mesure reçue : capteur=%s température=%.1f °C",
        capteur,
        temperature,
    )

    if temperature >= THRESHOLD:
        logger.warning(
            "[ALERTE_SEUIL] %s : %.1f °C, seuil %.1f °C",
            capteur,
            temperature,
            THRESHOLD,
        )


def check_absence():
    with state_lock:
        if not subscribed.is_set():
            return

        now = time.monotonic()

        for capteur, last_received in last_seen.items():
            elapsed = now - last_received

            if elapsed >= ABSENCE_TIMEOUT and capteur not in missing:
                missing.add(capteur)

                logger.warning(
                    "[ALERTE_ABSENCE] %s : aucune mesure valide depuis %.0f s",
                    capteur,
                    elapsed,
                )


def request_stop(signum, frame):
    stop.set()


def main():
    if not ALLOWED_CAPTEURS or not ALLOWED_CAPTEURS <= TOPICS.keys():
        raise ValueError("Allowlist vide ou capteur sans topic configuré")

    if not math.isfinite(THRESHOLD):
        raise ValueError("Le seuil doit être un nombre fini")

    if not math.isfinite(ABSENCE_TIMEOUT) or ABSENCE_TIMEOUT <= 0:
        raise ValueError("Le délai d'absence doit être positif et fini")

    context = ssl.create_default_context(
        cafile=os.environ["CA_CERT"],
    )
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(
        certfile=os.environ["CLIENT_CERT"],
        keyfile=os.environ["CLIENT_KEY"],
    )

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="superviseur",
        protocol=mqtt.MQTTv5,
    )

    client.tls_set_context(context)
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_disconnect = on_disconnect
    client.on_connect_fail = on_connect_fail
    client.on_message = on_message
    client.enable_logger(logger)

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    client.connect_async(
        os.getenv("MQTT_HOST", "broker"),
        int(os.getenv("MQTT_PORT", "8883")),
        keepalive=30,
    )
    client.loop_start()

    try:
        while not stop.wait(1):
            check_absence()
    finally:
        client.disconnect()
        client.loop_stop()
        logger.info("Arrêt du superviseur")


if __name__ == "__main__":
    main()