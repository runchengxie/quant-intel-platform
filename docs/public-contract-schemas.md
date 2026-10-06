# Public contract schemas

The JSON Schema files under `schemas/public/` are the language neutral description of the two public handoff shapes currently consumed outside the Python package:

- `market-intel-a-share-charts.v1.json` describes reviewed chart payloads consumed by the Astro site in `quant-intel-pages`.
- `research-platform-publication.v1.json` describes publication manifests exchanged between research owners and presentation or distribution consumers.

The Python validators remain the enforcement point for producer side rules such as public URL host checks, content hash calculation, exact chart key sets, and the relationship between `report_id`, `date`, and `kind`. Consumers must still validate at runtime; generated TypeScript types do not validate JSON.

When a field changes, update the schema, the Python contract test, and consumer types together. Increment the schema version for incompatible changes.
