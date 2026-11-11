"""Render small offline artifacts with the full image's Agent Python environment."""

import os
import subprocess
import tempfile
from pathlib import Path


def check_latex(root: Path) -> None:
    """Exercise CVPR-style packages and common scientific-paper extensions offline."""
    (root / "paper.tex").write_text(r"""\documentclass[10pt,twocolumn,letterpaper]{article}
\usepackage{times,xspace,graphicx,amsmath,amssymb,booktabs}
\usepackage[dvipsnames]{xcolor}
\usepackage[numbers,sort&compress]{natbib}
\usepackage{silence,etoolbox,caption,subcaption,microtype}
\usepackage{algorithm,algpseudocode}
\usepackage[colorlinks]{hyperref}
\usepackage[capitalize]{cleveref}
\title{Cirno paper compilation check}
\author{Offline fixture}
\begin{document}
\maketitle
\section{Scientific content}
Equation $\mathbb{E}[x^2] = \sum_{i=1}^{n} x_i^2/n$ and a reference~\cite{fixture}.
\begin{figure}[t]
\centering
\begin{subfigure}{.45\linewidth}\centering\rule{1cm}{1cm}\caption{Input}\end{subfigure}
\begin{subfigure}{.45\linewidth}\centering\rule{1cm}{1cm}\caption{Output}\end{subfigure}
\caption{An offline figure.}\label{fig:fixture}
\end{figure}
\begin{algorithm}[t]
\caption{Compilation check}
\begin{algorithmic}[1]\State $x\gets 1$\State \Return $x$\end{algorithmic}
\end{algorithm}
\begin{tabular}{lr}\toprule Method & Score\\\midrule Fixture & 1\\\bottomrule\end{tabular}
See \cref{fig:fixture}.
\bibliographystyle{plainnat}
\bibliography{references}
\end{document}
""", encoding="utf-8")
    (root / "references.bib").write_text(
        "@misc{fixture, author={Cirno Test}, title={Offline bibliography fixture}, year={2026}}\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", "paper.tex"],
        cwd=root, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (root / "paper.pdf").stat().st_size > 0
    assert "Offline bibliography fixture" in (root / "paper.bbl").read_text(encoding="utf-8")


def main() -> None:
    import playwright
    import pymupdf
    from docx import Document
    from openpyxl import Workbook, load_workbook
    from playwright.sync_api import sync_playwright
    from pptx import Presentation

    assert (Path(playwright.__file__).parent / "driver" / "node").is_file()
    assert list(Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"]).glob("chromium_headless_shell-*"))
    assert not list(Path("/home/linuxbrew/.linuxbrew/Cellar").glob("python@*/*/lib/python3.*/test"))
    fonts = subprocess.run(["fc-list", ":lang=zh", "family"], check=True, capture_output=True, text=True)
    assert "Noto" in fonts.stdout, "CJK fonts are missing"
    with tempfile.TemporaryDirectory(prefix="cirno-media-smoke-") as temporary:
        root = Path(temporary)
        (root / "test_python_tools.py").write_text(
            "from pathlib import Path\n"
            "import unittest, subprocess, sys\n"
            "class TestPythonTools(unittest.TestCase):\n"
            "    def test_environment(self):\n"
            "        subprocess.run(['uv', 'venv', '--python', sys.executable, 'test-venv'], check=True)\n"
            "        self.assertTrue(Path('test-venv/bin/python').is_file())\n",
            encoding="utf-8",
        )
        subprocess.run(["pytest", "-q", "test_python_tools.py"], cwd=root, check=True, timeout=90)
        (root / "filter.lua").write_text(
            "function Str(element) return pandoc.Str(string.upper(element.text)) end\n",
            encoding="utf-8",
        )
        converted = subprocess.run(
            ["pandoc", "-f", "markdown", "-t", "html", "--lua-filter", str(root / "filter.lua")],
            input="# Cirno\n", capture_output=True, text=True, check=True, timeout=30,
        )
        assert ">CIRNO</h1>" in converted.stdout, converted.stdout
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
        check_latex(root)
    print("OK pytest/venv, Pandoc/Lua, LibreOffice conversion/recalculation, CJK fonts, standard Playwright/Chromium screenshot and scientific LaTeX/BibTeX compilation", flush=True)


if __name__ == "__main__":
    main()
