import type { Album, DownloadGroup, SearchResult, Status } from "./types";

// Relative URLs on purpose: under Ingress the page lives at /api/hassio_ingress/<token>/.
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`api/${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = ((await response.json()) as { detail?: string }).detail ?? detail;
    } catch {
      // not JSON
    }
    throw new ApiError(response.status, detail);
  }
  return (response.status === 204 || response.status === 202 ? undefined : response.json()) as T;
}

export const api = {
  status: () => request<Status>("GET", "status"),
  startSearch: (query: string) => request<{ id: string }>("POST", "searches", { query }),
  search: (id: string) => request<SearchResult>("GET", `searches/${id}`),
  deleteSearch: (id: string) => request<void>("DELETE", `searches/${id}`),
  download: (album: Album) =>
    request<void>("POST", "downloads", {
      username: album.username,
      files: album.tracks.map((t) => ({ filename: t.filename, size: t.size })),
    }),
  downloads: () => request<DownloadGroup[]>("GET", "downloads"),
  cancel: (username: string, id: string) =>
    request<void>("DELETE", `downloads/${encodeURIComponent(username)}/${id}`),
  clearCompleted: () => request<void>("DELETE", "downloads/completed"),
};
