from cubo.activity import ActivityLog
from cubo.voice.events import Heard, Replied, State, StateChanged


def test_keeps_the_conversation_in_order():
    log = ActivityLog()

    log.record(Heard("liga a luz"))
    log.record(Replied("Pronto."))

    assert [(entry.author, entry.text) for entry in log.entries()] == [
        ("you", "liga a luz"),
        ("cubo", "Pronto."),
    ]


def test_follows_the_current_state():
    log = ActivityLog()
    assert log.state is State.WAITING

    log.record(StateChanged(State.THINKING))

    assert log.state is State.THINKING


def test_empty_replies_are_not_listed():
    log = ActivityLog()

    log.record(Replied(""))

    assert log.entries() == []


def test_forgets_the_oldest_entries():
    log = ActivityLog(max_entries=2)

    for text in ("um", "dois", "três"):
        log.record(Heard(text))

    assert [entry.text for entry in log.entries()] == ["dois", "três"]
