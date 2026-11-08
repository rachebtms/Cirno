"""Answer boundaries and identities survive streaming, recovery and large chunks."""

import hashlib
import json

import pytest
from cirno_core.session.transcript.answer_digest import AnswerDigest, assistant_signature_identity
from cirno_core.session.transcript.answers import visit_transcript_answers
from cirno_core.session.transcript.recovery import transcript_turn_signature


def expected_identity(texts):
    return hashlib.sha256(json.dumps(texts, ensure_ascii=False).encode()).hexdigest() if texts else ""


@pytest.mark.parametrize("texts", [(), ("",), (" a ", "雪❄️\n\t\"\\"), ("x" * 20000, "line\nnext")])
def test_canonical_identity_preserves_exact_json_string_contents(texts):
    assert assistant_signature_identity(texts) == expected_identity(texts)


@pytest.mark.parametrize("records, expected", [
    ([{"event": "delta", "text": " first "}, {"event": "delta", "text": "\nnext "}], ("first \nnext",)),
    ([{"event": "delta", "text": "discard"}, {"event": "stream_end", "text": "final"}], ("final",)),
    ([{"event": "delta", "text": "discard"}, {"event": "stream_end", "text": ""}], ()),
    ([{"event": "delta", "text": "first"}, {"event": "stream_end", "text": None}], ("first",)),
    ([{"event": "delta", "text": "partial"}, {"event": "stream_end", "resuming": True, "merge_next": True, "text": "corrected "},
      {"event": "delta", "text": "continuation"}, {"event": "stream_end"}], ("corrected continuation",)),
    ([{"event": "delta", "text": "first "}, {"event": "stream_end", "resuming": True, "merge_next": True},
      {"event": "delta", "text": "second"}], ("first second",)),
    ([{"event": "delta", "text": "a"}, {"event": "message", "kind": "progress", "text": "hidden"},
      {"event": "delta", "text": "b"}, {"event": "message", "text": " c "}, {"event": "delta", "text": "d"},
      {"event": "reasoning_delta", "text": "hidden"}, {"event": "delta", "text": "e"}, {"event": "user"},
      {"event": "message", "kind": "reasoning", "text": "hidden"}, {"event": "delta", "text": "f"}, {"event": "turn_end"}], ("ab", "c", "d", "e", "f")),
    ([{"event": "message", "text": " \t\n"}, {"event": "message", "text": 10}, {"event": "delta", "text": None}], ()),
])
def test_recovery_and_index_share_answer_boundaries(records, expected):
    assert transcript_turn_signature(iter(records)) == expected
    digest = AnswerDigest()
    visit_transcript_answers(iter(records), digest.append, digest.replace, digest.finish)
    assert digest.identity() == expected_identity(expected)
    assert digest.first_preview == (expected[0][:240] if expected else "")


@pytest.mark.parametrize("text", [
    "\n" * 20000 + "雪❄️\\\"\t\nanswer" + "\n" * 30000,
    "a" + " " * 20000 + "z\t", "   " + "x" * 25000,
    " \n\t " * 20000, "first  \n" + "last" * 3000,
])
@pytest.mark.parametrize("size", [1, 17, 8191, 20000])
def test_digest_preserves_whitespace_and_preview_across_chunk_boundaries(text, size):
    digest = AnswerDigest()
    for offset in range(0, len(text), size):
        digest.append(text[offset : offset + size])
    digest.finish()
    expected = (text.strip(),) if text.strip() else ()
    assert digest.identity() == expected_identity(expected)
    assert digest.first_preview == (expected[0][:240] if expected else "")
