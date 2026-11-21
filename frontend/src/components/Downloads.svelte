<script lang="ts">
  import { albumKey, formatBytes, formatSpeed } from "../lib/format";
  import type { DownloadGroup } from "../lib/types";

  interface Props {
    groups: DownloadGroup[];
    oncancel: (username: string, id: string) => void;
    onclear: () => void;
  }

  let { groups, oncancel, onclear }: Props = $props();
  let expanded = $state<Record<string, boolean>>({});

  const LABELS: Record<DownloadGroup["state"], string> = {
    queued: "Queued",
    downloading: "Downloading",
    completed: "Done",
    failed: "Failed",
  };

  let hasFinished = $derived(groups.some((g) => g.state === "completed" || g.state === "failed"));
</script>

<section class="downloads">
  <header>
    <h2>Downloads</h2>
    {#if hasFinished}
      <button class="ghost" onclick={onclear}>Clear finished</button>
    {/if}
  </header>

  {#if groups.length === 0}
    <p class="muted empty">Nothing yet. Albums you download show up here.</p>
  {/if}

  {#each groups as group (albumKey(group))}
    {@const key = albumKey(group)}
    <div class="card group">
      <button class="ghost head" onclick={() => (expanded[key] = !expanded[key])}>
        <span class="title">{group.title}</span>
        <span class="state {group.state}">{LABELS[group.state]}</span>
      </button>
      <div class="progress" aria-label="{group.percent}%">
        <div style:width="{group.percent}%"></div>
      </div>
      <div class="sub muted">
        <span>{group.username}</span>
        <span>{group.files.length} files · {group.percent}%</span>
      </div>

      {#if expanded[key]}
        <ul>
          {#each group.files as file (file.id)}
            <li>
              <span class="name" title={file.error ?? file.state}>{file.name}</span>
              <span class="muted">
                {#if file.state.startsWith("InProgress")}
                  {file.percent}% · {formatSpeed(file.speed)}
                {:else}
                  {file.state.replace(/^Completed, /, "")} · {formatBytes(file.size)}
                {/if}
              </span>
              {#if !file.state.startsWith("Completed")}
                <button
                  class="ghost"
                  aria-label="Cancel {file.name}"
                  onclick={() => oncancel(group.username, file.id)}>✕</button
                >
              {/if}
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  {/each}
</section>

<style>
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.6rem;
  }

  h2 {
    margin: 0;
    font-size: 1.05rem;
  }

  .empty {
    font-size: 0.9rem;
  }

  .group {
    padding: 0.7rem 0.8rem;
    margin-bottom: 0.6rem;
  }

  .head {
    width: 100%;
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
    padding: 0 0 0.45rem;
    color: var(--text);
    text-align: left;
  }

  .title {
    font-weight: 600;
    overflow-wrap: anywhere;
  }

  .state {
    font-size: 0.8rem;
    white-space: nowrap;
    color: var(--muted);
  }

  .state.downloading {
    color: var(--accent);
  }

  .state.completed {
    color: var(--good);
  }

  .state.failed {
    color: var(--bad);
  }

  .sub {
    display: flex;
    justify-content: space-between;
    font-size: 0.8rem;
    margin-top: 0.35rem;
  }

  ul {
    list-style: none;
    margin: 0.5rem 0 0;
    padding: 0;
    font-size: 0.82rem;
  }

  li {
    display: grid;
    grid-template-columns: 1fr auto auto;
    gap: 0.5rem;
    align-items: center;
    padding: 0.15rem 0;
  }

  li .name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
