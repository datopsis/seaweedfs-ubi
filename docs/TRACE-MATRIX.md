# SeaweedFS UBI requirement trace matrix

**Generated; do not edit.** Run `python scripts/build-trace-matrix.py` to regenerate.
CI checks for drift and broken links. It does not require all gaps to be closed yet.

Python method and selected shell-suite markers are indexed. Shell markers
identify entire suites, not particular assertions. Other shell suites and
manual assessment records are not indexed yet; a missing link
may mean existing evidence has not been traced, not that no test exists.

A test link means only that a named test is intended to verify the stated
behavior. It is not a passing test result, a release-candidate assessment,
or evidence for another architecture, role, topology, or platform.
`Decomposed` means a child exists, not that the parent is satisfied.
Manual methods need separately reviewed evidence in the qualification ledger.

## Initial trace state

| Measure | Count |
| --- | ---: |
| L1 / L2 / L3 requirements | 9 / 17 / 14 |
| Leaf requirements linked to a test | 8 |
| Testable leaves missing a test link | 8 |
| Leaves awaiting manual evidence | 3 |

## L1 requirements

| ID | Parent | Methods | Test links | Trace state |
| --- | --- | --- | --- | --- |
| `L1-API-001` | — | Test, Analysis | — | decomposed |
| `L1-CFG-001` | — | Test | — | decomposed |
| `L1-DAT-001` | — | Test, Demonstration | — | decomposed |
| `L1-EVD-001` | — | Test, Inspection | — | decomposed |
| `L1-INT-001` | — | Test, Demonstration | — | decomposed |
| `L1-OBS-001` | — | Test, Demonstration | — | decomposed |
| `L1-REL-001` | — | Test, Inspection, Demonstration | — | decomposed |
| `L1-RUN-001` | — | Test | — | decomposed |
| `L1-SUP-001` | — | Test, Analysis | — | decomposed |

## L2 requirements

| ID | Parent | Methods | Test links | Trace state |
| --- | --- | --- | --- | --- |
| `L2-API-001` | `L1-API-001` | Test, Analysis | — | decomposed |
| `L2-CFG-001` | `L1-CFG-001` | Test | — | decomposed |
| `L2-CFG-002` | `L1-CFG-001` | Test | — | decomposed |
| `L2-CFG-003` | `L1-CFG-001` | Test | — | missing test link |
| `L2-DAT-001` | `L1-DAT-001` | Test | — | decomposed |
| `L2-DAT-002` | `L1-DAT-001` | Demonstration | — | manual evidence pending |
| `L2-EVD-001` | `L1-EVD-001` | Test, Inspection | — | decomposed |
| `L2-EVD-002` | `L1-EVD-001` | Inspection | — | manual evidence pending |
| `L2-INT-001` | `L1-INT-001` | Test | — | decomposed |
| `L2-INT-002` | `L1-INT-001` | Demonstration | — | manual evidence pending |
| `L2-OBS-001` | `L1-OBS-001` | Test, Demonstration | — | decomposed |
| `L2-REL-001` | `L1-REL-001` | Test | — | decomposed |
| `L2-REL-002` | `L1-REL-001` | Test, Inspection, Demonstration | — | missing test link |
| `L2-RUN-001` | `L1-RUN-001` | Test | — | decomposed |
| `L2-RUN-002` | `L1-RUN-001` | Test | — | decomposed |
| `L2-SUP-001` | `L1-SUP-001` | Test, Analysis | — | decomposed |
| `L2-SUP-002` | `L1-SUP-001` | Test | — | decomposed |

## L3 requirements

| ID | Parent | Methods | Test links | Trace state |
| --- | --- | --- | --- | --- |
| `L3-API-001` | `L2-API-001` | Test | `tests/s3.sh:130 (main suite)` | test linked |
| `L3-CFG-001` | `L2-CFG-001` | Test | — | missing test link |
| `L3-CFG-002` | `L2-CFG-002` | Test | — | missing test link |
| `L3-DAT-001` | `L2-DAT-001` | Test | `tests/test_backup_validation.py:52 (test_refuses_parent_traversal)`<br>`tests/test_backup_validation.py:57 (test_refuses_an_absolute_path)`<br>`tests/test_backup_validation.py:62 (test_refuses_a_symbolic_link)` | test linked |
| `L3-EVD-001` | `L2-EVD-001` | Test | `tests/test_spdxchecks.py:31 (test_accepts_seaweedfs_and_go_inventory)`<br>`tests/test_spdxchecks.py:43 (test_refuses_missing_go_inventory)`<br>`tests/test_spdxchecks.py:50 (test_refuses_missing_seaweedfs)`<br>`tests/test_spdxchecks.py:57 (test_refuses_main_module_without_dependencies)` | test linked |
| `L3-EVD-002` | `L2-EVD-001` | Test | `tests/test_trivychecks.py:41 (test_accepts_image_os_and_language_coverage)`<br>`tests/test_trivychecks.py:63 (test_refuses_missing_os)`<br>`tests/test_trivychecks.py:70 (test_refuses_missing_language_coverage)` | test linked |
| `L3-EVD-003` | `L2-EVD-001` | Test | `tests/test_govulnchecks.py:34 (test_accepts_clean_scan_without_turning_inventory_into_gate)`<br>`tests/test_govulnchecks.py:44 (test_rejects_missing_database_timestamp)`<br>`tests/test_govulnchecks.py:55 (test_rejects_wrong_tool_version)` | test linked |
| `L3-INT-001` | `L2-INT-001` | Test | `tests/inter-component.sh:287 (main suite)` | test linked |
| `L3-OBS-001` | `L2-OBS-001` | Test | `tests/test_listening_ports.py:11 (test_decodes_ipv4_and_ipv6_listeners_and_sorts_them)`<br>`tests/test_listening_ports.py:22 (test_empty_and_non_listening_input_has_no_ports)` | test linked |
| `L3-REL-001` | `L2-REL-001` | Test | `tests/test_release_tag_validation.py:108 (test_refuses_version_not_in_artifact_lock)`<br>`tests/test_release_tag_validation.py:117 (test_refuses_disagreeing_base_majors)`<br>`tests/test_release_tag_validation.py:135 (test_refuses_unpinned_base)`<br>`tests/test_release_tag_validation.py:141 (test_refuses_reused_immutable_tag)`<br>`tests/test_release_tag_validation.py:147 (test_refuses_skipped_or_filled_sequence)`<br>`tests/test_release_tag_validation.py:69 (test_refuses_malformed_tags)`<br>`tests/test_release_tag_validation.py:89 (test_refuses_backdated_or_future_date)` | test linked |
| `L3-RUN-001` | `L2-RUN-001` | Test | — | missing test link |
| `L3-RUN-002` | `L2-RUN-002` | Test | — | missing test link |
| `L3-SUP-001` | `L2-SUP-001` | Test | — | missing test link |
| `L3-SUP-002` | `L2-SUP-002` | Test | — | missing test link |
