"""Hermes MQTT service for Rhasspy G2P"""
import argparse
import logging
import os
import threading
import time
import typing
from pathlib import Path

import paho.mqtt.client as mqtt

from . import G2pHermesMqtt

_LOGGER = logging.getLogger(__name__)


def main():
    """Main method."""
    parser = argparse.ArgumentParser(prog="rhasspyg2p_hermes")
    parser.add_argument(
        "--model",
        nargs="+",
        action="append",
        required=True,
        help="Id and path to g2p FST model",
    )
    parser.add_argument(
        "--dictionary",
        nargs="+",
        action="append",
        help="Id and path to phonetic dictionary",
    )
    parser.add_argument(
        "--reload",
        type=float,
        default=None,
        help="Poll dictionary file(s) for given number of seconds and automatically reload when changed",
    )
    parser.add_argument(
        "--host", default="localhost", help="MQTT host (default: localhost)"
    )
    parser.add_argument(
        "--port", type=int, default=1883, help="MQTT port (default: 1883)"
    )
    parser.add_argument(
        "--siteId",
        action="append",
        help="Hermes siteId(s) to listen for (default: all)",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Print DEBUG messages to the console"
    )
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    _LOGGER.debug(args)

    # Load model paths
    models = {}
    for model_args in args.model:
        if len(model_args) == 1:
            # Path only
            models[G2pHermesMqtt.DEFAULT_MODEL_ID] = Path(model_args[0])
        else:
            # Id and path
            models[model_args[0]] = Path(model_args[1])

    _LOGGER.debug("Models: %s", models)

    # Load dictionary paths
    dictionaries = {}
    if args.dictionary:
        for dictionary_args in args.dictionary:
            if len(dictionary_args) == 1:
                # Path only
                dictionaries[G2pHermesMqtt.DEFAULT_DICTIONARY_ID] = Path(
                    dictionary_args[0]
                )
            else:
                # Id and path
                dictionaries[dictionary_args[0]] = Path(dictionary_args[1])

    _LOGGER.debug("Dictionaries: %s", dictionaries)

    try:
        # Listen for messages
        client = mqtt.Client()
        hermes = G2pHermesMqtt(
            client, models=models, dictionaries=dictionaries, siteIds=args.siteId
        )

        if args.reload and args.dictionary:
            # Start polling thread
            threading.Thread(
                target=poll_dictionaries,
                args=(args.reload, dictionaries, hermes),
                daemon=True,
            ).start()

        def on_disconnect(client, userdata, flags, rc):
            try:
                # Automatically reconnect
                _LOGGER.info("Disconnected. Trying to reconnect...")
                client.reconnect()
            except Exception:
                logging.exception("on_disconnect")

        # Connect
        client.on_connect = hermes.on_connect
        client.on_disconnect = on_disconnect
        client.on_message = hermes.on_message

        _LOGGER.debug("Connecting to %s:%s", args.host, args.port)
        client.connect(args.host, args.port)

        client.loop_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _LOGGER.debug("Shutting down")


# -----------------------------------------------------------------------------


def poll_dictionaries(
    seconds: float, dictionaries: typing.Dict[str, Path], hermes: G2pHermesMqtt
):
    """Watch dictionary files for changes and reload."""
    last_timestamps: typing.Dict[str, int] = {}

    while True:
        time.sleep(seconds)
        try:
            do_reload = False
            for dictionary_id, dictionary_path in dictionaries.items():
                if not dictionary_path.is_file():
                    # Wait if file doesn't exist
                    continue

                timestamp = os.stat(dictionary_path).st_mtime_ns
                if dictionary_id not in last_timestamps:
                    last_timestamps[dictionary_id] = timestamp
                elif timestamp != last_timestamps[dictionary_id]:
                    do_reload = True
                    _LOGGER.debug(
                        "Re-loading dictionary %s (%s)", dictionary_path, dictionary_id
                    )
                    last_timestamps[dictionary_id] = timestamp

            if do_reload:
                # Force reloading of all dictionaries
                hermes.dictionary = None

        except Exception:
            _LOGGER.exception("poll_dictionaries")


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    main()
