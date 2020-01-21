"""Tests for rhasspyg2p_hermes"""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

from rhasspyg2p_hermes import G2pHermesMqtt
from rhasspyg2p_hermes.messages import G2pPronounce, G2pPhonemes


def test_lookup_words():
    """Test dictionary look up"""
    client = MagicMock()
    hermes = G2pHermesMqtt(client, models={}, dictionaries={})

    dictionary_id = str(uuid4())

    with tempfile.NamedTemporaryFile(mode="w") as dict_file:
        # Create fake dictionary
        print("foo", "F", "O", "O", file=dict_file)
        print("bar", "B", "A", "R", file=dict_file)
        print("baz", "B", "A", "Z", file=dict_file)
        dict_file.seek(0)

        hermes.dictionaries[dictionary_id] = Path(dict_file.name)

        # Look up words in fake dictionary
        result = hermes.handle_pronounce(G2pPronounce(words=["foo", "bar"]))
        assert isinstance(result, G2pPhonemes)

        assert len(result.phonemes) == 2

        # Check pronunciations
        assert "foo" in result.phonemes
        assert len(result.phonemes["foo"]) == 1
        foo_pron = result.phonemes["foo"][0]
        assert foo_pron.word == "foo"
        assert foo_pron.dictionaryId == dictionary_id
        assert foo_pron.modelId is None
        assert foo_pron.phonemes == ["F", "O", "O"]
