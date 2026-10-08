"""Tests for the Threadline REST API. The OpenAI call is faked; PostgreSQL is real."""
import app as threadline


def new_chat(client):
    res = client.post("/api/conversations")
    assert res.status_code == 201
    return res.get_json()["id"]


def send(client, chat_id, content):
    return client.post(f"/api/conversations/{chat_id}/messages", json={"content": content})


# Conversations

def test_new_conversation_has_default_title(client):
    res = client.post("/api/conversations")
    assert res.status_code == 201
    assert res.get_json()["title"] == "New chat"


def test_list_conversations_newest_first(client):
    first = new_chat(client)
    second = new_chat(client)
    ids = [c["id"] for c in client.get("/api/conversations").get_json()]
    assert ids == [second, first]


def test_delete_conversation_removes_its_messages(client, fake_model):
    chat_id = new_chat(client)
    send(client, chat_id, "Hi")
    assert client.delete(f"/api/conversations/{chat_id}").status_code == 204
    with threadline.db() as conn:
        count = conn.execute("SELECT count(*) AS n FROM messages").fetchone()["n"]
    assert count == 0


def test_delete_missing_conversation_returns_404(client):
    assert client.delete("/api/conversations/999").status_code == 404


# Sending messages

def test_reply_streams_back_in_full(client, fake_model):
    chat_id = new_chat(client)
    res = send(client, chat_id, "Hi")
    assert res.status_code == 200
    assert res.get_data(as_text=True) == "Hello there!"


def test_both_messages_are_saved_in_order(client, fake_model):
    chat_id = new_chat(client)
    send(client, chat_id, "Hi").get_data()
    messages = client.get(f"/api/conversations/{chat_id}/messages").get_json()
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "Hi"),
        ("assistant", "Hello there!"),
    ]


def test_first_message_becomes_the_title(client, fake_model):
    chat_id = new_chat(client)
    send(client, chat_id, "Plan a trip to Lisbon").get_data()
    send(client, chat_id, "Make it three days").get_data()
    title = client.get("/api/conversations").get_json()[0]["title"]
    assert title == "Plan a trip to Lisbon"


def test_long_first_message_title_is_truncated(client, fake_model):
    chat_id = new_chat(client)
    send(client, chat_id, "x" * 200).get_data()
    assert len(client.get("/api/conversations").get_json()[0]["title"]) == 60


def test_model_receives_system_prompt_and_full_history(client, fake_model):
    chat_id = new_chat(client)
    send(client, chat_id, "My name is Priya").get_data()
    send(client, chat_id, "What's my name?").get_data()
    sent = fake_model.calls[-1]["messages"]
    assert sent[0]["role"] == "system"
    assert [m["content"] for m in sent[1:]] == ["My name is Priya", "Hello there!", "What's my name?"]
    assert fake_model.calls[-1]["stream"] is True


def test_conversations_do_not_share_history(client, fake_model):
    a, b = new_chat(client), new_chat(client)
    send(client, a, "secret in chat A").get_data()
    send(client, b, "hello from chat B").get_data()
    sent = [m["content"] for m in fake_model.calls[-1]["messages"][1:]]
    assert "secret in chat A" not in sent


# Validation

def test_empty_message_is_rejected(client, fake_model):
    chat_id = new_chat(client)
    res = send(client, chat_id, "   ")
    assert res.status_code == 400
    assert fake_model.calls == []


def test_missing_body_is_rejected(client):
    chat_id = new_chat(client)
    res = client.post(f"/api/conversations/{chat_id}/messages", data="not json")
    assert res.status_code == 400


def test_message_over_limit_is_rejected(client, fake_model):
    chat_id = new_chat(client)
    res = send(client, chat_id, "x" * (threadline.MAX_MESSAGE_CHARS + 1))
    assert res.status_code == 400


def test_message_at_limit_is_accepted(client, fake_model):
    chat_id = new_chat(client)
    res = send(client, chat_id, "x" * threadline.MAX_MESSAGE_CHARS)
    assert res.status_code == 200


def test_message_to_missing_conversation_returns_404(client, fake_model):
    assert send(client, 999, "Hi").status_code == 404
    assert client.get("/api/conversations/999/messages").status_code == 404


# Failures

def test_model_error_shows_message_and_saves_no_reply(client, fake_model):
    fake_model.error = RuntimeError("API down")
    chat_id = new_chat(client)
    body = send(client, chat_id, "Hi").get_data(as_text=True)
    assert "didn't respond" in body
    roles = [m["role"] for m in client.get(f"/api/conversations/{chat_id}/messages").get_json()]
    assert roles == ["user"]


def test_error_mid_stream_saves_the_partial_reply(client, fake_model):
    fake_model.reply = ["Part one.", " Part two."]
    fake_model.error = RuntimeError("connection dropped")
    fake_model.error_after = 1
    chat_id = new_chat(client)
    send(client, chat_id, "Hi").get_data()
    messages = client.get(f"/api/conversations/{chat_id}/messages").get_json()
    assert messages[-1] == {**messages[-1], "role": "assistant", "content": "Part one."}
