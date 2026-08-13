"""Static safety contract for Echo's public release workflow."""
from __future__ import annotations

import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


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

    def test_release_discovery_retries_eventual_consistency_without_losing_fail_closed(self) -> None:
        self.assertIn("release discovery settle $visibility_attempt/4", WORKFLOW)
        self.assertIn("for visibility_attempt in $(seq 1 10)", WORKFLOW)
        self.assertIn('direct=$(gh api "repos/$REPO/releases/$id")', WORKFLOW)
        self.assertIn('-f tag_name="$TAG" -f name="Echo $TAG"', WORKFLOW)
        self.assertIn("reservation_ok=0", WORKFLOW)
        self.assertIn("after bounded retry", WORKFLOW)

    def test_publish_uses_exact_id_and_normal_latest_channel(self) -> None:
        self.assertIn('rel=$(gh api "repos/$repo/releases/$id")', WORKFLOW)
        self.assertNotIn('select(.tag_name==\\"$tag\\")][0]', WORKFLOW)
        self.assertIn("-F draft=false -F prerelease=false -f make_latest=true", WORKFLOW)
        self.assertNotRegex(WORKFLOW, r"prerelease:\s*\$\{\{")
        self.assertIn("prerelease: false", WORKFLOW)

    def test_schedule_accepts_alpha_tags_and_docs_match(self) -> None:
        self.assertIn("(-[A-Za-z0-9._-]+)?$", WORKFLOW)
        self.assertIn("normale GitHub-Releases", README)
        self.assertIn("keinen separaten Prerelease-Kanal", README)

    def test_only_one_component_can_create_a_release(self) -> None:
        creates = re.findall(r'repos/\$REPO/releases"', WORKFLOW)
        self.assertEqual(len(creates), 1, "only reserve may POST a release")


if __name__ == "__main__":
    unittest.main()
