# Production parity fixtures

Fixtures in this directory are redacted, deterministic JSON artifacts captured
from a production run or a frozen replay input. They must not contain secrets,
Feishu message IDs, access tokens, or personally identifying information.

Each fixture set should include:

- the source and signal dates;
- the producing repository commit and data snapshot identifier;
- the artifact schema version;
- an expected artifact and, when useful, an actual replay artifact;
- a short note describing allowed differences such as generated timestamps.

Use `parity.compare.compare_artifacts` for comparisons. Keep generated times
and delivery message IDs ignored by default, while dates, statuses, counts,
receipt identity, and file inventories remain mandatory comparisons.
