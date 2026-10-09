# Delivery and recovery assurance

Report sends persist an intent before invoking each Lark, Hermes or webhook target.
Text and image artifacts have separate identities. Confirmed targets are skipped
on retry. An interrupted send or missing acknowledgement is an unknown outcome,
so retry does not invoke that target automatically. Existing successful v1 report
receipts retain their whole-report skip behavior.

The intent database stores recipient hashes, artifact fingerprints and message IDs,
not raw recipient addresses or webhook credentials. It belongs in the owner data
root. `A_SHARE_DELIVERY_INTENT_ROOT` can specify an explicit external directory.
After checking the actual worker and provider, resolve one intent with evidence:

```bash
a-share-daily delivery-resolve --root "$intent_root" --key "$intent_key" --outcome sent --evidence 'Provider message verified'
a-share-daily delivery-resolve --root "$intent_root" --key "$intent_key" --outcome not_sent --evidence 'Worker stopped and provider verified absence'
```

`not_sent` permits one new attempt; `sent` confirms delivery. Stop any original
sender before resolving an unknown intent. A provider without lookup support
requires operator verification. This mechanism does not guarantee exactly-once
delivery across an external provider and the local database.

Business freshness compares expected and actual report dates and requires valid
delivery receipts. A zero subprocess exit cannot override an explicit unknown
outcome. Corrupted receipts and wrong dates remain stale. Synthetic tests exercise
acknowledgement failure, partial targets, explicit resolution and recovery cleanup;
they do not send real messages or change schedules.
