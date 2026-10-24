# Weekly public provider plan

Owner: Platform; source revision: eb93edd. Implementation is confined to public
projection, file validation, import/export and snapshot handoff. Research owners
remain authoritative for facts and series.

1. Define the strict weekly v1 contract and synthetic boundary tests.
2. Export only explicitly approved public Markdown, bounded PNG and admitted owner facts.
3. Stage and validate imports before replacing the public directory. Retain five weekly
   dates and preserve daily assets; preserve weekly assets through daily imports/pruning.
4. Include validated weekly records and bound files in site snapshots.
5. Run the full repository gate, independent integration review, then push and open PR.
   Provider must merge before consumers pin; production remains a separate operation.

Validation evidence is recorded in the PR. Initial pytest environment setup failed
because the restricted uv cache/network was unavailable; locked sync used the approved
escalated network path. A malformed timestamp test then failed with TypeError before
its validator correction, establishing the fail-closed regression.
