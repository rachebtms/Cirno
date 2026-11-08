/** Files contracts shared by the browser and its transports. */

export interface FileReferenceMetadata {
  path: string;
  relative_path: string | null;
}

export interface FilePreviewMetadata {
  path: string;
  display_path: string;
  project_path: string;
  size: number;
}

export type FilePreviewPayload = FilePreviewMetadata &
  (
    | { kind?: "text"; language: string; content: string; truncated: boolean }
    | { kind: "image"; mime_type: string; data_url: string }
    | { kind: "video"; mime_type: string; url: string }
  );
