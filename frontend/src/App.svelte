<script lang="ts">
  import { onMount } from "svelte";

  import AlbumCard from "./components/AlbumCard.svelte";
  import Downloads from "./components/Downloads.svelte";
  import { api, ApiError } from "./lib/api";
  import { albumKey } from "./lib/format";
  import type { Album, DownloadGroup, SearchResult, Status } from "./lib/types";

  const SEARCH_POLL_MS = 1200;
  const DOWNLOADS_POLL_MS = 2000;
  const STATUS_POLL_MS = 5000;

  let status = $state<Status | null>(null);
  let statusError = $state<string | null>(null);

  let query = $state("");
  let result = $state<SearchResult | null>(null);
  let searching = $state(false);
  let error = $state<string | null>(null);
  let losslessOnly = $state(false);
  let freeSlotOnly = $state(false);

  let downloads = $state<DownloadGroup[]>([]);
  let queued = $state<Set<string>>(new Set());
  let tab = $state<"results" | "downloads">("results");

  let searchTimer: ReturnType<typeof setTimeout> | undefined;

  let albums = $derived(
    (result?.albums ?? []).filter(
      (a) => (!losslessOnly || a.lossless) && (!freeSlotOnly || a.has_free_upload_slot),
    ),
  );
  let activeDownloads = $derived(
    downloads.filter((d) => d.state === "queued" || d.state === "downloading").length,
  );

  function message(e: unknown): string {
    return e instanceof Error ? e.message : String(e);
  }

  async function refreshStatus() {
    try {
      status = await api.status();
      statusError = null;
    } catch (e) {
      status = null;
      statusError = e instanceof ApiError && e.status === 503 ? "Starting…" : message(e);
    }
  }

  async function refreshDownloads() {
    try {
      downloads = await api.downloads();
    } catch {
      // the status pill already reports an unreachable engine
    }
  }

  async function pollSearch(id: string) {
    try {
      const next = await api.search(id);
      if (result && result.id !== id) return; // a newer search replaced this one
      result = next;
      if (next.complete) {
        searching = false;
        return;
      }
    } catch (e) {
      error = message(e);
      searching = false;
      return;
    }
    searchTimer = setTimeout(() => pollSearch(id), SEARCH_POLL_MS);
  }

  async function search(event: SubmitEvent) {
    event.preventDefault();
    const text = query.trim();
    if (text.length < 2 || searching) return;
    clearTimeout(searchTimer);
    const previous = result?.id;
    error = null;
    searching = true;
    tab = "results";
    try {
      const { id } = await api.startSearch(text);
      result = { id, query: text, complete: false, response_count: 0, albums: [] };
      void pollSearch(id);
      if (previous) void api.deleteSearch(previous).catch(() => {});
    } catch (e) {
      error = message(e);
      searching = false;
    }
  }

  async function download(album: Album) {
    const key = albumKey(album);
    queued = new Set(queued).add(key);
    try {
      await api.download(album);
      void refreshDownloads();
    } catch (e) {
      const next = new Set(queued);
      next.delete(key);
      queued = next;
      error = `Could not queue "${album.title}": ${message(e)}`;
    }
  }

  async function cancel(username: string, id: string) {
    await api.cancel(username, id).catch((e: unknown) => (error = message(e)));
    void refreshDownloads();
  }

  async function clearFinished() {
    await api.clearCompleted().catch((e: unknown) => (error = message(e)));
    void refreshDownloads();
  }

  onMount(() => {
    void refreshStatus();
    void refreshDownloads();
    const timers = [
      setInterval(refreshStatus, STATUS_POLL_MS),
      setInterval(refreshDownloads, DOWNLOADS_POLL_MS),
    ];
    return () => {
      timers.forEach(clearInterval);
      clearTimeout(searchTimer);
    };
  });
</script>

