# Source references and attribution

Scud is a Python source for local files. Its Rex integration and matching behavior were developed with reference to Zurg.

Relevant Zurg source paths are recorded in the corresponding modules:

- `/internal/rexfeed/feed.go`: registration, batching, snapshots, delivery queue and retries.
- `/internal/rexfeed/library.go`: media placement and explicit bonus-video kinds.
- `/internal/releasename/releasename.go` and `/internal/releasename/numbering.go`: filename parsing and episode numbering.
- `/internal/torrent/mediainfo.go`: ffprobe output supplied to the media server.

Scud contains its own local filesystem inventory, HTTP file server, TMDB integration, interface and persistent publisher. It does not bundle the Zurg or Rex source trees. Rex’s feed contract is documented in its `/docs/feed-api.md`.

