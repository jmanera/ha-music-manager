# Music Manager

Search the Soulseek network for albums and download them into your Home Assistant media
folder. The app adds a **Music** panel to the sidebar.

## Configuration

| Option | Default | Description |
| --- | --- | --- |
| `soulseek_username` | | Your Soulseek username. If the name is free, the account is created on first login. |
| `soulseek_password` | | Your Soulseek password. |
| `download_dir` | `/media/music` | Where finished downloads go. Must be under `/media` or `/share`. Each album lands in its own folder. |
| `share_dirs` | `[]` | Folders you share with other users. Soulseek is a sharing community: some peers won't serve users who share nothing. |
| `log_level` | `info` | `debug` also prints the Soulseek engine's own log. |

Partial downloads are kept in `/share/ha-music-manager/incomplete` until they finish.

## Network

Soulseek works without any port forwarding, but some peers can only reach you if port
**50300/tcp** is forwarded to your Home Assistant host. If you change the host port in the
app's **Network** settings, forward the same port on your router.

## Playing your music

Point Music Assistant, Jellyfin or Plex at `/media/music` (or whatever you set as
`download_dir`). New albums show up after their next library scan.

## Home Assistant integration

Install the **Music Manager** integration from HACS (custom repository
`https://github.com/jmanera/ha-music-manager`, type *Integration*). While this app runs,
Home Assistant discovers it under **Settings → Devices & services**: click **Configure** and
you're done. You get download sensors, the `music_manager.search` and
`music_manager.download_best` actions, and `music_manager_download_completed` /
`music_manager_download_failed` events.

The integration authenticates with a key the app creates on first start. It is stored in the
app's data folder as `integration_key`. You only need it to set up the integration by hand, for
example against an app running outside Home Assistant OS.

## Legal

Download and share only content you have the right to.

## Support

Report problems at <https://github.com/jmanera/ha-music-manager/issues>.