<div class="app">
  <header class="top">
    <h1>Music Manager</h1>
    {#if status?.logged_in}
      <span class="pill ok" title={status.server_state}>● {status.username}</span>
    {:else if status}
      <span class="pill warn" title={status.server_state}>● {status.server_state}</span>
    {:else}
      <span class="pill warn">● {statusError ?? "Connecting…"}</span>
    {/if}
  </header>

  <form class="search" onsubmit={search}>
    <input
      type="search"
      placeholder="Artist, album or song"
      aria-label="Search Soulseek"
      bind:value={query}
      autocomplete="off"
    />
    <button class="primary" type="submit" disabled={query.trim().length < 2 || searching}>
      {searching ? "Searching…" : "Search"}
    </button>
  </form>

  <nav class="tabs">
    <button class:active={tab === "results"} onclick={() => (tab = "results")}>Results</button>
    <button class:active={tab === "downloads"} onclick={() => (tab = "downloads")}>
      Downloads{activeDownloads ? ` (${activeDownloads})` : ""}
    </button>
  </nav>

  {#if error}
    <div class="error" role="alert">
      {error}
      <button class="ghost" aria-label="Dismiss" onclick={() => (error = null)}>✕</button>
    </div>
  {/if}

  <div class="layout">
    <main class:hidden={tab !== "results"}>
      {#if result}
        <div class="toolbar">
          <span class="muted">
            {albums.length} albums from {result.response_count} users
            {searching ? "· still searching…" : ""}
          </span>
          <label><input type="checkbox" bind:checked={losslessOnly} /> Lossless</label>
          <label><input type="checkbox" bind:checked={freeSlotOnly} /> Free slot</label>
        </div>
        {#if searching}<div class="progress indeterminate"><div></div></div>{/if}

        <div class="results">
          {#each albums as album (albumKey(album))}
            <AlbumCard {album} queued={queued.has(albumKey(album))} ondownload={download} />
          {:else}
            {#if !searching}
              <p class="muted">No albums matched. Try fewer words or turn off the filters.</p>
            {/if}
          {/each}
        </div>
      {:else}
        <div class="hero muted">
          <p>Search the Soulseek network. Results are grouped into albums and ranked by quality
            and how fast they're likely to download.</p>
        </div>
      {/if}
    </main>

    <aside class:hidden={tab !== "downloads"}>
      <Downloads groups={downloads} oncancel={cancel} onclear={clearFinished} />
    </aside>
  </div>

  <footer class="muted">
    {#if status}v{status.version} ·{/if}
    Download and share only content you have the right to.
  </footer>
</div>

<style>
  .app {
    max-width: 1280px;
    margin: 0 auto;
    padding: 1rem 16px 2rem;
  }

  .top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 0.9rem;
  }

  h1 {
    margin: 0;
    font-size: 1.35rem;
    font-weight: 500;
  }

  .pill {
    font-size: 0.82rem;
    padding: 0.2rem 0.7rem;
    border-radius: 999px;
    background: var(--surface-2);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 60%;
  }

  .pill.ok {
    color: var(--good);
  }

  .pill.warn {
    color: var(--warn);
  }

  .search {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 0.9rem;
  }

  .tabs {
    display: none;
    gap: 0.4rem;
    margin-bottom: 0.8rem;
  }

  .tabs button {
    flex: 1;
  }

  .tabs .active {
    border-color: var(--accent);
    color: var(--accent);
  }

  .error {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.8rem;
    margin-bottom: 0.8rem;
    border-radius: 8px;
    background: color-mix(in srgb, var(--bad) 14%, transparent);
    color: var(--bad);
  }

  .layout {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 340px;
    gap: 1.2rem;
    align-items: start;
  }

  aside {
    position: sticky;
    top: 1rem;
  }

  .toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem 1rem;
    align-items: center;
    margin-bottom: 0.6rem;
    font-size: 0.88rem;
  }

  .toolbar span {
    flex: 1;
  }

  .results {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    margin-top: 0.6rem;
  }

  .hero {
    padding: 3rem 1rem;
    text-align: center;
    max-width: 34rem;
    margin: 0 auto;
  }

  .indeterminate > div {
    width: 30%;
    animation: slide 1.2s ease-in-out infinite;
  }

  @keyframes slide {
    from {
      transform: translateX(-100%);
    }
    to {
      transform: translateX(340%);
    }
  }

  footer {
    margin-top: 2rem;
    font-size: 0.78rem;
    text-align: center;
  }

  @media (max-width: 900px) {
    .layout {
      grid-template-columns: 1fr;
    }

    .tabs {
      display: flex;
    }

    .hidden {
      display: none;
    }

    aside {
      position: static;
    }
  }
</style>
