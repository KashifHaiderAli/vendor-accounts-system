from django.core.management.base import BaseCommand

from core.scenario_test_runner import ScenarioTestRunner


class Command(BaseCommand):
    help = "Run a complete scenario-based smoke test and generate detailed HTML/TXT reports."

    def add_arguments(self, parser):
        parser.add_argument("--reset-test-data", action="store_true", help="Safely reset/cancel AUTO-TEST data where supported before running.")
        parser.add_argument("--report-format", choices=["html", "txt"], default="html", help="Preferred report format. Both HTML and TXT are always generated.")
        parser.add_argument("--verbose", action="store_true", help="Print each test step while running.")
        parser.add_argument("--auto-fix", action="store_true", default=True, help="Attempt safe auto-fixes for AUTO-TEST setup issues.")
        parser.add_argument("--no-auto-fix", dest="auto_fix", action="store_false", help="Disable safe auto-fixes.")
        parser.add_argument("--skip-license-mutation", action="store_true", default=True, help="Do not mutate real license state.")
        parser.add_argument("--skip-restore-test", action="store_true", default=True, help="Do not restore database automatically.")

    def handle(self, *args, **options):
        runner = ScenarioTestRunner(
            report_format=options["report_format"],
            verbose=options["verbose"],
            auto_fix=options["auto_fix"],
            reset_test_data=options["reset_test_data"],
            skip_license_mutation=options["skip_license_mutation"],
            skip_restore_test=options["skip_restore_test"],
        )
        html_path, txt_path = runner.run()
        counts = runner.report.counts()
        self.stdout.write(f"HTML report: {html_path}")
        self.stdout.write(f"TXT report: {txt_path}")
        self.stdout.write(
            "Summary: "
            f"PASS={counts['PASS']} FAIL={counts['FAIL']} WARNING={counts['WARNING']} "
            f"SKIPPED={counts['SKIPPED']} AUTO-FIXED={counts['AUTO-FIXED']}"
        )
        conclusion = runner.report.conclusion()
        if conclusion == "NOT READY":
            self.stdout.write(self.style.ERROR(f"Final conclusion: {conclusion}"))
        elif conclusion == "READY WITH WARNINGS":
            self.stdout.write(self.style.WARNING(f"Final conclusion: {conclusion}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Final conclusion: {conclusion}"))
