# Finfluence

[![tests](https://github.com/slriggss/finfluence/actions/workflows/tests.yml/badge.svg)](https://github.com/slriggss/finfluence/actions/workflows/tests.yml)

A tool that, every day on its own, downloads the public YouTube statistics of 17 women-focused and money-mindset personal-finance channels, adds them to a history with one row per channel per day, reports which channels moved the most, and publishes the result as an installable website.

- Site: https://slriggss.github.io/finfluence/
- Built for the Financial Data Analytics Data Tracker project.

## What it tracks

Seventeen YouTube channels of creators, educators and companies in women-focused personal finance, including two chosen for an anti-consumption, frugal-living angle (The Financial Diet and Kate Kaden). See `roster.csv`. The key that lines a channel up from one day to the next is its YouTube **channel ID** (`item_id`). In the roster, the `match` column says how sure the match from the creator's Instagram handle to the YouTube channel was (`high`, `medium`, `low`); `direct` marks a channel added by its YouTube handle, with no Instagram handle (so `instagram` is empty for it).

## Sources

| Source | Format | What is kept |
|---|---|---|
| `youtube`: YouTube Data API v3, `channels.list` | JSON, saved as `data/raw/<date>/youtube.json.gz` | One call per 50 channels, only for the channel IDs in `roster.csv`, asking for `snippet` and `statistics`. Of the response, only each channel's `id`, `title` and `statistics` are kept (not thumbnails, descriptions or other fields). |

The API key is stored as the repository secret `YOUTUBE_API_KEY`, read by the workflow, and never written to any file. Each run also writes `data/raw/<date>/results.json`, the outcome of every source (ok, count, error). A source that fails writes no raw file that day, and the run goes on.

## Files

| Path | What it does |
|---|---|
| `tracker/sources.py` | Fetches each source and converts its payload to the common columns. |
| `tracker/build.py` | Builds `data/history.csv` and the status from the raw files alone (`python -m tracker.build`). |
| `tracker/moves.py` | The move rule. |
| `tracker/pipeline.py` | The daily run: fetch, build, write status, update the GitHub Issue. |
| `roster.csv` | The tracked channels and their fixed attributes. |
| `data/raw/<date>/` | The compressed raw responses and `results.json` for each day. |
| `data/history.csv` | One row per channel per day. |
| `data/status.json` | Describes the latest run. |
| `index.html`, `browse.html`, `trends.html` | The three pages: Today, Browse, Trends. |
| `app.js` | Navigation bar, data loading and formatting shared by the pages. |
| `calc.js` | The calculations behind the Today and Trends pages (also run by the tests in Node). |
| `charts.js` | Small inline-SVG chart functions. |
| `style.css` | The one set of fonts and colors for all pages. |
| `manifest.webmanifest`, `sw.js`, `icon*` | Make the site installable and usable offline. |
| `tests/` | The pytest suite (and a Node script that checks the Trends numbers). |
| `.github/workflows/daily.yml` | Runs the pipeline twice a day (07:23 and 19:47 UTC) and commits the data. |
| `.github/workflows/tests.yml` | Runs the tests on every push. |
| `pyproject.toml`, `uv.lock` | Python dependencies. |

## Columns of `data/history.csv`

Dates are UTC dates, `YYYY-MM-DD`. A value the source does not report is left empty. Rows are sorted by `date`, then `item_id`.

| Column | Meaning | Unit |
|---|---|---|
| `date` | UTC date of the run that produced the row | date |
| `item_id` | The channel's YouTube channel ID (the key) | text |
| `item` | The channel's name on YouTube | text |
| `source` | Where the row came from (`youtube`) | text |
| `subscribers` | Public subscriber count. YouTube rounds it to three significant figures, and it is empty if the channel hides it. | subscribers |
| `views` | Total lifetime views of all the channel's videos | views |
| `videos` | Number of public videos | videos |
| `views_per_video` | `views ÷ videos`, rounded to one decimal; empty if there are no videos | views per video |
| `tier` | Size band from `subscribers`: `under 10K`, `10K-100K`, `100K-1M`, `1M+` | text |
| `kind` | `creator` (a person-led channel) or `company` (a business or platform), from `roster.csv` | text |
| `instagram` | The Instagram handle the channel was matched from, from `roster.csv` | text |
| `youtube_handle` | The channel's YouTube handle, from `roster.csv` | text |

`data/status.json` has `run_time` (UTC), `first_run_date` (earliest raw file), `days_with_success` (different dates with a raw file), `items` (channels in the latest run), `new_today` (channels that appeared since the previous day with data; 0 on the first day), `gone_today` (channels that disappeared), and `sources` (one entry each with `name`, `ok`, `count`).

## The move rule

A **move** is the **percent change in a channel's total views** between the latest run and the previous run that has data. The Issue lists the **10 channels with the largest absolute percent change** (ties are broken by the larger absolute change in views, then by channel ID), with old and new views, the change, subscribers before and after, and new videos. Channels present on only one of the two days are listed as appeared or disappeared, not as moves. Percent change favors small channels, since a few thousand views move a small channel more than a large one; the Issue shows the raw numbers beside the percentage for that reason.

An Issue titled with the date is opened (or updated, on a second run the same day) every day, even a day with no changes, and the previous day's Issue is closed.

## Build the history from the raw files

```
uv run python -m tracker.build
```

This reads every file in `data/raw/` and rewrites `data/history.csv`. The history depends on the raw files alone, so running it again gives the identical file, and a change to a rule applies to every day.

A second run on the same day replaces that day's raw files, rebuilds the history and updates that day's Issue, so each day counts once. If every source fails on a second run, that day's earlier files are kept rather than wiped.

## Run it yourself

```
uv sync
YOUTUBE_API_KEY=... uv run python -m tracker.pipeline --no-issue
uv run pytest
```

## Notes and limits

- Subscriber counts are rounded by YouTube, so large channels change in steps. Views and video counts update more finely.
- Matches from Instagram handles to YouTube channels marked `medium` or `low` in `roster.csv` should be read with caution.
- Only public data is collected, from the official API, once a day.
