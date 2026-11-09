# Memory retrieval

The agent's `memory.search` tool and Settings → Memory retrieval use the same search pipeline. BM25 is available by default. Semantic and hybrid modes are optional and index active knowledge and profiles; original evidence and task-state searches remain lexical. Empty queries browse records without starting inference or making an embedding API call.

Original evidence pages contain at most twenty lines and 16,000 characters in total. Long individual lines continue through a character offset rather than loading the entire line into context. Follow the returned line and character cursors to read further; memory-body pointers use the same page budget. Reads retain their resolved source revision, and immutable-body hash mismatches are reported explicitly.

## Local CPU embeddings

Enable Semantic retrieval and choose Local CPU model. Select an ONNX model and matching tokenizer. The full image supplies matching BGE weights; inference remains disabled until enabled. Local inference runs in a disposable CPU worker, with a configurable RSS limit and timeout. The main service does not keep the model loaded. Long records use overlapping token chunks, indexed incrementally and stored in `vectors.sqlite3`.

## External embedding API

Choose External API and enter an OpenAI-compatible API base URL, model and optional API key. For example, `https://embedding.example/v1` sends requests to `https://embedding.example/v1/embeddings`. A complete `/embeddings` endpoint is also accepted. Local HTTP services are supported; URLs must not contain credentials or secret query parameters. The API key is stored in the instance configuration and masked in settings responses. It can be replaced or cleared without revealing the existing value.

The service must accept `model`, an array of input strings and `encoding_format: "float"`, then return an indexed `data` array of finite numeric embedding vectors. See the [embedding API format](https://developers.openai.com/api/reference/resources/embeddings/methods/create). Output order is normalized by index. Vectors are normalized before cosine similarity; dimensions must stay consistent within a search.

API mode sends the query and selected memory chunks to that service. It loads no local embedding model. Adjust the character chunk size for the model's input limit; chunks overlap by 25%. Each search indexes at most 32 chunks in batches of at most eight, and later searches resume unfinished indexing. Endpoint, model, chunk size and vector dimensions identify the index, so incompatible vectors are never mixed. Index identity excludes the secret key; rotating credentials does not rebuild the same model's index.

Both modes use the same scope filters, disk vector storage, bounded ranking and BM25/vector fusion. API errors, timeouts and malformed vectors produce a visible warning and fall back to BM25. Requests do not silently follow redirects with credentials. There is no default API endpoint, automatic model download or background per-reply embedding call.
