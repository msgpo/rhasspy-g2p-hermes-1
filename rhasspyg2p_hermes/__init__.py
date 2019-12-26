"""Grapheme to phoneme Hermes service"""
import json
import logging
import subprocess
import re
import tempfile
import typing
from collections import defaultdict
from pathlib import Path

import attr
from rhasspyhermes.base import Message

from .messages import G2pPronounce, G2pPronunciation, G2pPhonemes, G2pError

_LOGGER = logging.getLogger(__name__)


class G2pHermesMqtt:
    """Hermes MQTT server for Rhasspy G2P."""

    DEFAULT_MODEL_ID = "default"
    DEFAULT_DICTIONARY_ID = "default"

    def __init__(
        self,
        client,
        models: typing.Dict[str, Path],
        dictionaries: typing.Dict[str, Path],
        siteIds: typing.Optional[typing.List[str]] = None,
    ):
        self.client = client
        self.models = models
        self.dictionaries = dictionaries
        self.siteIds = siteIds or []

        # Pre-built pronunciation dictionary
        self.dictionaries_loaded: typing.Set[str] = set()
        self.dictionary: typing.Optional[
            typing.Dict[str, typing.List[G2pPronunciation]]
        ] = None

    # -------------------------------------------------------------------------

    def handle_pronounce(
        self, request: G2pPronounce
    ) -> typing.Union[G2pPhonemes, G2pError]:
        """Handle g2p pronounce request"""
        _LOGGER.debug("<- %s", request)

        try:
            # Check dictionaries
            if request.dictionaries is not None:
                phonemes = self.lookup_words(request.words, request.dictionaries)
            else:
                # Guess all pronunciations
                phonemes: typing.Dict[str, typing.List[G2pPronunciation]] = {}

            # Check if any words need to be guessed
            if (request.models is not None) and (len(phonemes) < len(request.words)):
                # Guess missing words
                unknown_words = set(request.words) - set(phonemes.keys())
                guesses = dict(
                    self.guess_words(
                        unknown_words, request.models, num_guesses=request.numGuesses
                    )
                )

                # Join dictionary lookups with guesses
                phonemes = {**phonemes, **guesses}

            return G2pPhonemes(
                id=request.id,
                phonemes=phonemes,
                siteId=request.siteId,
                sessionId=request.sessionId,
            )
        except Exception as e:
            _LOGGER.exception("handle_pronounce")

            # Publish error message
            return G2pError(
                id=request.id,
                siteId=request.siteId,
                sessionId=request.sessionId,
                error=str(e),
                context=",".join(request.words),
            )

    # -------------------------------------------------------------------------

    def lookup_words(
        self, words: typing.Iterable[str], dictionary_ids: typing.List[str]
    ) -> typing.Dict[str, typing.List]:
        """Look up words in a phonetic dictionary"""
        dictionary_ids = set(dictionary_ids or self.dictionaries.keys())

        # Load dictionaries as needed
        if not self.dictionary:
            new_dictionary = {}
            for dictionary_id, dictionary_path in self.dictionaries.items():
                assert (
                    dictionary_id in self.dictionaries
                ), f"Missing dictionary id {dictionary_id}"

                dictionary_path = self.dictionaries[dictionary_id]
                _LOGGER.debug(
                    "Loading dictionary from %s (%s)", dictionary_path, dictionary_id
                )

                # Load pronunciations
                with open(dictionary_path, "r") as dictionary_file:
                    for i, line in enumerate(dictionary_file):
                        line = line.strip()
                        if not line:
                            continue

                        try:
                            # Use explicit whitespace (avoid 0xA0)
                            parts = re.split(r"[ \t]+", line)
                            line_word = parts[0]

                            # Skip Julius extras
                            parts = [p for p in parts[1:] if p[0] not in ["[", "@"]]

                            idx = line_word.find("(")
                            if idx > 0:
                                line_word = line_word[:idx]

                            if "+" in line_word:
                                # Julius format word1+word2
                                line_words = line_word.split("+")
                            else:
                                line_words = [line_word]

                            for word in line_words:
                                # Add pronunciation
                                pronunciations = new_dictionary.get(word, [])
                                pronunciations.append(
                                    G2pPronunciation(
                                        word=word,
                                        dictionaryId=dictionary_id,
                                        phonemes=parts,
                                    )
                                )
                                new_dictionary[word] = pronunciations
                        except Exception as e:
                            _LOGGER.warning("%s: %s (line %s)", dictionary_id, e, i + 1)

                # Save for later
            self.dictionary = new_dictionary

        # Gather all eligible pronunciations
        pronunciations = defaultdict(list)
        for word in words:
            for word_pron in self.dictionary.get(word, []):
                # Make sure pronunciation comes from appropriate dictionary
                if word_pron.dictionaryId in dictionary_ids:
                    pronunciations[word].append(word_pron)

        return pronunciations

    def guess_words(
        self,
        words: typing.Iterable[str],
        model_ids: typing.List[str],
        num_guesses: int = 5,
    ) -> typing.Iterable[typing.Tuple[str, G2pPronunciation]]:
        """Guess pronunciations for words"""
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".txt") as wordlist_file:
            # Write words to a temporary word list file
            for word in words:
                print(word, file=wordlist_file)

            wordlist_file.seek(0)

            # Guess pronunciations with each eligible G2P model
            model_ids = model_ids or self.models.keys()
            for model_id in model_ids:
                assert model_id in self.models, f"Missing G2P model {model_id}"
                model_path = self.models[model_id]

                # Output phonetisaurus results to temporary file
                with tempfile.NamedTemporaryFile(
                    mode="w+", suffix=".txt"
                ) as pronounce_file:
                    # Use phonetisaurus to guess pronunciations
                    g2p_command = [
                        "phonetisaurus-apply",
                        "--model",
                        str(model_path),
                        "--word_list",
                        wordlist_file.name,
                        "--nbest",
                        str(num_guesses),
                    ]

                    _LOGGER.debug(repr(g2p_command))
                    subprocess.check_call(g2p_command, stdout=pronounce_file)

                    pronounce_file.seek(0)

                    # Read results
                    ws_pattern = re.compile(r"\s+")
                    for line in pronounce_file:
                        line = line.strip()
                        if line:
                            # word P1 P2 P3...
                            parts = ws_pattern.split(line)
                            word = parts[0].strip()
                            phonemes = parts[1:]
                            yield (
                                word,
                                G2pPronunciation(
                                    word=word, phonemes=phonemes, modelId=model_id
                                ),
                            )

    # -------------------------------------------------------------------------

    def on_connect(self, client, userdata, flags, rc):
        """Connected to MQTT broker."""
        try:
            topics = [G2pPronounce.topic()]
            for topic in topics:
                self.client.subscribe(topic)
                _LOGGER.debug("Subscribed to %s", topic)
        except Exception:
            _LOGGER.exception("on_connect")

    def on_message(self, client, userdata, msg):
        """Received message from MQTT broker."""
        try:
            _LOGGER.debug("Received %s byte(s) on %s", len(msg.payload), msg.topic)
            if msg.topic == G2pPronounce.topic():
                json_payload = json.loads(msg.payload)

                # Check siteId
                if not self._check_siteId(json_payload):
                    return

                self.publish(self.handle_pronounce(G2pPronounce(**json_payload)))
        except Exception:
            _LOGGER.exception("on_message")

    def publish(self, message: Message, **topic_args):
        """Publish a Hermes message to MQTT."""
        try:
            _LOGGER.debug("-> %s", message)
            topic = message.topic(**topic_args)
            payload = json.dumps(attr.asdict(message))
            _LOGGER.debug("Publishing %s char(s) to %s", len(payload), topic)
            self.client.publish(topic, payload)
        except Exception:
            _LOGGER.exception("on_message")

    # -------------------------------------------------------------------------

    def _check_siteId(self, json_payload: typing.Dict[str, typing.Any]) -> bool:
        if self.siteIds:
            return json_payload.get("siteId", "default") in self.siteIds

        # All sites
        return True
