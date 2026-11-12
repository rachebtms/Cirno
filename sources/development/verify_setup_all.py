"""Exercise optional catalogue tools offline after `cirno-setup +all --verify`."""

import shutil
import subprocess
import tempfile
from pathlib import Path

from cirno_core.processes.environment import ExecutionEnvironment


def main() -> None:
    env = ExecutionEnvironment().build()
    env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    for command in ("sshpass", "youtube_transcript_api", "cairosvg", "marker", "marker_single", "manim"):
        assert shutil.which(command, path=env["PATH"]), f"Missing optional CLI: {command}"
    subprocess.run(["uv", "pip", "check", "--python", shutil.which("python", path=env["PATH"])],
                   env=env, check=True, timeout=120)
    for command in (["sshpass", "-V"], ["youtube_transcript_api", "--help"],
                    ["cairosvg", "--version"], ["marker_single", "--help"], ["manim", "--version"]):
        subprocess.run(command, env=env, check=True, timeout=120)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        probe = root / "optional.py"
        probe.write_text('''import httpx, markdown, cairosvg, marker, torch, youtube_transcript_api
from bs4 import BeautifulSoup
from manim import Circle, MathTex, Scene, Text, tempconfig
from pathlib import Path
import sys
root = Path(sys.argv[1])
assert BeautifulSoup("<p>Cirno</p>", "html.parser").p.text == "Cirno"
assert "<strong>Cirno</strong>" in markdown.markdown("**Cirno**")
with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="offline"))) as client:
    assert client.get("https://fixture.invalid").text == "offline"
image = cairosvg.svg2png(bytestring=b'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><rect width="16" height="16" fill="blue"/></svg>')
assert image.startswith(b"\\x89PNG")
class SetupScene(Scene):
    def construct(self):
        self.add(Circle(), Text("Cirno"), MathTex(r"x^2 + y^2 = 1"))
        self.wait(0.2)
with tempconfig({"quality": "low_quality", "media_dir": str(root / "media"), "disable_caching": True, "preview": False, "progress_bar": "none"}):
    SetupScene().render()
assert any(path.stat().st_size > 0 for path in root.rglob("*.mp4"))
print("OK optional HTTP/HTML/Markdown/SVG libraries, Marker/PyTorch import and Manim text/formula/video rendering")
''', encoding="utf-8")
        subprocess.run(["python", str(probe), str(root)], env=env, check=True, timeout=300)
    print("OK complete setup catalogue, dependency consistency and offline tool use", flush=True)


if __name__ == "__main__":
    main()
