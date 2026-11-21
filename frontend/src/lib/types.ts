// Mirrors the backend's response models (src/ha_music_manager/api.py, albums.py).

export interface Status {
  version: string;
  engine: "managed" | "external";
  connected: boolean;
  logged_in: boolean;
  server_state: string;
  username: string;
}

export interface Track {
  filename: string;
  name: string;
  size: number;
  extension: string;
  bit_rate: number | null;
  length: number | null;
}

export interface Album {
  username: string;
  directory: string;
  title: string;
  track_count: number;
  tracks: Track[];
  quality: string;
  lossless: boolean;
  total_size: number;
  total_length: number;
  has_free_upload_slot: boolean;
  queue_length: number;
  upload_speed: number;
  score: number;
}

export interface SearchResult {
  id: string;
  query: string;
  complete: boolean;
  response_count: number;
  albums: Album[];
}

export interface DownloadFile {
  id: string;
  name: string;
  state: string;
  size: number;
  percent: number;
  speed: number;
  error: string | null;
}

export interface DownloadGroup {
  username: string;
  directory: string;
  title: string;
  percent: number;
  state: "queued" | "downloading" | "completed" | "failed";
  files: DownloadFile[];
}
