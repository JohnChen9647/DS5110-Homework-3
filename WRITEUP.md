# Step 3 — Load the data and keep what is refused

## Predictions

The loader uses UTF-8 decoding, with date format of `DD-MMM-YYYY`, does not allow blank required fields, and retains blank optional movie
fields as `NULL`. Scanning the source data, some movie has invalid characters, and some ratings & genres will be dropped because of the rejection of those movies. Due to the amount of data, I can only estimate on how many rows will be rejected.

| Table | Predicted rows | Basis |
|---|---:|---|
| `occupations` | 21 | One row per line in `u.occupation` |
| `users` | 943 | One row per record in `u.user` |
| `movies` | 1,680 | 1,682 source rows in `u.item`, some rows have illegal char |
| `genres` | 19 | The 19 named genre IDs in `u.genre` |
| `movie_genres` | 2,000 | Most movies have 1-3 genres, 2000 is a good estimate on a tidy form of genres with movies|
| `ratings` | 99,950| 100,000 source rows, some ratings are associated with refused movies |
| Rejected records | 52 | 2 movie rows plus 50 ratings with missing movie references |


## Results 1

| Table | Predicted rows | Actual rows | Difference | Reason|
|---|---:|---:|---:|---:|
| `occupations` | 21 | 21 | 0 |  |
| `users` | 943 | 943 | 0 |  |
| `movies` | 1,680 | 1,672 | 8| More movies have illegal characters |
| `genres` | 19 | 19 | 0 |  |
| `movie_genres` | 2,000| 2,878 | 0 | The initial estimate was not accurate. More genres than we thought |
| `ratings` | 99,950| 99,926 | 0 | Expected less rating being dropped. Actuallly more |
| Rejected records | 52| 84 | 0 |  |

The rejections were fixable. We can change the decode format to allow the non-utf8 characters. Also, there was a line rejected for bad date foramt: `u.item,1373,movies,"[""1373"", ""Good Morning (1971)"", ""4-Feb-1971"", """", ""http://us.imdb.com/M/title-exact?Good%20Morning%20(1971)"", ""1"", ""0"", ""0"", ""0"", ""0"", ""0"", ""0"", ""0"", ""0"", ""0"", ""0"", ""0"", ""0"", ""0"", ""0"", ""0"", ""0""]",invalid release date '4-Feb-1971'; expected DD-MMM-YYYY`. This should be accepted because the cell itself has valid data. The dropped ratings should also be included after changing decoding method.

## Follow-up: reload all source rows

The Makefile now runs `src/load.py` first, then `src/reload.py`. The second script clears and rebuilds
`data/movielens.db` from all raw files; it decodes the text as Latin-1 and keeps release dates as source text. Empty optional movie fields (release date, video-release date, and IMDb URL) are stored as SQL `NULL`, matching the nullable columns in the schema; they do not cause the movie row to be rejected. Required fields remain subject to the schema's `NOT NULL` constraints. The reload script does not write or replace the rejection CSV, so that file remains the record of what the first load rejected.

## Results 2

| Table / report | After `load.py` | After `reload.py` | Restored by reload |
|---|---:|---:|---:|
| `occupations` | 21 | 21 | 0 |
| `users` | 943 | 943 | 0 |
| `movies` | 1,672 | 1,682 | 10 |
| `genres` | 19 | 19 | 0 |
| `movie_genres` | 2,878 | 2,893 | 15 |
| `ratings` | 99,926 | 100,000 | 74 |
| Rejected rows | 84 | 0|  |
