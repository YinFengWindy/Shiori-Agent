"""The enforced kernel budget rejects excess, missing and empty source trees."""


def test_budget_boundary_controls_the_process_exit_status(tmp_path):
    import shutil
    import subprocess
    import sys
    from scripts import kernel_loc_budget as budget

    script = tmp_path / "scripts/kernel_loc_budget.py"
    script.parent.mkdir()
    shutil.copyfile(budget.__file__, script)
    source = tmp_path / "packages/sdk/python/shiori_sdk/kernel/kernel.py"
    source.parent.mkdir(parents=True)
    source.write_text("value = 1\n" * 700, encoding="utf-8")
    assert subprocess.run([sys.executable, str(script)], check=False).returncode == 0
    source.write_text("value = 1\n" * 701, encoding="utf-8")
    assert subprocess.run([sys.executable, str(script)], check=False).returncode == 1


def test_missing_or_empty_kernel_cannot_pass(tmp_path, monkeypatch):
    from scripts import kernel_loc_budget as budget

    missing = tmp_path / "kernel"
    monkeypatch.setattr(budget, "KERNEL", missing)
    assert budget.main() == 1
    missing.mkdir()
    (missing / "README.md").write_text("No implementation", encoding="utf-8")
    assert budget.main() == 1
