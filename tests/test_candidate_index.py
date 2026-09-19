"""Candidate OCI index identity refuses unbound or wrong-platform manifests."""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
from validate_candidate_index import CandidateIndexError, validate  # noqa: E402


def encoded(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def fixture() -> tuple[bytes, dict[str, bytes], dict[str, bytes], dict[str, str]]:
    children = {}
    configs = {}
    for architecture in ("amd64", "arm64"):
        configs[architecture] = encoded(
            {
                "os": "linux",
                "architecture": architecture,
                "rootfs": {"type": "layers", "diff_ids": ["sha256:" + "c" * 64]},
            }
        )
        children[architecture] = encoded(
            {
                "schemaVersion": 2,
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "config": {
                    "mediaType": "application/vnd.oci.image.config.v1+json",
                    "digest": digest(configs[architecture]),
                    "size": len(configs[architecture]),
                },
                "layers": [
                    {
                        "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
                        "digest": "sha256:" + "b" * 64,
                        "size": 200,
                    }
                ],
            }
        )
    child_digests = {architecture: digest(value) for architecture, value in children.items()}
    index = encoded(
        {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "manifests": [
                {
                    "mediaType": "application/vnd.oci.image.manifest.v1+json",
                    "digest": child_digests[architecture],
                    "size": len(children[architecture]),
                    "platform": {"os": "linux", "architecture": architecture},
                }
                for architecture in ("amd64", "arm64")
            ],
        }
    )
    return index, children, configs, child_digests


class CandidateIndexTests(unittest.TestCase):
    def test_exact_two_platform_index_is_bound(self) -> None:
        index, children, configs, child_digests = fixture()
        self.assertEqual(
            validate(index, digest(index), children, configs, child_digests),
            {"indexDigest": digest(index), "manifests": child_digests},
        )

    def test_wrong_index_digest_and_tampered_child_are_refused(self) -> None:
        index, children, configs, child_digests = fixture()
        with self.assertRaisesRegex(CandidateIndexError, "index bytes"):
            validate(index, "sha256:" + "0" * 64, children, configs, child_digests)
        children["arm64"] += b" "
        with self.assertRaisesRegex(CandidateIndexError, "byte size"):
            validate(index, digest(index), children, configs, child_digests)

    def test_digest_match_does_not_excuse_wrong_child_size(self) -> None:
        index, children, configs, child_digests = fixture()
        document = json.loads(index)
        document["manifests"][0]["size"] += 1
        altered = encoded(document)
        with self.assertRaisesRegex(CandidateIndexError, "byte size"):
            validate(altered, digest(altered), children, configs, child_digests)

    def test_duplicate_or_extra_platform_is_refused(self) -> None:
        index, children, configs, child_digests = fixture()
        document = json.loads(index)
        document["manifests"][1]["platform"]["architecture"] = "amd64"
        altered = encoded(document)
        with self.assertRaisesRegex(CandidateIndexError, "duplicate platform"):
            validate(altered, digest(altered), children, configs, child_digests)
        document = json.loads(index)
        document["manifests"].append(copy.deepcopy(document["manifests"][0]))
        altered = encoded(document)
        with self.assertRaisesRegex(CandidateIndexError, "exactly two"):
            validate(altered, digest(altered), children, configs, child_digests)

    def test_wrong_platform_metadata_is_refused(self) -> None:
        index, children, configs, child_digests = fixture()
        document = json.loads(index)
        document["manifests"][0]["platform"]["variant"] = "v8"
        altered = encoded(document)
        with self.assertRaisesRegex(CandidateIndexError, "exact OS/architecture"):
            validate(altered, digest(altered), children, configs, child_digests)

    def test_artifact_manifest_is_refused(self) -> None:
        index, children, configs, child_digests = fixture()
        arm64 = json.loads(children["arm64"])
        arm64["artifactType"] = "example"
        children["arm64"] = encoded(arm64)
        child_digests["arm64"] = digest(children["arm64"])
        document = json.loads(index)
        document["manifests"][1]["digest"] = child_digests["arm64"]
        document["manifests"][1]["size"] = len(children["arm64"])
        altered = encoded(document)
        with self.assertRaisesRegex(CandidateIndexError, "artifact"):
            validate(altered, digest(altered), children, configs, child_digests)

    def test_wrong_claimed_child_digest_is_refused(self) -> None:
        index, children, configs, child_digests = fixture()
        child_digests["amd64"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(CandidateIndexError, "disagrees"):
            validate(index, digest(index), children, configs, child_digests)

    def test_config_architecture_must_agree_with_index(self) -> None:
        index, children, configs, child_digests = fixture()
        configs["arm64"] = configs["amd64"]
        with self.assertRaisesRegex(CandidateIndexError, "config byte size|config bytes|config platform"):
            validate(index, digest(index), children, configs, child_digests)

    def test_duplicate_json_key_is_refused_even_with_matching_digest(self) -> None:
        index, children, configs, child_digests = fixture()
        altered = index.replace(b'"schemaVersion":2}', b'"schemaVersion":2,"schemaVersion":2}')
        with self.assertRaisesRegex(CandidateIndexError, "duplicate JSON key"):
            validate(altered, digest(altered), children, configs, child_digests)

    def test_config_rootfs_layer_count_must_match_manifest(self) -> None:
        index, children, configs, child_digests = fixture()
        config = json.loads(configs["amd64"])
        config["rootfs"]["diff_ids"] = []
        configs["amd64"] = encoded(config)
        child = json.loads(children["amd64"])
        child["config"]["digest"] = digest(configs["amd64"])
        child["config"]["size"] = len(configs["amd64"])
        children["amd64"] = encoded(child)
        child_digests["amd64"] = digest(children["amd64"])
        document = json.loads(index)
        document["manifests"][0]["digest"] = child_digests["amd64"]
        document["manifests"][0]["size"] = len(children["amd64"])
        altered = encoded(document)
        with self.assertRaisesRegex(CandidateIndexError, "layer count"):
            validate(altered, digest(altered), children, configs, child_digests)


if __name__ == "__main__":
    unittest.main()
