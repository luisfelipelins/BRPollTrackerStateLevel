# Brazilian presidential poll tracker

This project compares a tracker built directly from national presidential runoff polls with a national estimate built from state polls. A third series restricts national polls to institutes also represented in state polling. The local dashboard covers 2026 and the completed elections of 2014, 2018 and 2022.

There are two separate workflows: `app.py` reads the existing dataset and serves the dashboard; `dataset_completer.py` downloads 2026 survey registrations, searches for published results and fills missing percentages using OpenRouter. Opening or refreshing the dashboard does **not** run the dataset updater.

## Contents

- [Project files](#project-files)
- [Installation and startup](#installation-and-startup)
- [Using the dashboard](#using-the-dashboard)
- [Data sources and CSV structure](#data-sources-and-csv-structure)
- [Methodology](#methodology)
- [Creating an OpenRouter API key](#creating-an-openrouter-api-key)
- [Updating the dataset](#updating-the-dataset)
- [Reviewing and correcting results](#reviewing-and-correcting-results)
- [Configuration and maintenance](#configuration-and-maintenance)
- [Checks and troubleshooting](#checks-and-troubleshooting)

## Project files

| Path | Purpose |
| --- | --- |
| `app.py` | Flask server, JSON API, caching and dashboard calculations. |
| `eleicoes2026.py` | Current-election preparation, aggregation, TSE results, diagnostics and standalone charts. |
| `avaliacao.py` | Historical preparation, aggregation and comparison with actual runoff results. |
| `dataset_completer.py` | Registration download, missing-result queue, web search, AI extraction and validated writes. |
| `data/data.csv` | Main polling dataset, shared by the dashboard and analysis scripts. |
| `data/tse.csv` | Extracted 2026 TSE registration data, replaced by the updater. |
| `data/poll_status.csv` | Extraction status, retry history and source information by registration. |
| `tracker_web/index.html` | Dashboard layout. |
| `tracker_web/methodology.html` | Methodology text displayed inside the dashboard. |
| `tracker_web/static/app.js` | Plotly charts, controls, table filtering and CSV exports. |
| `tracker_web/static/style.css` | Dashboard styling. |
| `requirements.txt` | Pinned Python dependencies for the dashboard and updater. |
| `openrouter_api_key.txt` | Local credential used by the updater; ignored by Git. |
| `tests/` | Local backend and frontend checks, when available; ignored by Git. |

The `.gitignore` excludes `aux_csv/`, `openrouter_api_key.txt`, `tests/` and `__pycache__/`, including matching names below the root. It does not exclude the main dataset or status log. Ignore rules do not remove files already tracked by Git. This folder was not a Git repository when this guide was updated; the rules take effect when it is placed in one.

## Installation and startup

### Python environment

The inspected environment uses **Python 3.10.9**, at `C:\Users\lfval\anaconda3\python.exe`. Installed versions were obtained with:

```powershell
& C:/Users/lfval/anaconda3/python.exe -m pip list
```

`requirements.txt` pins Flask 2.2.5, Werkzeug 2.2.3, Plotly 5.19.0, NumPy 1.26.4, pandas 2.2.3, Matplotlib 3.10.8, requests 2.32.4 and ddgs 9.16.0. `ddgs` supplies the updater's web searches. Werkzeug is pinned alongside Flask to preserve the installed web-stack combination. This is a project dependency list, not a complete lockfile of the Anaconda environment; other transitive dependencies are resolved by pip.

Run commands from the project folder. On Luis's computer:

```powershell
& C:/Users/lfval/anaconda3/python.exe -m pip install -r requirements.txt
& C:/Users/lfval/anaconda3/python.exe app.py
```

On another Windows computer with Python 3.10 installed, create an isolated environment alongside the project folder:

```powershell
py -3.10 -m venv ../tracker-venv
& ../tracker-venv/Scripts/python.exe -m pip install -r requirements.txt
& ../tracker-venv/Scripts/python.exe app.py
```

Use the same interpreter for installation and execution. Below, `python` is shorthand: substitute the Anaconda or virtual-environment executable when necessary. In the inspected setup, plain `python` resolves to the Windows Store shortcut rather than Anaconda.

### Start the dashboard

Open **http://127.0.0.1:5000** after starting `app.py`. Leave the terminal running; stop with `Ctrl+C`. The server binds to the local computer only, with debug mode disabled. Plotly JavaScript is served locally from the Python package. Normal use needs no Node installation or frontend build step.

Keep `data/data.csv` in place: the updater extends an existing dataset and does not bootstrap the historical dataset from scratch. An OpenRouter key is unnecessary for viewing existing data.

### First-load election downloads

Previous-election results supply state weights and fallback estimates. Historical views also need the selected election's actual result:

| Dashboard year | TSE result archives needed |
| --- | --- |
| 2014 | 2010 and 2014 |
| 2018 | 2014 and 2018 |
| 2022 | 2018 and 2022 |
| 2026 | 2022 |

Archives are reused from the system temporary directory as `polls_votacao_YEAR.zip`. If absent, the importer downloads TSE's municipality/zone voting archive. These can be several hundred MB, so the first request can take time and needs internet access. Temporary-directory cleanup can require a later download again.

## Using the dashboard

Choose 2026 or a previous election, then an aggregation rule. **Latest 10 polls** is the initial selection. The rule applies to national and state polling alike.

The national chart compares all selected national polls, the state aggregate and national polls from shared institutes. Hover to compare daily values and coverage. The separate state selector controls the state chart and its survey dots. Click a dot to highlight it; click again or use **Clear selected poll** to reset. Drag to zoom and double-click to reset the view.

The survey table has searchable, multiselect column filters; clicking column labels sorts it. These controls affect only the table, not trackers, performance calculations or exports. Table shares use the same two-candidate normalization as the charts. Missing registry numbers appear as “Not provided”; none are inferred.

The table includes eligible polls from **August 3** through the last displayed date. Chart calendars and plotted poll dots cover **September 1 through runoff**, capped at today for 2026. Earlier same-year polls can still enter latest-ten calculations even when absent from the table.

Each chart's **Export data** button downloads a UTF-8 CSV independently of table filters. National/state exports include daily estimates, plotted polls and actual-result references when available. Other exports contain the respective diagnostics or contributions. Plotly's toolbar exports PNGs. CSVs retain precision; displayed contributions round to two decimals.

Use **Refresh** after saving dataset changes. Backend cache keys include the source modification timestamp and today's date. Refresh requests the current revision; it does not clear all caches or download poll registrations. Restart after changing Python modules. Dataset updates are not automatically scheduled.

## Data sources and CSV structure

The project's supplied methodology identifies [Poder360's polling dataset through Base dos Dados](https://basedosdados.org/dataset/fb38dbe8-03ce-46b4-a6b7-638ade03999c?table=b6df9e1c-cbcb-4dbd-893b-8645a51773e6) as its main polling source. It records that missing 2018 and 2026 observations were reconstructed from TSE registration metadata and web searches for reported results, with ChatGPT assistance. A sample was checked, but this is not a complete audit of those figures.

The automated updater downloads the [TSE 2026 survey registration dataset](https://dadosabertos.tse.jus.br/dataset/pesquisas-eleitorais-2026), extracting `pesquisa_eleitoral_2026_BRASIL.csv` from `pesquisa_eleitoral_2026.zip`. Registrations identify surveys and describe their methodology; published candidate percentages are sought separately on the web.

Actual election outcomes come from TSE's `votacao_candidato_munzona_YEAR.zip` archives. The importer selects presidential second-round nominal votes for the configured candidates, including all 26 states, DF and overseas votes (`ZZ`).

### Main dataset

`data/data.csv` is comma-separated, with one candidate observation per row. Preserve its full existing header. Key columns are:

| Column | Meaning and expected values |
| --- | --- |
| `id_pesquisa` | Survey identifier shared by candidate rows; new registrations use the TSE protocol. |
| `ano` | Election year, e.g. `2026`. |
| `sigla_uf` | State abbreviation or `ZZ`; blank national scope becomes `BR` during preparation. |
| `cargo` | `presidente` for eligible tracker rows. |
| `data` | Tracker date. New registrations use TSE's `DT_DIVULGACAO`, written as month/day/year. Preserve a consistent parseable format. |
| `instituto` | Canonical institute label from the selected list below. |
| `numero_registro` | TSE registration, e.g. `BR-12345/2026`; used for updater matching. |
| `tipo` | Tracker accepts `estimulada` or `espontânea`; new updater rows are `estimulada`. |
| `turno` | `2` for runoff scenarios. |
| `nome_candidato` | Candidate name; updater uses `Lula` and `Flávio Bolsonaro`. |
| `percentual` | Published numeric percentage, e.g. `45.2`, without `%`; leave missing values blank. |

Retain original fields such as sample size, margins and scenario identifiers even though they are not aggregation weights. Store percentages as published: preparation normalizes them later. Blank is missing data, not zero.

Selected institutes are MDA, Quaest, Datafolha, AtlasIntel/Internet, Paraná Pesquisas, FSB, PoderData, Ideia Big Data, Ipec, Real Time Big Data and Futura. The updater maps selected legal/trading names to these labels, including Nexus to FSB and 100 Cidades to Futura. Unmapped institutes are excluded from new registrations.

Analysis loaders decode source lines as UTF-8 with Windows-1252 fallback. Some updater reads instead use UTF-8 with replacement characters. Avoid unnecessary whole-file encoding conversions and inspect accented candidate/institute names after manual edits.

## Methodology

### 1. Eligible observations and normalization

The loader selects the election year, presidential office, second round, accepted poll types, selected institutes, configured candidate pair and dates no later than the displayed endpoint. Pairs are Dilma/Aécio (2014), Haddad/Bolsonaro (2018), Lula/Bolsonaro (2022) and Lula/Flávio Bolsonaro (2026). The last is a configured scenario, not a statement that the runoff participants are known.

Rows are pivoted by date, geography, year, institute and survey ID. Duplicate candidate observations within these keys are averaged by pandas' pivot operation; `id_cenario` is not a separate key. Both candidates must be present and their sum positive. Incomplete pairs are excluded until completed.

For published percentages `x_A` and `x_B`:

```text
p_A = x_A / (x_A + x_B)
p_B = x_B / (x_A + x_B)
```

Thus 45% and 40% become 52.94% and 47.06%. Undecided, blank and null responses are removed from the denominator. Prepared shares use a 0–1 scale and are multiplied by 100 for display. This normalization does not model how undecided voters will vote.

### 2. Daily polling averages

The calendar begins September 1 and ends on the configured runoff date: October 26, 2014; October 28, 2018; October 30, 2022; or October 25, 2026. The 2026 endpoint is capped at today. These dates are settings in the source code.

Let `d_i,t` be survey age in calendar days on tracker day `t`. Future polls never enter that day's average.

| API method | Eligible surveys | Weight |
| --- | --- | --- |
| `simple` | Age 0–29 days inclusive | Equal per poll |
| `weighted` | Age 0–29 days inclusive | `1 / (d_i,t + 1)` |
| `latest_10` | Ten most recent available same-year surveys, or all if fewer exist | Equal; no age cutoff |

```text
estimate_c,t = sum_i(weight_i,t * p_i,c) / sum_i(weight_i,t)
```

In the weighted rule, same-day weight is 1, one-day-old weight 1/2, and 29-day-old weight 1/30. At age 30 the survey exits. August polls can enter the first September windows. Latest-ten can retain much older polls; stable prepared input order breaks same-day ties.

No eligible polls means a missing polling estimate. The calculation runs independently for national coverage and each state. There is no sample-size weighting, institute-accuracy weighting, margin-of-error weighting or house-effect adjustment. The in-app methodology calls freshness weighting its baseline; the dashboard initially selects latest-ten, while both standalone scripts currently start with `weighted`.

### 3. Filling missing state estimates

The dashboard fills a missing state estimate with that geography's **previous presidential runoff result**. Political sides map positionally: previous PT candidate to current PT candidate, and previous opponent to current opponent. For 2026, the fallback uses Lula/Bolsonaro's 2022 shares for Lula/Flávio Bolsonaro.

Filling applies whenever the selected rule produces no estimate. A 30-day rule can revert to historical shares after the last poll expires. Latest-ten retains an estimate while a prior eligible poll exists. Overseas votes remain included even without overseas polling.

The analysis functions also support `fill_type='national'`, using the same-day national tracker. The dashboard explicitly uses `fill_type='previous'` and has no UI switch for this alternative.

### 4. From states to a national estimate

Each geography has a fixed weight equal to its share of **previous-election valid runoff votes**:

```text
omega_s = previous_valid_votes_s / sum_s(previous_valid_votes_s)
state_aggregate_c,t = sum_s(omega_s * completed_state_share_s,c,t)
```

The sum includes 26 states, DF and `ZZ`. Weights sum to one and stay fixed during the tracking period. They reflect votes cast for the two runoff candidates, not population, registered electorate or survey sample sizes. The resulting estimate combines polling in covered places with historical information elsewhere.

### 5. National polls from shared institutes

The third national line retains institutes with at least one national and one state survey during the displayed September-to-endpoint period, then applies the same rule to their national polls. Earlier eligible observations from those institutes can enter initial windows.

This holds the institute set in common, but does not equalize survey frequency, dates or state coverage. The set is determined over the whole displayed period, not separately each day. Historical versions are descriptive comparisons rather than strictly real-time reconstructions of institute availability.

### 6. Coverage and freshness

Coverage is measured **before historical filling**. Let `I_s,t` indicate an available polling estimate:

```text
coverage_t (%) = 100 * sum_s(omega_s * I_s,t)
freshness_t (days) = sum_s(omega_s * I_s,t * latest_poll_age_s,t)
                    / sum_s(omega_s * I_s,t)
```

Freshness is the voting-weighted age of the latest poll among covered states, not the mean age of every poll entering their trackers. It is missing if no states are covered. Latest-ten coverage can remain high despite old polling, so read freshness alongside coverage.

### 7. Contributions and historical errors

For 2026, each state's contribution to the PT-candidate aggregate's daily movement is:

```text
daily_contribution_s,t (pp) = 100 * omega_s * (share_s,t - share_s,t-1)
```

The first day has no prior observation. The dashboard displays dates with complete contributions and at least one nonzero state movement. Changes may arise from new polls, aging weights, window expiry or historical fallback; they do not necessarily reflect new information about preferences.

For historical elections, let `q_s` denote the actual state share and `v_s` the current-election valid-vote weight:

```text
state_error_s,t (pp) = 100 * omega_s * (share_s,t - q_s)
voting_weight_correction (pp) = 100 * sum_s((omega_s - v_s) * q_s)
national_error_t = sum_s(state_error_s,t) + voting_weight_correction
```

The correction reconciles the previous-election weights used by the tracker with the current-election weights behind the actual national result.

SP, MG, RJ, BA, PR, RS, PE, CE and PA appear separately. **Others** includes all remaining geographies, including overseas. Historical charts also show the weight correction. The backend asserts that components sum to the national change/error within numerical tolerance.

Historical summary cards report signed PT-candidate estimate minus actual national result, in percentage points. Positive means overestimation. The institute table instead reports mean absolute individual-survey errors, with equal survey weights and state surveys compared to their own state's result. Counts and errors cover September through runoff; table filters and August table rows do not alter that period. Survey timing and state composition can differ across institutes.

### Interpretation and limitations

This is a descriptive aggregator, with no probability of victory, confidence interval or explicit turnout forecast. Normalization, fixed voting weights and political-side fallback are substantive assumptions. Sparse state coverage can leave a large historical component in the national estimate. Duplicate scenarios can be averaged together by the preparation keys, and incorrect survey dates distort daily information availability.

Reconstructed 2018/2026 figures and automated extractions can contain errors. Source matching and basic numeric checks do not independently prove that every extracted value or scenario is correct. Preserve provenance and inspect questionable results against original publications.

## Creating an OpenRouter API key

1. Sign in or create an account at [OpenRouter](https://openrouter.ai/).
2. Open [API keys](https://openrouter.ai/settings/keys), choose **Create API Key**, and name it, for example, `poll-tracker`. Review the available limit and expiry settings.
3. Copy the generated key into **`openrouter_api_key.txt` in the project root**, beside `dataset_completer.py`.
4. Save as plain UTF-8 without a byte-order mark. Include only the key: no quotes, `Bearer` prefix, JSON or variable assignment. A final newline is acceptable.

Check that Windows has not named it `openrouter_api_key.txt.txt`. The script reads this file directly: an environment variable or `.env` file alone does not configure it. Keep it out of shared files. Git ignore rules cannot remove a previously committed credential; revoke and replace an exposed key.

The updater calls `https://openrouter.ai/api/v1/chat/completions` through `requests`, using bearer authentication. No OpenAI/OpenRouter SDK is needed. See the [official API quickstart](https://openrouter.ai/docs/quickstart).

The configured model is **`openrouter/free`**, with temperature zero. This routes among available free models; the actual model can change and is logged in `poll_status.csv`. See [OpenRouter's free-router documentation](https://openrouter.ai/docs/guides/routing/routers/free-router).

Free access still has account/request limits and provider-capacity constraints. Check your account and the [official rate-limit documentation](https://openrouter.ai/docs/api_reference/limits) before large runs. The script's local 40-call setting is separate from account quotas. If you change to a paid model, check its price and your key/account limits.

## Updating the dataset

### Routine update

1. Ensure `data/data.csv` exists and the API key is configured.
2. Back up the dataset and status log. These PowerShell commands put timestamped copies beside the project:

   ```powershell
   $backupStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
   Copy-Item -LiteralPath data/data.csv -Destination "../poll-data-$backupStamp.csv"
   if (Test-Path data/poll_status.csv) {
       Copy-Item -LiteralPath data/poll_status.csv -Destination "../poll-status-$backupStamp.csv"
   }
   ```

3. Run one updater process, with no spreadsheet editor writing the same files:

   ```powershell
   & C:/Users/lfval/anaconda3/python.exe dataset_completer.py
   ```

4. Read the summary and inspect `data/poll_status.csv`, particularly `manual_review`, `conflict`, `unresolved` and technical-error notes. Review newly filled numbers against source URLs as needed.
5. Refresh the dashboard after completion. Blank registrations do not enter the tracker until both candidate percentages are available.

There are no command-line options. The updater is configured for 2026, the stimulated Lula/Flávio Bolsonaro runoff scenario, and registrations with `DT_DIVULGACAO` on or after **2026-08-03**. It does not update historical elections or every possible 2026 matchup.

### What each run does

1. **Download metadata:** replace `data/tse.csv` with the current registration extract.
2. **Filter:** keep presidential registrations for mapped institutes after the cutoff and deduplicate by protocol.
3. **Append:** compare registration numbers with `data/data.csv` and create two blank candidate rows for each new registration. Existing registrations are not reappended or refreshed with revised metadata.
4. **Infer scope:** find state abbreviations/geographic phrases in methodology text. Unknown scope defaults to national (`BR`, stored blank). Inspect ambiguous classifications.
5. **Find pending results:** identify missing/unparseable percentages in 2026 presidential runoff rows whose publication date has arrived. Future registrations can be appended but are not searched yet.
6. **Build the queue:** synchronize status entries and select records eligible for retry.
7. **Search:** `ddgs` queries combine registration, institute aliases, candidates and date. URLs are deduplicated and ranked. Exact-registration matches score highest; snippets explicitly identifying another registration are rejected.
8. **Fetch:** attempt the top four nonnegative-score results. Only HTML is extracted, excluding script/style content. PDFs, images, blocked pages and JavaScript-dependent content may supply no evidence. Send up to the first 12,000 extracted characters from each successful page to the model.
9. **Extract:** request JSON with status, both percentages, source URL and reason. Poll metadata and page evidence are sent to OpenRouter and its selected provider. The prompt requires the exact poll and matchup, distinguishing final cancellation from temporary suspension or missing evidence.
10. **Validate and persist:** fill eligible blank cells and record provenance. Completed records are saved throughout the run.

### Validation before writing

Both percentages must parse as numbers between 0 and 100. The source URL must exactly match a fetched page, whose extracted text must contain the target registration after normalization. Both candidate rows must exist. Existing percentages must agree with the extraction; disagreements produce `conflict` rather than an overwrite.

Only blank, `nan` or `none` cells are filled. The updater writes `data/data.tmp.csv` then replaces the original. Its Latin-1 read/write path preserves existing non-ASCII byte encoding of field contents, although CSV serialization may change quoting or line endings. Other rows are retained.

Cancellation also requires a supplied source containing the exact registration; the model interprets whether non-publication/cancellation is final. Failure to find runoff numbers remains `not_found`, not proof that no scenario existed. The implementation does not independently check the sum of extracted percentages or cross-verify numbers across publications.

### Retry rules and run limits

Only `pending` and `not_found` registrations with missing data are automatically searched. Never-checked records can run immediately. Polls aged 0–5 days wait six hours after a previous check; those aged six or more wait 24 hours. An unsuccessful search becomes `unresolved` when the poll is **more than eight days old** and has **at least three unsuccessful attempts**.

Technical failures and results with no extractable pages remain `pending`, with an updated check timestamp; these do not increment unsuccessful-result counts. Legacy `no_runoff` statuses reopen as `pending` during synchronization.

The main block sets `MAX_AI_CALLS_PER_RUN = 40` and pauses two seconds between polls. The counter increments only after AI analysis returns successfully. Failed HTTP calls or malformed responses can consume provider quota without increasing that counter. It is a local processing limit, not an exact request/billing cap. An immediate rerun does not bypass retry timestamps.

## Reviewing and correcting results

`data/poll_status.csv` records `numero_registro`, `result_status`, `last_checked`, `source_url`, `source_type`, `ai_model`, `notes` and `attempt_count`. Notes hold the model response or technical/validation explanation.

| Status | Meaning | Automatic retry? |
| --- | --- | --- |
| `pending` | New record, technical error or inaccessible evidence | When due |
| `not_found` | Requested result not established | When due |
| `found` | Passed implemented checks | No |
| `cancelled` | Cancellation passed source/registration checks | No |
| `manual_review` | Numeric, source or candidate-row problem | No |
| `conflict` | Extracted value differs from existing data | No |
| `unresolved` | Age/unsuccessful-attempt threshold reached | No |

For a correction, find the registration in both CSVs and check the original publication's institute, scope, date and exact runoff scenario. Edit candidate percentages in `data/data.csv`, retaining survey identifiers and the published percentage scale. Record the source and explanation in the status log; for manually completed results, `found` with `source_type` set to `manual` is a useful convention.

To deliberately reopen an incomplete record, set status to `pending` and clear `last_checked`. Reset `attempt_count` to zero if a fresh sequence is intended, preserving useful evidence in notes. A fully populated poll does not re-enter the queue just because its status changes: queue construction begins with missing percentages. Review and correct wrong existing values directly rather than expecting automatic overwrites.

Keep registration numbers as text; avoid spreadsheet conversion of dates and identifiers. Save without an extra index column. If an entire candidate row is absent, add it with matching survey metadata: the updater does not repair this structure automatically.

## Configuration and maintenance

| Setting | Location |
| --- | --- |
| Tracker pollsters | `SELECTED_INSTITUTES` in both analysis modules |
| TSE institute mapping/search aliases | `mapa_institutos_2026` / `SEARCH_NAMES` in updater |
| Registration cutoff / AI-call limit | Updater's main block |
| Model, prompt, timeout | `analyze_pages_with_ai` |
| Retry intervals / unresolved threshold | `get_polls_to_search` / `record_not_found` |
| Election dates and candidates | `ELECTIONS` / `election_settings` in analysis modules |
| Dashboard years, methods, contribution states | `app.py` and matching frontend controls |
| In-app methodology | `tracker_web/methodology.html` |

A new election or scenario can require coordinated changes to preparation, updater and frontend controls; it is not inferred automatically. Keep both analysis implementations and the in-app text consistent with this guide.

Standalone analysis is available from the project root:

```powershell
python eleicoes2026.py
python avaliacao.py
```

These print summaries and display Matplotlib figures. Their main blocks currently select 2026 and 2022 respectively, both with freshness weighting. The web app reuses their functions and closes diagnostic figures after preparing dashboard data.

### Local API

```text
GET /api/dashboard?year=2026&method=latest_10
```

Years: `2014`, `2018`, `2022`, `2026`. Methods: `simple`, `latest_10`, `weighted`. Defaults: 2026/latest-ten. Responses include candidates, dates, daily national series, completed states, shared institutes, contributions, surveys, historical performance and actual results where available. Unsupported values return HTTP 400; calculation errors return HTTP 500 with details in the terminal. `/` serves the dashboard and `/plotly.js` serves the installed Plotly bundle.

## Checks and troubleshooting

A quick import check that does not update data or call OpenRouter:

```powershell
python -c "import app, dataset_completer; print('Imports OK')"
```

If local tests are available:

```powershell
python -m unittest discover -s tests -p 'test_*.py'
```

Backend tests cover election/method combinations and contribution reconciliation and can require TSE archives. With the server running and Node installed, the optional frontend check is:

```powershell
node tests/test_tracker_frontend.cjs
```

This uses a mocked DOM/Plotly recorder; it is not a visual browser test. Because `tests/` is ignored, a fresh checkout may not contain the checks. Node is unnecessary for ordinary dashboard use.

| Symptom | What to check |
| --- | --- |
| Python not found | Use the explicit Anaconda/virtual-environment executable instead of the Windows Store alias. |
| Missing module | Install requirements with the same interpreter used to run the project; updater requires `ddgs`. |
| Missing main CSV | Restore `data/data.csv`; registration downloads do not recreate historical polling data. |
| Slow first request | Check terminal output, TSE downloads, internet and temporary-directory space. |
| Dashboard HTTP 500 | Inspect traceback, CSV headers/dates/candidate names, complete pairs and archive integrity. |
| Missing/empty API key | Use the exact root-level filename and raw UTF-8 key. Validation occurs when the AI stage is reached. |
| API authentication/quota/rate error | Check key, account usage and provider availability; technical failures stay pending. |
| Non-JSON/empty model output | Inspect recorded error/model; free-router providers can vary. |
| No searches on rerun | Check missing values, publication dates, status and six-/24-hour deadlines. |
| New poll absent from charts | Both candidate values are required; verify institute, scope, date and window. |
| Incorrect state/national classification | Review `infer_uf`; ambiguous scope defaults to national. |
| Old dashboard values | Save the correct dataset and Refresh; restart after Python changes. |
| Port 5000 occupied | Stop the previous server or change `app.py`'s port and browser URL. |

After an update, inspect national estimates, several states, coverage and recent survey rows together. A change in state coverage is analytically different from a new national poll even when both happen on the same date.
