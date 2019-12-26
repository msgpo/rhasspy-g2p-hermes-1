"""Tests for rhasspyg2p_hermes"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

from rhasspyg2p_hermes import G2pHermesMqtt
from rhasspyg2p_hermes.messages import G2pPronounce, G2pPhonemes


class G2pHermesTestCase(unittest.TestCase):
    """Tests for rhasspyg2p_hermes"""

    def setUp(self):
        client = MagicMock()
        self.hermes = G2pHermesMqtt(client, models={}, dictionaries={})

    def test_lookup_words(self):
        """Test dictionary look up"""
        dictionary_id = str(uuid4())

        with tempfile.NamedTemporaryFile(mode="w") as dict_file:
            # Create fake dictionary
            print("foo", "F", "O", "O", file=dict_file)
            print("bar", "B", "A", "R", file=dict_file)
            print("baz", "B", "A", "Z", file=dict_file)
            dict_file.seek(0)

            self.hermes.dictionaries[dictionary_id] = Path(dict_file.name)

            # Look up words in fake dictionary
            result = self.hermes.handle_pronounce(G2pPronounce(words=["foo", "bar"]))
            self.assertIsInstance(result, G2pPhonemes)

            self.assertEqual(len(result.phonemes), 2)

            # Check pronunciations
            self.assertIn("foo", result.phonemes)
            self.assertEqual(len(result.phonemes["foo"]), 1)
            foo_pron = result.phonemes["foo"][0]
            self.assertEqual(foo_pron.word, "foo")
            self.assertEqual(foo_pron.dictionaryId, dictionary_id)
            self.assertIsNone(foo_pron.modelId)
            self.assertEqual(foo_pron.phonemes, ["F", "O", "O"])
