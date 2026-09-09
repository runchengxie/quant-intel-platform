# Parity run evidence

Store one generated comparison manifest per source/signal-date pair here.
Each manifest should be accompanied by the frozen input snapshot reference and
the commits for both implementations. A clean run has
`unexplained_differences: false` and exit status zero.

The comparator normalizes only fields explicitly scoped as artifact paths. The
default `paths` mapping compares path values by basename, so different runtime
roots do not create noise while the referenced artifact name remains part of
the contract. Add other mappings with `--path-field`; do not use broad ignored
fields to hide business data.
