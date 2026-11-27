# F-1 Compass

F-1 Compass is an account-free Streamlit reference desk for University of Maryland, College Park students exploring CPT, on-campus employment, and unpaid work. Answers include excerpts and links from indexed UMD ISSS pages.

The app uses Gemini embeddings and BM42 in Qdrant, reranks hybrid candidates with FlashRank, and sends the top four passages to Gemini. Follow-up questions use conversation-aware query rewriting.

## Run locally

Use Python 3.11. Install dependencies, configure a local environment, then start Streamlit.

```sh
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Set `GEMINI_API_KEY`, `QDRANT_URL`, and `QDRANT_API_KEY` (for authenticated Qdrant) in the runtime environment or an untracked local `.env`. Point the app at a Qdrant instance with the project corpus indexed. To populate a new instance, run `python -m scripts.index_source SOURCE_ID` for each entry in `sources.json` using the saved snapshots.

## Deploy

Use a single container with a persistent volume for `/app/data/cache` so the public question list and reusable answers survive restarts. Provide credentials through the host's runtime secret settings. The app needs outbound access to Gemini, Qdrant, and model download hosts on first startup.

```sh
docker build -t f1-compass .
docker run --rm -p 8501:8501 --env-file .env -v f1-compass-cache:/app/data/cache f1-compass
```

Keep `F1_COMPASS_ENABLE_INGESTION` unset on the public instance. Before sharing the URL, try one question with each of the three UMD sources. Open the citation cards and check that a question explicitly shared from a fresh conversation appears in the sidebar. Restart the container and verify the shared question still appears.

## Shared answers without accounts

The application does not require a visitor account. General first-turn
questions can reuse an answer saved by an earlier visitor. This is an exact
match after lowercasing and whitespace normalization; punctuation, numbers,
negation, and location words remain significant. Paraphrases do not match yet.
Follow-ups still use conversation-aware query rewriting and the existing
hybrid retrieval, FlashRank, and Gemini generation pipeline.

The SQLite cache lives at `data/cache/answers.sqlite3` and is excluded from
Git. It stores eligible questions, successful answers, and their ordered
source cards for up to 24 hours. The sidebar lists up to 50 recently shared
questions from a separate table in the same database. Visitors can opt in
when asking a general first-turn question. The public list retains only the
question text and recency, independently of answer expiry and reindexing.
Older cached questions stay private. Expired answers are deleted during cache
reads/writes. Only results with valid citation IDs and passages matching
current locally registered source snapshots are cached. Citation-ID validity
does not prove factual support; cached answers inherit generation limitations.

Questions that appear personal, contain obvious identifiers, or have chat
history are skipped. This filter is conservative, not a reliable detector of
all personal information. Visitors can uncheck **Reuse and save answers for
general questions** to bypass both lookup and storage. Abstentions, invalid
citations, API errors, and passages from unregistered uploads are not cached.
Storage errors fall back to the original answer pipeline.

Cache entries are invalidated by indexing through `upload_chunks`, snapshot
metadata changes, endpoint changes, and changes to the cache/retrieval/
generation code. Direct Qdrant edits outside this application are not tracked:
clear the local cache while the app is stopped after external corpus changes.
If indexing crashes mid-update, reuse stays disabled until an operator checks
the corpus and repairs the cache state while the app is stopped. Removing
the entire database would also remove the public question list. The
source-version labels do not implement retirement of old Qdrant points.

Uploads are hidden by default. Set `F1_COMPASS_ENABLE_INGESTION=true` only in
a trusted local/operator instance, or use `python -m scripts.index_source`.
This setting is not authentication; do not enable it on an anonymous public
instance. This change does not deploy the app or configure hosting access.

SQLite is shared by visitors to a single server with the same disk, not by
independent replicas. Hosting must preserve `data/cache/` across restarts for
durable reuse. Keep the database private; never serve it as a download.

Offline checks: `python -B -m unittest discover -s tests -v`.

### Live evaluation

Run these suites sequentially from the project root. They use the configured
Gemini account and pause 30 seconds between cases. Set
`F1_EVAL_PAUSE_SECONDS` to a longer interval for a lower quota.

```sh
python -m scripts.compare_rankings
python -m scripts.evaluate_held_out
python -m scripts.evaluate_generation
python -m scripts.evaluate_end_to_end
```

The first two use the original CPT point labels, including the previously
inspected held-out cases. Generation uses supplied evidence. End-to-end
cases retrieve live evidence, including one question for each additional
UMD source. Each script saves a separate report under `evaluation/runs/`.

## F-1 Compass interface

The registry includes UMD ISSS pages for CPT, on-campus employment and unpaid work.
The Streamlit interface uses a light reference-desk palette, CPT starter
questions, and numbered source cards. Retrieval and source-update dates
remain separate; missing dates remain Unknown. Public uploads stay hidden
unless the existing trusted-operator setting is enabled.

Run `python -B tests/check_ui.py` in the project environment for the real
Streamlit UI smoke check with mocked services. To preview the design without
live API calls, run `streamlit run tests/ui_preview.py --server.port 8502`.
The preview uses one recorded development answer and is not a deployment
entry point. The normal entry point remains `streamlit run app.py`.

### Retrieval results

With hybrid retrieval and FlashRank, a labeled supporting passage ranked
first for 4 of 6 CPT development questions and appeared in the top five
for 5 of 6. At the production cutoff of four passages, all labeled evidence
groups were retrieved for 3 of 4 previously inspected CPT questions.
These counts describe the labeled cases and their indexed corpus.
See [evaluation notes](evaluation/notes.md) for run IDs and limitations.
