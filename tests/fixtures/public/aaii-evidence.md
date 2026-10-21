AAII regression evidence
========================

The small HTML strings in `test_aaii_survey_evidence.py` are reconstructed
semantic fixtures, not captured production HTML. The prior insights fixture in
`test_sentiment_fetchers.py` was also synthetic and is now explicitly dated and
scoped to a current-results block. Passing these fixtures does not establish
live insights markup compatibility.

The official AAII article dated 2026-10-15 separates current results
(38.7 / 19.7 / 41.6) from historical averages (37.5 / 31.0 / 31.5):
https://www.aaii.com/latest/article/553747-aaii-sentiment-survey-pessimism-rises

The official index identifies the current observation week as ending 2026-10-14:
https://www.aaii.com/sentimentsurvey

A separately authorized direct GET returned HTTP 403, so actual raw article HTML
and live insights compatibility are unverified. Its preserved error-body SHA256
is 4adf71c734187ed20a9d09750d8aa50dc931de7df7f7b148a671dcf349394f18.
No whole article HTML is distributed in this repository. Missing evidence causes
failure or an explicit unknown date rather than a fabricated current date.
