import json
import logging
import os
import random
import signal
import ssl
import threading
import time

import paho.mqtt.client as mqtt


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("capteur")

connected = threading.Event()
stop = threading.Event()


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        logger.error("Connexion refusée : %s", reason_code)
        return

    connected.set()
    logger.info("Connexion MQTT établie")


def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    connected.clear()

    if reason_code.is_failure:
        logger.warning("Connexion perdue : %s", reason_code)


def on_publish(client, userdata, mid, reason_code, properties):
    if reason_code.is_failure:
        logger.error(
            "Publication refusée : mid=%s code=%s raison=%s",
            mid,
            reason_code.value,
            reason_code,
        )
    else:
        logger.info(
            "Publication confirmée : mid=%s code=%s",
            mid,
            reason_code.value,
        )


def request_stop(signum, frame):
    stop.set()


def main():
    capteur_id = os.environ["CAPTEUR_ID"]
    topic = os.environ["TOPIC"]

    host = os.getenv("MQTT_HOST", "broker")
    port = int(os.getenv("MQTT_PORT", "8883"))

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
        client_id=capteur_id,
        protocol=mqtt.MQTTv5,
    )

    client.tls_set_context(context)
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_publish = on_publish
    client.enable_logger(logger)

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    client.connect_async(host, port, keepalive=30)
    client.loop_start()

    sequence = 0

    try:
        while not stop.is_set():
            if not connected.wait(timeout=1):
                continue

            sequence += 1
            temperature = random.uniform(60, 75)

            # Pointe régulière pour tester l'alerte de surchauffe.
            if sequence % 7 == 0:
                temperature = random.uniform(86, 95)

            payload = {
                "capteur": capteur_id,
                "temperature_c": round(temperature, 1),
                "timestamp": int(time.time()),
                "sequence": sequence,
            }

            result = client.publish(
                topic,
                json.dumps(payload),
                qos=1,
                retain=False,
            )

            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                logger.warning(
                    "Échec local de publication : %s",
                    mqtt.error_string(result.rc),
                )
            else:
                logger.info(
                    "Mesure envoyée : capteur=%s température=%.1f topic=%s",
                    capteur_id,
                    payload["temperature_c"],
                    topic,
                )

            stop.wait(3)

    finally:
        client.disconnect()
        client.loop_stop()
        logger.info("Arrêt du capteur")


if __name__ == "__main__":
    main()