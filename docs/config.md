# Configuration

The setup wizard and Settings page save to `/opt/scud/config.yml`. If you edit the file directly, restart Scud with `systemctl restart scud` to apply the changes.

| Option | Type | Default | Description |
|---|---|---|---|
| `scud` | string | `v1` | Configuration format version. Keep this value. |
| `host` | string | `0.0.0.0` | Listen address. The default accepts connections on all IPv4 interfaces. |
| `port` | integer | `8788` | Port for the web interface and media files. |
| `source_url` | string | empty | Scud address that Rex can reach. Leave blank for automatic detection. |
| `rex_url` | string | empty | Rex server URL, including its port, such as `http://rex:32400`. |
| `rex_source` | string | `scud` | Name of this Scud installation in Rex. Use a unique name for each installation connected to the same Rex server. |
| `rex_snapshot_every_hours` | integer | `6` | How often to send the complete media list to Rex. Minimum: 1 hour. |
| `poll_every_secs` | integer | `60` | How often to check folders for changes. Minimum: 5 seconds. |
| `tmdb_api_key` | string | empty | TMDB v3 API key or API Read Access Token for title searches. |
| `ffmpeg_path` | string | empty | FFmpeg executable or folder path. Leave blank for automatic detection. |
| `log_level` | string | `INFO` | DEBUG, INFO, WARNING, ERROR or CRITICAL; changes apply immediately. |
| `allow_rex_delete` | boolean | `false` | Permit Rex to delete registered local media files. Off by default. |
| `libraries` | list | empty | Movie and TV folders to scan. |

## Settings and scan status

Settings has separate tabs for TMDB, Rex, scanning and serving, and libraries. Save settings applies changes across all tabs. Settings are saved locally even if Rex is busy or unavailable; library creation and source registration retry in the background.

The media page shows scan start and finish times, elapsed time, and average files processed per second. After counting the files, Scud estimates the finish time from the speed so far; estimates can change when matching or probing takes longer.

A folder shows **Complete in Rex** when its files have been verified in the configured Rex library. Scud checks file names, sizes and modification times to identify changed folders; unchanged folders skip matching and probing. A file edited in place is detected even when its parent folder’s date stays the same.

Settings → Compatibility shows the last tested Rex commit and the results of the startup Rex and TMDB API checks. A failed check is logged and displayed in a warning banner. Scud keeps running so existing media remains accessible.

## Media folders

```yaml
libraries:
  - id: movies
    type: movie
    name: Movies
    path: /mnt/media/movies
  - id: tv
    type: show
    name: TV
    path: /mnt/media/tv
```

- `id`: a unique identifier for the folder. Keep it stable after adding media.
- `type`: `movie` or `show`.
- `name`: the library name shown in Scud.
- `path`: the folder's path on the Scud server. The service must be able to read it.

Scud creates or reuses a Rex library with the configured name and media type. Its section ID is saved as `rex_library_key` and used when sending files. `rex_library_name`, when present, supplies the name in Rex.

## TMDB

Add your TMDB API key in the wizard or Settings, then click **Test TMDB**. You can use a v3 API key or API Read Access Token from your TMDB account’s API settings. The value is masked in the browser; leave the field blank to keep the saved key. Configuration files containing a key should be kept private.

## FFmpeg path

Leave `ffmpeg_path` empty to use the system installation. For a custom installation, enter the executable path, such as `/usr/bin/ffmpeg`, or its containing folder. The folder must also contain `ffprobe`, which Scud uses to read media details.

Paths refer to the Scud server. **Test FFmpeg** checks the current field value before you save and reports the versions of both tools or an error.

## Network settings

Automatic detection chooses the local address Scud uses to connect to Rex. If Rex cannot reach that address, set `source_url` to an address it can reach, such as `http://192.168.1.20:8788`.

Restart Scud after changing its listen address or port. Open the new address to reconnect to the web interface.

## Logs

INFO records scan summaries, delivery and errors. DEBUG adds HTTP request details. WARNING, ERROR and CRITICAL reduce output. Set the level in Settings; `SCUD_LOG_LEVEL` overrides the configuration when supplied through the environment. HTTP-library debug output is suppressed so API credentials are not logged in query strings.

Use `journalctl -u scud -f` to follow service logs. Logs, configuration and the media database are operator state and are not part of the source distribution.

## Multiple folders

Use **Add library** in the wizard or Settings. Each row has its own folder, media type and destination name. Different folders can use the same Rex library name to share one destination library. Removing a row stops scanning that folder and withdraws its Scud entries; it does not delete local files or other sources’ media.

## Deletion from Rex

**Allow deletion from Rex** is off by default. If enabled, Rex’s source DELETE requests remove registered files from disk and withdraw their source IDs. This is destructive and requires a trusted network. Unregistered files and paths outside configured roots cannot be deleted through this endpoint.
