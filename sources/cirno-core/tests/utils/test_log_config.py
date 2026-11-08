from io import StringIO

from loguru import logger

from cirno_core.utils.log_config import add_console_log_sink


def test_console_log_sink_includes_context_and_escapes_message_newlines() -> None:
    output = StringIO()
    sink = add_console_log_sink(output, level="DEBUG")
    try:
        with logger.contextualize(
            request_id="request-1",
            turn_id="turn-1",
            session_key="channel:chat",
        ):
            logger.bind(channel="test").info("first line\nsecond line")
    finally:
        logger.remove(sink)

    rendered = output.getvalue()
    assert "request=request-1 turn=turn-1 session=channel:chat" in rendered
    assert "first line\\nsecond line" in rendered
    assert "first line\nsecond line" not in rendered


def test_console_log_sink_keeps_exception_traceback_multiline() -> None:
    output = StringIO()
    sink = add_console_log_sink(output)
    try:
        try:
            raise RuntimeError("broken")
        except RuntimeError:
            logger.opt(exception=True).error("operation failed")
    finally:
        logger.remove(sink)

    rendered = output.getvalue()
    assert "operation failed" in rendered
    assert "RuntimeError: broken" in rendered


def test_exception_diagnostics_do_not_dump_configuration_credentials() -> None:
    output = StringIO()
    sink = add_console_log_sink(output)
    configuration = {"api_key": "test-only-credential-9c638"}

    def connect(settings):
        raise RuntimeError("Connection failed")

    try:
        try:
            connect(configuration)
        except RuntimeError:
            logger.exception("Provider connection failed")
    finally:
        logger.remove(sink)

    rendered = output.getvalue()
    assert "test-only-credential-9c638" not in rendered
    assert "connect" in rendered
    assert "RuntimeError: Connection failed" in rendered
