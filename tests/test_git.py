from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from gigalphex.git import GitService, jira_branch_name


class GitServiceTest(unittest.TestCase):
    def test_dirty_paths_preserves_spaces_and_both_sides_of_rename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git = GitService(repo)
            git.run("init")
            git.run("config", "user.email", "test@example.com")
            git.run("config", "user.name", "GigaLphex Test")

            original = repo / "old name.txt"
            original.write_text("tracked\n", encoding="utf-8")
            git.run("add", ".")
            git.run("commit", "-m", "initial")

            git.run("mv", "old name.txt", "new name.txt")
            (repo / "untracked file.txt").write_text("new\n", encoding="utf-8")

            self.assertEqual(
                {
                    Path("old name.txt"),
                    Path("new name.txt"),
                    Path("untracked file.txt"),
                },
                set(git.dirty_paths()),
            )

    def test_jira_branch_name_uses_task_and_plan_description(self) -> None:
        self.assertEqual(
            "feature/PROJ-123-add-demo-feature",
            jira_branch_name(Path("docs/plans/20260625-add-demo-feature.md"), "PROJ-123"),
        )

    def test_ensure_clean_reports_dirty_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git = GitService(repo)
            git.run("init")
            (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")

            with self.assertRaisesRegex(Exception, "dirty.txt"):
                git.ensure_clean(False)

    def test_commit_subjects_since_returns_new_subjects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git = GitService(repo)
            git.run("init")
            git.run("config", "user.email", "test@example.com")
            git.run("config", "user.name", "GigaLphex Test")

            (repo / "one.txt").write_text("one\n", encoding="utf-8")
            git.run("add", ".")
            git.run("commit", "-m", "initial")
            head = git.head_commit()

            (repo / "two.txt").write_text("two\n", encoding="utf-8")
            git.run("add", ".")
            git.run("commit", "-m", "PROJ-123 feat: add two")

            self.assertEqual(["PROJ-123 feat: add two"], git.commit_subjects_since(head))


if __name__ == "__main__":
    unittest.main()
