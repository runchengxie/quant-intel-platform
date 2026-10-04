import copy
import json

import pytest

from market_intel_publication.us_news_contract import validate_news_revision
from tests.daily_report.test_news_revision import inputs, revision


@pytest.mark.parametrize("replacement", [True, 1])
def test_revision_rejects_json_type_changes(tmp_path, replacement):
    paths = inputs(tmp_path)
    result = revision(paths, tmp_path / "stage")
    original = json.loads(paths[0].read_text())
    revised = json.loads(result.artifact_path.read_text())
    original["facts"][0]["retained_vendor_metadata"]["number"] = 1.0
    revised["facts"][0]["retained_vendor_metadata"]["number"] = replacement
    with pytest.raises(ValueError, match="market facts"):
        validate_news_revision(
            original,
            revised,
            original_sha256=revised["quality_summary"]["news_revision"]["input_report_sha256"],
        )


def test_revision_rejects_duplicate_only_claims(tmp_path):
    paths = inputs(tmp_path)
    result = revision(paths, tmp_path / "stage")
    original = json.loads(paths[0].read_text())
    revised = json.loads(result.artifact_path.read_text())
    original["claims"] = copy.deepcopy(revised["claims"])
    revised["claims"] = original["claims"] + copy.deepcopy(original["claims"])
    with pytest.raises(ValueError, match="new claims"):
        validate_news_revision(
            original,
            revised,
            original_sha256=revised["quality_summary"]["news_revision"]["input_report_sha256"],
        )
