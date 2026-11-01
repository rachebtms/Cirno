from cirno.utils.helpers import sanitize_surrogates as _sanitize_surrogates


class TestSanitizeSurrogates:
    def test_lone_surrogates_replaced(self):
        result = _sanitize_surrogates("hello \udce9 world")
        assert "\udce9" not in result
        assert "hello" in result
        assert "world" in result

    def test_normal_text_unchanged(self):
        assert _sanitize_surrogates("normal ascii text") == "normal ascii text"

    def test_emoji_already_correct(self):
        """Properly encoded emoji should pass through unchanged."""
        assert _sanitize_surrogates("hello 🐈 cirno") == "hello 🐈 cirno"

    def test_mixed_unicode_preserved(self):
        assert _sanitize_surrogates("你好 hello こんにちは 🎉") == "你好 hello こんにちは 🎉"

    def test_multiple_lone_surrogates(self):
        result = _sanitize_surrogates("\udce9\udcf1\udcff")
        assert "\udce9" not in result
        assert "\udcf1" not in result
        assert "\udcff" not in result
