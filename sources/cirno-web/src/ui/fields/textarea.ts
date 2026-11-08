/** Measure an editor without moving its containing transcript during the measurement. */
export function autosizeTextarea(
  input: HTMLTextAreaElement,
  maximumHeight = 260,
) {
  const container = input.parentElement!,
    previous = container.style.minHeight;
  container.style.minHeight = `${container.getBoundingClientRect().height}px`;
  try {
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, maximumHeight)}px`;
  } finally {
    container.style.minHeight = previous;
  }
}
