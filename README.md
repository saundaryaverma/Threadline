# Threadline

A ChatGPT-style chat app with a test and eval pipeline. The frontend is React with strict TypeScript, the backend is a Python Flask REST API, chats are saved in PostgreSQL, and replies stream in from the OpenAI API as they're generated.

Most AI apps are tested by someone trying a few prompts and deciding the answers look fine. Threadline treats model quality like any other part of the code: every push runs API tests against a real database, and an eval suite scores the model's answers and fails the build if quality drops.

![CI](https://github.com/saundaryaverma/Threadline/actions/workflows/ci.yml/badge.svg)

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

## Testing

There are two layers, and CI runs both on every push (`.github/workflows/ci.yml`).

### 1. API tests (pytest)

38 tests across the API, the eval checks, and the eval runner, with 94% line coverage. CI fails if coverage drops below 85%.

The API tests run against a real PostgreSQL database and replace only the OpenAI call with a fake, so they're fast, free, and still exercise real SQL. They cover:

- **Happy paths:** creating, listing, and deleting chats; streaming a reply; saving both messages in order; titling a chat from its first message.
- **Context handling:** the model receives the system prompt and the full history, and chats never leak into each other.
- **Validation:** empty, missing, and oversized messages, including the exact length limit on both sides.
- **Failures:** if the model call fails, the user sees a clear error and no empty reply is saved. If the connection drops mid-stream, the partial reply that the user already saw is saved, so history matches the screen.

```bash
docker compose exec db createdb -U chat threadline_test   # once
pip install -r requirements-dev.txt
pytest --cov
```

### 2. Model evals (`evals/`)

Unit tests can't tell you whether the model's answers are any good, so the eval suite sends real prompts to the model and scores the replies with deterministic checks (`contains_any`, `not_contains`, `regex`, `max_words`, and more in `evals/checks.py`).

The cases in `evals/cases.json` are grouped by what they protect:

| Tag | What it checks |
| --- | --- |
| accuracy | Correct facts and arithmetic |
| instruction-following | Answers in the format asked for |
| conversation | Uses information from earlier in the chat |
| honesty | Says "I don't know" when something can't be known, instead of making it up |
| safety | Resists prompt injection, including instructions hidden inside pasted text |

The eval suite uses the same system prompt as the app (`backend/prompt.py`), so it always tests what users actually get.

A run **fails** if:
- any case marked `critical` fails,
- any case that passed in the saved baseline now fails (a regression), or
- the overall pass rate drops below 90%.

That makes it a gate for prompt and model changes. Change the system prompt or switch models, and CI tells you exactly which behaviors got worse.

```bash
export OPENAI_API_KEY=sk-...
python -m evals.run_evals                     # run and compare against the baseline
python -m evals.run_evals --update-baseline   # accept this run as the new baseline
python -m evals.run_evals --tag safety        # run one group
```

Each run writes `evals/results/latest.md` (a readable report) and `latest.json`. In CI, the report appears on the run's summary page. To enable evals in CI, add `OPENAI_API_KEY` under the repo's Settings → Secrets and variables → Actions. Without it, the eval job skips itself and the rest of CI still runs.

## Next feature: flagged answers become test cases

Right now every eval case is written by hand. The plan is to let real usage write them:

1. Add a "Flag" button under each assistant reply in the UI.
2. Add `POST /api/messages/:id/flags`, which stores the flag with an optional note on what was wrong.
3. Add a script that turns flagged replies into draft cases in `evals/cases.json`, using the user's prompt and the earlier history, with a `not_contains` check against the bad answer and a placeholder for the check a person should fill in.

Over time the suite fills up with the failures real users hit, not the ones a developer imagined.

## Ideas to extend it

- Render Markdown and code blocks in replies
- Add a Stop button that cancels the stream (`AbortController` on the frontend)
- Let users rename chats
- Count tokens and trim old messages so long chats stay under the model's context limit
