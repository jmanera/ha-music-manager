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

## Legal

Download and share only content you have the right to.

## Support

Report problems at <https://github.com/jmanera/ha-music-manager/issues>.
