import { FitAddon } from "@xterm/addon-fit";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";

export function terminalPalette(host: HTMLElement) {
  const style = getComputedStyle(host);
  return { background: style.backgroundColor, foreground: style.color, cursor: style.caretColor,
    selectionBackground: style.color, selectionForeground: style.backgroundColor };
}
export function createTerminalRenderer(host: HTMLDivElement) {
  const terminal = new Terminal({ cursorBlink: true, disableStdin: true, fontSize: 13, scrollback: 3000,
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", theme: terminalPalette(host) });
  const fit = new FitAddon();
  terminal.loadAddon(fit);
  terminal.open(host);
  fit.fit();
  return { terminal, fit };
}
