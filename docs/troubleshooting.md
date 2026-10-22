# Troubleshooting

## View logs

```bash
journalctl -u scud -f
```

## Cannot connect to Rex

Check the address and port in **Settings → Rex URL**, then use **Test Rex** in the setup wizard. If you also run Plex, make sure the URL points to Rex.

The Rex source API must be reachable from the Scud server over a local or private network. Check firewall rules and Docker networking if the connection fails.

## Media does not appear in Rex

Check that Scud can read the configured folder and that the files appear in its **Media** list. Confirm that the configured library name appears in Rex. Check the logs for library-creation errors. Review Scud's logs for scan or sync errors.

## Rex cannot play a file

Check the address Scud registered:

```bash
curl http://REX:32400/rex/sources
```

Replace `REX:32400` with your Rex server's address and port. From the Rex host, try requesting a file from Scud:

```bash
curl -I 'http://SCUD:8788/files/movies/path/to/movie.mkv'
```

Replace the example address and file path with your own. If Rex cannot reach Scud's automatically selected address, set **Scud address for Rex** in Settings.

## A title stays unmatched

Click **Match…** beside the file and enter an IMDb, TMDB, or TVDB ID. See [Matching](matching.md) for filename examples and accepted ID formats.

## Media analysis fails

Use **Test FFmpeg** in Settings to check the installation. A custom FFmpeg folder must also contain FFprobe. Check the file's permissions and the logs for errors if analysis still fails.

## The web interface is unavailable

Check `systemctl status scud` and confirm that you are using the address printed by the installer. If the default port was occupied, Scud may be using a different one. Port and listen-address changes require a service restart.
