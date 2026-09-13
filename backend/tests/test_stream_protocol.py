from app.services.stream_protocol import StreamLedger, TerminalState, classify_non_stream


def test_does_not_default_to_stop():
    ledger = StreamLedger()
    assert ledger.finish_reason is None
    assert ledger.classify() is TerminalState.UNKNOWN_TERMINAL
    assert ledger.message_status() == "error"
    assert ledger.stored_finish_reason() == "unknown_terminal"
    assert ledger.incomplete() is True


def test_stop_requires_finish_and_done():
    ledger = StreamLedger()
    ledger.observe_finish("stop")
    assert ledger.classify() is TerminalState.UNKNOWN_TERMINAL
    ledger.observe_done_wire()
    assert ledger.classify() is TerminalState.COMPLETED_STOP
    assert ledger.message_status() == "complete"
    assert ledger.incomplete() is False


def test_length_is_complete_but_distinct():
    ledger = StreamLedger()
    ledger.observe_finish("length")
    ledger.observe_done_wire()
    assert ledger.classify() is TerminalState.COMPLETED_LENGTH
    assert ledger.message_status() == "complete"
    assert ledger.stored_finish_reason() == "length"


def test_eof_before_done_is_transport_interrupt():
    ledger = StreamLedger(http_eof=True, had_output=True)
    ledger.observe_finish("stop")
    assert ledger.classify() is TerminalState.INTERRUPTED_TRANSPORT
    assert ledger.message_status() == "error"
    assert ledger.stored_finish_reason() == "interrupted_transport"


def test_done_without_finish_is_protocol_error():
    ledger = StreamLedger()
    ledger.observe_done_wire()
    assert ledger.classify() is TerminalState.UPSTREAM_PROTOCOL_ERROR


def test_http_eof_without_signals_is_transport_interrupt():
    ledger = StreamLedger(http_eof=True, had_output=True)
    assert ledger.classify() is TerminalState.INTERRUPTED_TRANSPORT


def test_malformed_frames_without_terminal_are_protocol_error():
    ledger = StreamLedger(malformed_frames=3, http_eof=True)
    assert ledger.classify() is TerminalState.UPSTREAM_PROTOCOL_ERROR


def test_user_cancel_wins():
    ledger = StreamLedger(cancelled=True, http_eof=True)
    ledger.observe_finish("stop")
    assert ledger.classify() is TerminalState.INTERRUPTED_USER
    assert ledger.message_status() == "cancelled"
    assert ledger.stored_finish_reason() == "abort"


def test_timeout_and_generation_error():
    assert StreamLedger(exception=TimeoutError("mlx timeout")).classify() is TerminalState.TIMEOUT
    assert StreamLedger(exception=RuntimeError("boom")).classify() is TerminalState.GENERATION_ERROR
    assert StreamLedger(exception=ConnectionError("eof")).classify() is TerminalState.INTERRUPTED_TRANSPORT


def test_repetition_guard():
    ledger = StreamLedger(repetition_guard=True)
    ledger.observe_finish("stop")
    ledger.observe_done_wire()
    assert ledger.classify() is TerminalState.REPETITION_GUARD


def test_non_stream_missing_finish_is_unknown():
    assert classify_non_stream(finish_reason=None) is TerminalState.UPSTREAM_PROTOCOL_ERROR
    assert classify_non_stream(finish_reason="stop") is TerminalState.COMPLETED_STOP
    assert classify_non_stream(finish_reason="length") is TerminalState.COMPLETED_LENGTH
