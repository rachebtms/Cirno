import type { EvidenceCursor, EvidencePage } from "@/lib/contracts/memory";
export function nextEvidenceCursor(page: EvidencePage): EvidenceCursor | null {
  const last = page.lines?.at(-1);
  if (last?.next_char_offset != null)
    return {
      id: page.memory_id,
      revision: page.revision,
      start_line: last.line,
      char_offset: last.next_char_offset,
    };
  return page.next_line == null
    ? null
    : { id: page.memory_id, revision: page.revision, start_line: page.next_line, char_offset: 0 };
}
