# Threadline

A ChatGPT-style chat app. The frontend is React, the backend is a Python Flask REST API, chats are saved in PostgreSQL, and replies stream in from the OpenAI API as they're generated.

## How it works

```
React (Vite)  --->  Flask REST API  --->  OpenAI API
                         |
                     PostgreSQL
```

1. You type a message. If it's a new chat, the frontend first calls `POST /api/conversations` to create one.
2. The frontend sends the message to `POST /api/conversations/:id/messages`.
3. Flask saves your message, loads the whole conversation from PostgreSQL, and sends it to the OpenAI API with `stream=True`.
4. As the model writes, Flask passes each piece of text straight through to the browser. React reads the response body with a stream reader and appends each piece to the last message, so the reply appears word by word.
5. When the reply finishes, Flask saves it to PostgreSQL. The chat is named after its first message.

### API

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/conversations` | List chats, newest first |
| POST | `/api/conversations` | Create a chat |
| DELETE | `/api/conversations/:id` | Delete a chat and its messages |
| GET | `/api/conversations/:id/messages` | Get a chat's messages |
| POST | `/api/conversations/:id/messages` | Send a message, stream back the reply |

### Database

Two tables: `conversations` and `messages`. Each message belongs to a conversation (foreign key with `ON DELETE CASCADE`, so deleting a chat deletes its messages). There's an index on `(conversation_id, id)` because every chat load reads messages for one conversation in order. See `backend/schema.sql`.

## Run it locally

You need Python 3.10+, Node 18+, Docker (for PostgreSQL), and an OpenAI API key.

```bash
# 1. Start PostgreSQL
docker compose up -d

# 2. Start the backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...          # your key
export OPENAI_MODEL=gpt-4o-mini       # optional; use any current chat model
python app.py                          # runs on http://localhost:5000

# 3. Start the frontend (new terminal)
cd frontend
npm install
npm run dev                            # open http://localhost:5173
```

## Ideas to extend it

- Render Markdown and code blocks in replies
- Add a Stop button that cancels the stream (`AbortController` on the frontend)
- Let users rename chats
- Count tokens and trim old messages so long chats stay under the model's context limit
- Add tests for the API with `pytest` and Flask's test client
