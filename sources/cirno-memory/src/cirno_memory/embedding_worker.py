"""Optional BGE-small CPU worker. Executed as a script, never imported by the gateway."""
import json
import resource
import sys
import time


def peak_mb():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1048576 if sys.platform == "darwin" else 1024)


def main():
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer

    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.enable_cpu_mem_arena = False
    options.enable_mem_pattern = False
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
    session = ort.InferenceSession(sys.argv[1], sess_options=options, providers=["CPUExecutionProvider"])
    tokenizer = Tokenizer.from_file(sys.argv[2])
    tokenizer.enable_truncation(max_length=256)
    inputs = {item.name for item in session.get_inputs()}
    for line in sys.stdin:
        started = time.perf_counter()
        request = json.loads(line)
        vectors, chunks = [], []
        has_more = False
        items = []
        if request.get("chunked"):
            tokenizer.no_truncation()
            encoded = tokenizer.encode(request["texts"][0], add_special_tokens=False)
            starts = range(0, len(encoded.ids), 192)
            first = max(0, int(request.get("start_chunk", 0)))
            cap = min(8, max(1, int(request.get("max_chunks", 8))))
            chosen = list(starts[first:first + cap])
            has_more = first + len(chosen) < len(starts)
            for index, start in enumerate(chosen, first):
                end = min(start + 224, len(encoded.ids))
                # Keep the original token IDs: decoding and re-encoding can lose
                # boundary characters or change byte-level tokenization.
                # The model is BERT/BGE: CLS/SEP wrap the exact slice.
                cls_id = tokenizer.token_to_id("[CLS]")
                sep_id = tokenizer.token_to_id("[SEP]")
                if cls_id is None or sep_id is None:
                    raise ValueError("Choose a BGE BERT tokenizer with CLS/SEP tokens")
                token_ids = [cls_id, *encoded.ids[start:end], sep_id]
                items.append((token_ids, [1] * len(token_ids), [0] * len(token_ids)))
                chunks.append({"chunk_index": index, "start_char": encoded.offsets[start][0], "end_char": encoded.offsets[end - 1][1]})
            tokenizer.enable_truncation(max_length=256)
        else:
            for text in request["texts"]:
                encoded = tokenizer.encode(text)
                items.append((encoded.ids, encoded.attention_mask, encoded.type_ids))
        for ids, attention, types in items:
            values = {"input_ids": np.array([ids], dtype=np.int64),
                      "attention_mask": np.array([attention], dtype=np.int64),
                      "token_type_ids": np.array([types], dtype=np.int64)}
            output = session.run(None, {key: value for key, value in values.items() if key in inputs})[0]
            # BGE v1.5 uses normalized CLS embeddings, not mean pooling.
            vector = output[0, 0] if output.ndim == 3 else output[0]
            vector = vector / max(float(np.linalg.norm(vector)), 1e-12)
            vectors.append(vector.tolist())
        print(json.dumps({"vectors": vectors, "chunks": chunks, "has_more": has_more, "peak_mb": peak_mb(), "seconds": time.perf_counter() - started}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc), "peak_mb": peak_mb()}), flush=True)
        sys.exit(1)
