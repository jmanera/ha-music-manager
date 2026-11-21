<script lang="ts">
  import { formatBytes, formatDuration, formatSpeed } from "../lib/format";
  import type { Album } from "../lib/types";

  interface Props {
    album: Album;
    queued: boolean;
    ondownload: (album: Album) => void;
  }

  let { album, queued, ondownload }: Props = $props();
  let open = $state(false);
  let parentPath = $derived(album.directory.split("\\").slice(0, -1).join(" › "));
</script>

<article class="card album">
  <div class="main">
    <div class="score" title="Score: quality and availability (0–100)">
      <span>{Math.round(album.score)}</span>
    </div>

    <div class="info">
      <h3 title={album.directory}>{album.title}</h3>
      {#if parentPath}<div class="path muted">{parentPath}</div>{/if}
      <div class="meta">
        <span class="badge" class:lossless={album.lossless}>{album.quality}</span>
        <span>{album.tracks.length} {album.tracks.length === 1 ? "track" : "tracks"}</span>
        <span>{formatBytes(album.total_size)}</span>
        {#if album.total_length}<span>{formatDuration(album.total_length)}</span>{/if}
      </div>
      <div class="peer muted">
        <span>{album.username}</span>
        <span class:good={album.has_free_upload_slot}>
          {album.has_free_upload_slot ? "free slot" : `queue ${album.queue_length}`}
        </span>
        <span>{formatSpeed(album.upload_speed)}</span>
      </div>
    </div>

    <div class="actions">
      <button class="primary" disabled={queued} onclick={() => ondownload(album)}>
        {queued ? "Queued" : "Download"}
      </button>
      <button class="ghost" aria-expanded={open} onclick={() => (open = !open)}>
        {open ? "Hide tracks" : "Tracks"}
      </button>
    </div>
  </div>

  {#if open}
    <ol class="tracks">
      {#each album.tracks as track (track.filename)}
        <li>
          <span class="name">{track.name}</span>
          <span class="muted">
            {track.bit_rate ? `${track.bit_rate} kbps · ` : ""}{formatBytes(track.size)}
            {track.length ? ` · ${formatDuration(track.length)}` : ""}
          </span>
        </li>
      {/each}
    </ol>
  {/if}
</article>

<style>
  .album {
    padding: 0.9rem 1rem;
  }

  .main {
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 0.9rem;
    align-items: center;
  }

  .score {
    width: 2.7rem;
    height: 2.7rem;
    border-radius: 50%;
    display: grid;
    place-items: center;
    font-weight: 700;
    background: var(--surface-2);
  }

  h3 {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    overflow-wrap: anywhere;
  }

  .path {
    font-size: 0.8rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .meta,
  .peer {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem 0.8rem;
    align-items: center;
    margin-top: 0.3rem;
    font-size: 0.86rem;
  }

  .good {
    color: var(--good);
  }

  .actions {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    align-items: stretch;
  }

  .tracks {
    margin: 0.8rem 0 0;
    padding: 0.6rem 0 0 1.6rem;
    border-top: 1px solid var(--border);
    font-size: 0.88rem;
  }

  .tracks li {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.15rem 0;
  }

  .tracks .name {
    overflow-wrap: anywhere;
  }

  .tracks .muted {
    white-space: nowrap;
  }

  @media (max-width: 560px) {
    .main {
      grid-template-columns: auto 1fr;
    }

    .actions {
      grid-column: 1 / -1;
      flex-direction: row;
    }

    .actions .primary {
      flex: 1;
    }
  }
</style>
