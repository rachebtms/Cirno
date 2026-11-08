/** Bootstrap contracts shared by the browser and its transports. */

import type { PreferencesSnapshot } from "@/features/preferences/contracts";

export interface BootstrapResponse {
  preferences?: PreferencesSnapshot;
  browser_auth?: boolean;
  onboarding_required?: boolean;
  terminal?: {
    webui?: { capabilities?: string[] };
  };
  token?: string;
  api_token?: string;
  ws_path: string;
  ws_url?: string | null;
  expires_in?: number;
  limits?: WebUIIngressLimits;
  model_name?: string | null;
}

export interface WebUITransportLimits {
  max_frame_bytes: number;
  envelope_reserve_bytes: number;
}

export interface WebUIMessageLimits {
  max_text_bytes: number;
}

export interface WebUIAttachmentLimits {
  max_count: number;
  max_file_bytes: number;
  max_video_bytes: number;
  max_total_bytes: number;
}

export interface WebUIIngressLimits {
  transport: WebUITransportLimits;
  message: WebUIMessageLimits;
  attachments: WebUIAttachmentLimits;
}
