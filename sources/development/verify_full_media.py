"""Render small offline artifacts with the full image's Agent Python environment."""

from pathlib import Path
import subprocess
import tempfile


def main() -> None:
    from docx import Document
    from openpyxl import Workbook, load_workbook
    from pptx import Presentation
    from playwright.sync_api import sync_playwright
    from manim import DOWN, MathTex, Scene, Text, tempconfig
    import pymupdf

    fonts = subprocess.run(["fc-list", ":lang=zh", "family"], check=True, capture_output=True, text=True)
    assert "Noto" in fonts.stdout, "CJK fonts are missing"
    with tempfile.TemporaryDirectory(prefix="cirno-media-smoke-") as temporary:
        root = Path(temporary)
        document = Document()
        document.add_paragraph("Cirno 中文报告")
        document.save(root / "report.docx")
        slides = Presentation()
        slides.slides.add_slide(slides.slide_layouts[0]).shapes.title.text = "Cirno 中文幻灯片"
        slides.save(root / "slides.pptx")
        workbook = Workbook()
        workbook.active["A1"] = "=1+2"
        workbook.save(root / "formula.xlsx")
        profile = f"-env:UserInstallation={(root / 'office-profile').as_uri()}"
        for files, format_, destination in ((["report.docx", "slides.pptx"], "pdf", "pdf"),
                                            (["formula.xlsx"], "xlsx", "recalculated")):
            subprocess.run(["soffice", profile, "--headless", "--convert-to", format_,
                            "--outdir", str(root / destination), *[str(root / name) for name in files]],
                           check=True, timeout=120)
        for name in ("report", "slides"):
            with pymupdf.open(root / "pdf" / f"{name}.pdf") as rendered:
                assert len(rendered) >= 1
        calculated = load_workbook(root / "recalculated/formula.xlsx", data_only=True)
        assert calculated.active["A1"].value == 3
        calculated.close()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 640, "height": 360})
                page.set_content('<meta charset="utf-8"><p style="font-family: Noto Sans CJK SC">Cirno 中文渲染检查</p>')
                page.evaluate("document.fonts.ready")
                assert page.screenshot(path=str(root / "chromium.png"))
            finally:
                browser.close()
        with tempconfig({"media_dir": str(root / "manim"), "pixel_width": 320, "pixel_height": 160,
                         "frame_rate": 5, "disable_caching": True, "progress_bar": "none"}):
            class Probe(Scene):
                def construct(self):
                    self.add(Text("Cirno"), MathTex("x^2").shift(DOWN))
                    self.wait(0.2)
            Probe().render()
        assert any((root / "manim").rglob("*.mp4")), "Manim did not produce a video"
    print("OK LibreOffice conversion/recalculation, CJK fonts, Chromium screenshot and Manim/LaTeX video", flush=True)


if __name__ == "__main__":
    main()
