"""Static safety contract for Echo's public release workflow."""
from __future__ import annotations

import pathlib
import re
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
CONTRACT_WORKFLOW = (ROOT / ".github/workflows/release-contract.yml").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")
POLICY = ROOT / "scripts" / "release_policy.sh"


class ReleaseWorkflowContract(unittest.TestCase):
    def test_matrix_uploads_only_to_reserved_release_id(self) -> None:
        self.assertIn("reserve:\n    needs: prepare", WORKFLOW)
        self.assertIn("releaseId: ${{ needs.reserve.outputs.release_id }}", WORKFLOW)
        self.assertNotIn('releaseName: "Echo ${{ needs.prepare.outputs.tag }}"', WORKFLOW)
        self.assertRegex(
            WORKFLOW,
            r"build:\n\s+needs: \[prepare, reserve\]",
        )

    def test_same_tag_reservation_is_serialized_and_duplicate_safe(self) -> None:
        self.assertIn("group: echo-release-${{ needs.prepare.outputs.tag }}", WORKFLOW)
        self.assertIn("if [ \"$count\" -gt 1 ]; then", WORKFLOW)
        self.assertIn("release reservation lost its invariant", WORKFLOW)
        self.assertIn("refusing ambiguous publish", WORKFLOW)

    def test_all_triggers_share_one_full_workflow_lock(self) -> None:
        workflow_header = WORKFLOW.split("\njobs:\n", 1)[0]
        self.assertRegex(
            workflow_header,
            r"\nconcurrency:\n\s+group: echo-release-build\n\s+cancel-in-progress: false\n",
        )

    def test_release_discovery_retries_eventual_consistency_without_losing_fail_closed(self) -> None:
        self.assertIn("release discovery settle $visibility_attempt/4", WORKFLOW)
        self.assertIn("for visibility_attempt in $(seq 1 10)", WORKFLOW)
        self.assertIn('direct=$(gh api "repos/$REPO/releases/$id")', WORKFLOW)
        self.assertIn('-f tag_name="$TAG" -f name="Echo $TAG"', WORKFLOW)
        self.assertIn("reservation_ok=0", WORKFLOW)
        self.assertIn("after bounded retry", WORKFLOW)

    def test_publish_uses_exact_id_and_separates_stable_from_draft_rc(self) -> None:
        self.assertIn('rel=$(gh api "repos/$repo/releases/$id")', WORKFLOW)
        self.assertNotIn('select(.tag_name==\\"$tag\\")][0]', WORKFLOW)
        self.assertIn("-F draft=false -F prerelease=false -f make_latest=true", WORKFLOW)
        self.assertIn('if [ "$mode" = "draft_rc" ]; then', WORKFLOW)
        self.assertIn("retained as private draft", WORKFLOW)
        self.assertIn("RC release $id escaped its draft/prerelease boundary", WORKFLOW)
        self.assertIn("prerelease: ${{ needs.prepare.outputs.prerelease == 'true' }}", WORKFLOW)

    def test_schedule_ignores_suffix_tags_and_docs_match(self) -> None:
        self.assertIn("grep -E '^v[0-9]+\\.[0-9]+\\.[0-9]+$'", WORKFLOW)
        self.assertIn("Automatische Poller bauen ausschließlich suffixlose Stable-Tags", README)
        self.assertIn("niemals `Latest`", README)

    def test_only_one_component_can_create_a_release(self) -> None:
        creates = re.findall(r'repos/\$REPO/releases"', WORKFLOW)
        self.assertEqual(len(creates), 1, "only reserve may POST a release")

    def test_policy_changes_always_trigger_contract_ci(self) -> None:
        self.assertEqual(CONTRACT_WORKFLOW.count('"scripts/release_policy.sh"'), 2)


class ReleasePolicyContract(unittest.TestCase):
    def run_policy(self, event: str, ref: str, tag: str, mode: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(POLICY), event, ref, tag, mode],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_manual_stable_and_draft_rc_are_accepted(self) -> None:
        stable = self.run_policy("workflow_dispatch", "v0.5.166", "v0.5.166", "stable")
        self.assertEqual(stable.returncode, 0, stable.stderr)
        self.assertEqual(stable.stdout, "release_mode=stable\nprerelease=false\n")

        rc = self.run_policy("workflow_dispatch", "v0.5.166-rc.1", "v0.5.166-rc.1", "draft_rc")
        self.assertEqual(rc.returncode, 0, rc.stderr)
        self.assertEqual(rc.stdout, "release_mode=draft_rc\nprerelease=true\n")

    def test_automation_cannot_select_draft_rc(self) -> None:
        for event in ("schedule", "repository_dispatch", "push", ""):
            with self.subTest(event=event):
                result = self.run_policy(event, "v0.5.166-rc.1", "v0.5.166-rc.1", "draft_rc")
                self.assertNotEqual(result.returncode, 0)

    def test_stable_rejects_suffixes_and_malformed_values(self) -> None:
        cases = (
            ("v0.5.166-rc.1", "v0.5.166-rc.1"),
            ("v0.5.166", "v0.5.166-rc.1"),
            ("v0.5.166;touch-pwned", "v0.5.166"),
            ("", "v0.5.166"),
            ("v0.5", "v0.5"),
        )
        for ref, tag in cases:
            with self.subTest(ref=ref, tag=tag):
                result = self.run_policy("workflow_dispatch", ref, tag, "stable")
                self.assertNotEqual(result.returncode, 0)

    def test_draft_rc_rejects_wrong_shape_or_mismatched_tag(self) -> None:
        cases = (
            ("v0.5.166", "v0.5.166"),
            ("v0.5.166-alpha.1", "v0.5.166-alpha.1"),
            ("v0.5.166-rc.0", "v0.5.166-rc.0"),
            ("v0.5.166-RC.1", "v0.5.166-RC.1"),
            ("v0.5.166-rc.1", "v0.5.166-rc.2"),
            ("v0.5.166-rc.1\nforged", "v0.5.166-rc.1\nforged"),
        )
        for ref, tag in cases:
            with self.subTest(ref=ref, tag=tag):
                result = self.run_policy("workflow_dispatch", ref, tag, "draft_rc")
                self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
