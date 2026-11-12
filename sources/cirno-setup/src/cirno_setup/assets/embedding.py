"""Bundle the matching, revision-pinned BGE-small INT8 model and tokenizer."""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

MODEL_REPOSITORY = "Xenova/bge-small-zh-v1.5"
MODEL_REVISION = "75c43b069aac4d136ba6bc1122f995fedcfd2781"
MODEL_FILES = {
    "onnx/model_quantized.onnx": "15b717c382bcb518ba457b93ea6850ede7f4f1cd8937454aa06972366cd19bcc",
    "tokenizer.json": "48cea5d44424912a6fd1ea647bf4fe50b55ab8b1e5879c3275f80e339e8fae26",
    "README.md": "cb22054df1a98f7ee9d5b281d023e67c27cc316e1733baf03fc994d95c3048ab",
}


def downloads() -> list[tuple[str, str, str]]:
    return [
        (name, f"https://huggingface.co/{MODEL_REPOSITORY}/resolve/{MODEL_REVISION}/{name}", expected)
        for name, expected in MODEL_FILES.items()
    ] + [(
        "LICENSE",
        "https://raw.githubusercontent.com/FlagOpen/FlagEmbedding/897baa67c0ffddbfccf4e6776ff55310d67809d4/LICENSE",
        "587a673933425dbc36ec61268d3b954051b2d3ef3c9b322ede357976055ffdd5",
    )]


def main(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name, url, expected in downloads():
        path = destination / Path(name).name
        if path.is_file():
            with path.open("rb") as handle:
                if hashlib.file_digest(handle, "sha256").hexdigest() == expected:
                    continue
        subprocess.run([
            "curl", "--fail", "--location", "--retry", "5", "--retry-all-errors",
            "--output", str(path), url,
        ], check=True)
        with path.open("rb") as handle:
            actual = hashlib.file_digest(handle, "sha256").hexdigest()
        if actual != expected:
            raise ValueError(f"Checksum mismatch for {name}: {actual}")
    print(f"Bundled {MODEL_REPOSITORY}@{MODEL_REVISION}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
