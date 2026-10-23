from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
REVIEW_ACTION = ROOT / '.github/actions/review-upload/action.yml'
PUBLISH_ACTION = ROOT / '.github/actions/publish-site/action.yml'


def named_step(source, name):
    marker = f'    - name: {name}\n'
    start = source.index(marker)
    end = source.find('\n    - name: ', start + len(marker))
    return source[start:] if end < 0 else source[start:end]


class ReviewTransferPolicyTests(unittest.TestCase):
    def test_compatibility_shim_preserves_inputs_and_disables_upload(self):
        source = REVIEW_ACTION.read_text()
        for key in ('enabled', 'directory', 'patterns', 'name'):
            self.assertIn(f'  {key}:', source)
        self.assertIn('artifact-id:', source)
        self.assertIn('steps.disabled.outputs.artifact-id', source)
        self.assertIn('steps.disabled.outputs.outcome', source)
        self.assertIn("echo 'artifact-id=' >> \"$GITHUB_OUTPUT\"", source)
        self.assertIn("echo 'outcome=disabled' >> \"$GITHUB_OUTPUT\"", source)
        self.assertIn('no staging copy was created', source)
        self.assertNotRegex(source, r'uses:\s*actions/upload-artifact@')
        self.assertNotIn('review_transfer.py', source)

    def test_publisher_retains_evidence_for_each_package_kind_before_cleanup(self):
        source = PUBLISH_ACTION.read_text()
        retention = named_step(source, 'Retain bounded smoke evidence on the trusted runner')
        self.assertIn('id: retention', retention)
        self.assertIn("runner.environment == 'self-hosted'", retention)
        self.assertIn('runner_evidence.py', retention)
        self.assertNotIn('steps.resolve.outputs.package_kind', retention)
        self.assertNotIn('continue-on-error:', retention)
        self.assertLess(retention.index('runner_evidence.py'), retention.index("echo 'retained=true'"))
        self.assertIn("echo 'status=missing'", retention)
        self.assertIn("echo 'status=retained'", retention)

    def test_retention_failure_preserves_unique_evidence_and_removes_reproducible_inputs(self):
        source = PUBLISH_ACTION.read_text()
        preserve = named_step(source, 'Remove reproducible inputs after evidence retention failure')
        cleanup = named_step(source, "Remove this job's temporary payload after evidence retention")
        self.assertIn("steps.retention.outcome == 'failure'", preserve)
        self.assertIn('"$WORK/incoming"', preserve)
        self.assertIn('"$WORK/payload"', preserve)
        self.assertIn('"$WORK/candidate.json"', preserve)
        self.assertIn('"$WORK/release.zip"', preserve)
        self.assertNotIn('"$WORK/evidence"', preserve)
        self.assertIn('steps.retention.outputs.status == \'retained\'', cleanup)
        self.assertIn('steps.retention.outputs.status == \'missing\'', cleanup)
        self.assertNotIn("steps.retention.outcome == 'failure'", cleanup)

    def test_summary_only_claims_successful_retention_when_files_exist(self):
        source = PUBLISH_ACTION.read_text()
        summary = named_step(source, 'Report browser evidence retention separately')
        self.assertIn('RETAINED: ${{ steps.retention.outputs.retained }}', summary)
        self.assertIn('STATUS: ${{ steps.retention.outputs.status }}', summary)
        self.assertIn('OUTCOME: ${{ steps.retention.outcome }}', summary)
        self.assertIn('[[ "$RETAINED" == true && "$STATUS" == retained ]]', summary)
        self.assertIn('unique smoke evidence remains at $WORK/evidence', summary)
        self.assertIn('Hosted-runner evidence is available in this run’s logs only', summary)


if __name__ == '__main__':
    unittest.main()
