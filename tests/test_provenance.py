"""Where a measurement was made (eval.provenance), on a throwaway git repository."""
import subprocess

from eval.provenance import final_problem, in_name, provenance


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def repo_with_a_commit(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@t")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "anchor.py").write_text("x = 1\n")
    (tmp_path / "eval" / "results").mkdir(parents=True)
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "c")
    return tmp_path


def test_a_clean_copy_has_the_full_commit_and_no_dirty_mark(tmp_path):
    p = provenance(repo_with_a_commit(tmp_path))
    assert p["clean"] and len(p["commit_full"]) == 40 and p["commit"] == p["commit_full"][:7]
    assert in_name(p) == p["commit"] and p["tag"] == ""


def test_uncommitted_changes_mark_the_name_and_are_listed_but_new_results_do_not(tmp_path):
    repo = repo_with_a_commit(tmp_path)
    (repo / "eval" / "results" / "plans_x.json").write_text("{}")          # the measurement itself
    assert provenance(repo)["clean"]
    (repo / "anchor.py").write_text("x = 2\n")
    p = provenance(repo)
    assert not p["clean"] and p["changed"] == ["anchor.py"] and in_name(p).endswith("+dirty")


def test_a_final_run_needs_a_clean_copy_and_a_tag(tmp_path):
    repo = repo_with_a_commit(tmp_path)
    assert "tag" in final_problem(provenance(repo))
    git(repo, "tag", "v1.0.0")
    assert provenance(repo)["tag"] == "v1.0.0" and final_problem(provenance(repo)) == ""
    (repo / "anchor.py").write_text("x = 3\n")
    assert "nothing changed" in final_problem(provenance(repo))
