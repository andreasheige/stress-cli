from stress.messages import Message, load_messages, merge_messages, to_events
from stress.models import Meeting

HOUR = 3600


def msg(ts, sender="a@x.com"):
    return Message(ts=ts, sender=sender, source="slack")


def mk_meeting(start, end, uid="m"):
    return Meeting(uid=uid, summary="mtg", start=start, end=end, attendees=frozenset({"x@x.com"}))


class TestToEvents:
    def test_single_message_becomes_window_event(self):
        events = to_events([msg(1000)], [], window_s=600)

        assert len(events) == 1
        assert (events[0].start, events[0].end) == (1000, 1600)
        assert events[0].attendees == frozenset({"a@x.com"})

    def test_burst_from_same_sender_merges_into_one_event(self):
        events = to_events([msg(1000), msg(1300), msg(1700)], [], window_s=600)

        assert len(events) == 1
        assert (events[0].start, events[0].end) == (1000, 2300)

    def test_separate_bursts_stay_separate(self):
        events = to_events([msg(1000), msg(5000)], [], window_s=600)

        assert [(e.start, e.end) for e in events] == [(1000, 1600), (5000, 5600)]

    def test_different_senders_get_separate_events(self):
        events = to_events([msg(1000, "a@x.com"), msg(1100, "b@x.com")], [], window_s=600)

        assert len(events) == 2

    def test_messages_during_meetings_are_dropped(self):
        meeting = mk_meeting(900, 2000)

        assert to_events([msg(1000)], [meeting], window_s=600) == []

    def test_event_window_is_clipped_at_next_meeting_start(self):
        meeting = mk_meeting(1300, 2000)

        events = to_events([msg(1000)], [meeting], window_s=600)

        assert (events[0].start, events[0].end) == (1000, 1300)


class TestMessageCache:
    def test_merge_dedupes_and_load_filters_window(self, tmp_path):
        import time

        now = time.time()
        old = now - 40 * 86400
        merge_messages(tmp_path, [msg(now - 60), msg(old)])
        merge_messages(tmp_path, [msg(now - 60)])  # duplicate

        recent = load_messages(tmp_path, days=30)
        assert len(recent) == 1
        assert len(load_messages(tmp_path, days=60)) == 2
