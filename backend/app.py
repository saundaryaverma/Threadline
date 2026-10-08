"""Threadline backend: a small Flask REST API that stores chats in PostgreSQL
and streams replies from the OpenAI API."""
import os
from pathlib import Path

import psycopg
from flask import Flask, Response, jsonify, request, stream_with_context
from openai import OpenAI
from psycopg.rows import dict_row

from prompt import build_messages

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://chat:chat@localhost:5432/threadline")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
MAX_MESSAGE_CHARS = 8000

app = Flask(__name__)
client = OpenAI()  # reads OPENAI_API_KEY from the environment


def db():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db():
    schema = (Path(__file__).parent / "schema.sql").read_text()
    with db() as conn:
        conn.execute(schema)


def conversation_exists(conn, conversation_id):
    row = conn.execute("SELECT 1 FROM conversations WHERE id = %s", (conversation_id,)).fetchone()
    return row is not None


@app.get("/api/conversations")
def list_conversations():
    with db() as conn:
        rows = conn.execute(
            "SELECT id, title, created_at FROM conversations ORDER BY created_at DESC"
        ).fetchall()
    return jsonify(rows)


@app.post("/api/conversations")
def create_conversation():
    with db() as conn:
        row = conn.execute(
            "INSERT INTO conversations DEFAULT VALUES RETURNING id, title, created_at"
        ).fetchone()
    return jsonify(row), 201


@app.delete("/api/conversations/<int:conversation_id>")
def delete_conversation(conversation_id):
    with db() as conn:
        deleted = conn.execute(
            "DELETE FROM conversations WHERE id = %s RETURNING id", (conversation_id,)
        ).fetchone()
    if deleted is None:
        return jsonify(error="Conversation not found"), 404
    return "", 204


@app.get("/api/conversations/<int:conversation_id>/messages")
def list_messages(conversation_id):
    with db() as conn:
        if not conversation_exists(conn, conversation_id):
            return jsonify(error="Conversation not found"), 404
        rows = conn.execute(
            "SELECT id, role, content, created_at FROM messages "
            "WHERE conversation_id = %s ORDER BY id",
            (conversation_id,),
        ).fetchall()
    return jsonify(rows)


@app.post("/api/conversations/<int:conversation_id>/messages")
def send_message(conversation_id):
    content = (request.get_json(silent=True) or {}).get("content", "").strip()
    if not content:
        return jsonify(error="Message can't be empty"), 400
    if len(content) > MAX_MESSAGE_CHARS:
        return jsonify(error=f"Message is longer than {MAX_MESSAGE_CHARS} characters"), 400

    with db() as conn:
        if not conversation_exists(conn, conversation_id):
            return jsonify(error="Conversation not found"), 404
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES (%s, 'user', %s)",
            (conversation_id, content),
        )
        # Name the chat after its first message.
        conn.execute(
            "UPDATE conversations SET title = %s WHERE id = %s AND title = 'New chat'",
            (content[:60], conversation_id),
        )
        history = conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id = %s ORDER BY id",
            (conversation_id,),
        ).fetchall()

    messages = build_messages(history)

    def generate():
        parts = []
        try:
            stream = client.chat.completions.create(model=MODEL, messages=messages, stream=True)
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    parts.append(text)
                    yield text
        except Exception:
            app.logger.exception("OpenAI request failed")
            yield "\n\n[The model didn't respond. Check the server log and your API key.]"
        finally:
            # Save whatever arrived so the history matches what the user saw.
            if parts:
                with db() as conn:
                    conn.execute(
                        "INSERT INTO messages (conversation_id, role, content) "
                        "VALUES (%s, 'assistant', %s)",
                        (conversation_id, "".join(parts)),
                    )

    return Response(stream_with_context(generate()), mimetype="text/plain")


if __name__ == "__main__":
    init_db()
    app.run(port=5000, debug=True)
