# Matching

Scud identifies movies and TV episodes from their folder and file names, using TMDB.

For best results, include a movie's title and year in its name. For TV, use a show folder and episode numbers such as `S02E04` or `2x04`:

```text
movies/The Thing (1982)/The Thing (1982).mkv
tv/The Office (US)/Season 02/The Office US S02E04.mkv
```

## Automatic matches

Scud normalizes punctuation, capitalization, and leading articles (`The`, `A`, and `An`) before comparing titles. A result must have the same normalized title and media type. When a year is available, the result must be within one year; the closest year is preferred.

Files that do not meet these rules remain **Unmatched** in Scud. They are sent to Rex after an automatic or manual match supplies a valid media ID. TV files also need season and episode numbers.

## Correcting a match

Use the folder’s **Match…** button to match a movie or show folder and its subfolders. The match applies to all current files and files added in later scans, replacing existing matches in that folder. Each file also has a **Match…** button for individual corrections.

Enter one of these ID formats:

- IMDb: `tt0084787`
- TMDB: `tmdb://1091`, or a numeric TMDB ID
- TVDB: `tvdb://73244`

You can also enter a title and year. A manual match is preserved during later scans. For TV, use the show's ID; the filename supplies the season and episode numbers.

Rex retrieves the title's artwork and other metadata from the supplied identity.

## Suggested matches

The match popup shows filenames and the titles and years parsed from the folder and files. Suggestions come from TMDB and are ranked by title similarity and year. Choose a suggestion to fill in its ID, title, and year, then apply the match. You can also edit the search title and search again.

Automatic matching tries the folder name first, then the filename if the folder has no accepted match. Suggestions can include broader results for you to choose from; automatic matches require an exact normalized title and a compatible year.

## Episode matching

Scud starts with season and episode numbers parsed from the filename. Expand a TV folder in Media to see the episode number and its name from TMDB.

Use **Match episode…** beside a file to select its show, season, and episode. TMDB provides the season and episode choices; the show poster helps identify the series. For a file containing several episodes, choose its first and last episodes. Saved episode selections are kept during later scans and sent to Rex.

The match popup includes every filename in the selected folder, with a filename filter. Suggested titles include TMDB posters. Choosing a suggestion fills the ID, title, and year; use **Apply match** to save it.
