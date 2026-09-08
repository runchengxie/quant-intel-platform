#!/usr/bin/env bash
set -euo pipefail

repo=""
report=""
while (($#)); do
    case "$1" in
        --repo)
            repo="${2:-}"
            shift 2
            ;;
        --report)
            report="${2:-}"
            shift 2
            ;;
        *)
            echo "unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

if [[ -z "$repo" || -z "$report" ]]; then
    echo "--repo and --report are required" >&2
    exit 2
fi
repo=$(realpath "$repo")
git -C "$repo" rev-parse --git-dir >/dev/null
report=$(realpath -m "$report")
mkdir -p "$(dirname "$report")"
: > "$report"

markers=(
    "fast.xiaodefa.cn"
    "my.feishu.cn/docx/"
    "kaichuan"
    "凯川"
    "token_label"
    "-----BEGIN PRIVATE KEY-----"
    "-----BEGIN RSA PRIVATE KEY-----"
    "ghp_"
    "xoxb-"
)
patterns=(
    'AKIA[0-9A-Z]{16}'
    'AIza[0-9A-Za-z_-]{20,}'
)
safe_fixture_paths=(
    "."
    ":(exclude)scripts/public_release/**"
    ":(exclude)tests/public_release/**"
)

findings=0
while read -r commit; do
    for marker in "${markers[@]}"; do
        if files=$(git -C "$repo" grep -Iil -F "$marker" "$commit" -- "${safe_fixture_paths[@]}" 2>/dev/null); then
            while read -r file; do
                [[ -z "$file" ]] && continue
                printf 'private marker: commit=%s marker=%s file=%s\n' "$commit" "$marker" "$file" >> "$report"
                findings=$((findings + 1))
            done <<< "$files"
        fi
    done
    for pattern in "${patterns[@]}"; do
        if files=$(git -C "$repo" grep -Iil -E "$pattern" "$commit" -- "${safe_fixture_paths[@]}" 2>/dev/null); then
            while read -r file; do
                [[ -z "$file" ]] && continue
                printf 'private pattern: commit=%s pattern=%s file=%s\n' "$commit" "$pattern" "$file" >> "$report"
                findings=$((findings + 1))
            done <<< "$files"
        fi
    done
done < <(git -C "$repo" rev-list --all)

if command -v gitleaks >/dev/null 2>&1; then
    gitleaks_output=$(mktemp)
    trap 'rm -f "$gitleaks_output"' EXIT
    if ! gitleaks git --redact --no-banner --exit-code 1 "$repo" >"$gitleaks_output" 2>&1; then
        echo "gitleaks: findings reported by scanner" >> "$report"
        findings=$((findings + 1))
    else
        echo "gitleaks: clean" >> "$report"
    fi
else
    echo "gitleaks: not installed; marker scan completed" >> "$report"
fi

if ((findings > 0)); then
    echo "history audit failed; see redacted report: $report" >&2
    exit 1
fi
echo "history audit passed; see report: $report"
