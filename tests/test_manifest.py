import copy

import pytest
import yaml

from lio_benchmark.manifest import ManifestError, load_manifest
from lio_benchmark.paths import manifest_path


@pytest.fixture
def raw():
    return yaml.safe_load(manifest_path().read_text())


def write(tmp_path, raw):
    p = tmp_path / "m.yaml"
    p.write_text(yaml.safe_dump(raw))
    return p


def test_repository_manifest_is_valid():
    m = load_manifest()
    assert len(m.revision) == 40
    for f in m.files:
        assert f.size > 0 and f.digest
        assert f"/resolve/{m.revision}/{f.path}" in m.url(f)
    assert set(m.split["tune"]) == {"exp14"}
    assert set(m.split["heldout"]) == {"exp16", "exp18"}
    assert not set(m.split["tune"]) & set(m.split["heldout"])


def test_bags_use_sha256_and_small_files_use_blob_sha1():
    m = load_manifest()
    for f in m.files:
        expected = "sha256" if f.size > 10_000_000 else "git_blob_sha1"
        assert f.algorithm == expected, f.path


def test_opt_in_groups_not_default():
    m = load_manifest()
    assert "reference_scan" not in m.default_groups and "cad" not in m.default_groups
    assert {f.path for f in m.select(["seq:exp16"])} == {"rosbags/exp16_attic_to_upper_gallery_2.bag"}


def test_rejects_overlapping_split(tmp_path, raw):
    raw["split"]["heldout"].append("exp14")
    with pytest.raises(ManifestError, match="overlap"):
        load_manifest(write(tmp_path, raw))


def test_rejects_malformed_digest(tmp_path, raw):
    raw["files"][0]["hash"] = {"sha256": "abc"}
    with pytest.raises(ManifestError, match="malformed"):
        load_manifest(write(tmp_path, raw))


def test_rejects_path_escape(tmp_path, raw):
    bad = copy.deepcopy(raw["files"][0])
    bad["path"] = "../outside.txt"
    raw["files"].append(bad)
    with pytest.raises(ManifestError, match="relative"):
        load_manifest(write(tmp_path, raw))


def test_rejects_sequence_file_missing_from_files(tmp_path, raw):
    raw["files"] = [f for f in raw["files"] if f["path"] != raw["sequences"]["exp18"]["bag"]]
    with pytest.raises(ManifestError, match="not listed"):
        load_manifest(write(tmp_path, raw))


def test_unknown_group_selection():
    with pytest.raises(ManifestError, match="unknown groups"):
        load_manifest().select(["seq:exp99"])
