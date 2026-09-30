# Put the episodes to analyze in this folder

Copy your video files here. **The videos are never committed to git** (they are ignored), so nothing you put in this folder is uploaded anywhere by git.

## Rules

1. **Only `.mkv` files are picked up.** Convert other formats (`.mp4` and so on) to `.mkv` first.
2. **Each file name must contain an episode tag like `S01E03`**: `S` + season number + `E` + episode number. It is case-insensitive, can appear anywhere in the name, and the numbers can be one or two digits for the season and up to three for the episode.
3. **Subfolders are fine.** Files are found anywhere under this folder, so you can organise them however you like.
4. **Each tag may be used by only one file.** If two files carry the same tag, the run stops and tells you which two.

Only the tag matters. The rest of the file name is ignored, so keep any title or release text you like.

### Names that work

```
S01E03 - Family Politics.mkv
Show.Name.s02e10.1080p.mkv
video/some-folder/Show Name S01E15.mkv
```

### Names that do not work

| Name | Why |
|---|---|
| `Show Name 1x03.mkv` | The tag must be `S01E03`, not `1x03`. |
| `S01 E03.mkv` | No space allowed inside the tag. |
| `xS01E03.mkv` | The tag must not be glued to other letters or digits before it. |
| `S01E1234.mkv` | Episode numbers have at most three digits. |
| `Episode 3.mkv` | No tag at all. |

A file with no recognisable tag is **skipped**, and a `warning: ignoring ...` line is printed so you can see which one.

## Which episodes can be analyzed

The program also needs each episode's **title and air date**, and these currently come from a built-in list, not from the file. If your tag refers to an episode that is not in the list, the run stops with `no title/air date is known for S..E..`. Extending the list is a code change for now (`screenscan/config.py`).

Older download-style names that carry no tag (for example `103_Degrassi` or a leading `07 - `) are still understood for the episodes already in the built-in list, so existing files keep working. New files should use the tag.

## Checking your setup

From the project folder, this lists the episodes the program found and the file each one matched. Replace the `1` with the season number you want to check:

```bash
SEASON=1 uv run python -c "from screenscan.config import episodes; [print(e.code, '|', e.title, '|', e.video.name) for e in episodes()]"
```

If an episode is missing from the list, its file name does not follow the rules above. Then see the main [README](../README.md) for how to run the analysis.
