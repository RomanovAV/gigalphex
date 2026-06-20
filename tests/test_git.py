from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from gigalphex.git import GitService


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


if __name__ == "__main__":
    unittest.main()
