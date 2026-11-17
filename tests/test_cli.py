import subprocess
import sys

from perovskite_explorer.cli import main


def test_backup_restore_and_export(store, tmp_path):
    backup, restored = tmp_path / "backup", tmp_path / "restored"
    assert main(["backup", str(store.directory), "--out", str(backup)]) == 0
    assert main(["restore", str(backup), "--out", str(restored)]) == 0
    assert main(["export", str(restored)]) == 0
    assert (restored / "report.html").is_file()
    assert main(["backup", str(store.directory), "--out", str(backup)]) == 2


def test_active_lock_blocks_mutation(store):
    from filelock import FileLock
    with FileLock(str(store.directory / ".run.lock")):
        assert main(["export", str(store.directory)]) == 2


def test_process_kill_preserves_committed_page(store):
    script = '''
import sys,time
from pathlib import Path
from perovskite_explorer.store import Store
s=Store(Path(sys.argv[1]))
k=s.add_job('compound','test','hard-kill')
s.start(k)
s.page(k,[{'id':'committed'}],'next',2)
s.db.execute("UPDATE jobs SET cursor='uncommitted' WHERE id=?",(k,))
print('ready',flush=True)
time.sleep(30)
'''
    process = subprocess.Popen([sys.executable, "-c", script, str(store.directory)], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == "ready"
        process.kill()
        process.wait(timeout=10)
        store.recover()
        job = next(j for j in store.jobs() if j["source"] == "test")
        assert job["cursor"] == "next"
        assert job["payload"] == [{"id": "committed"}]
        assert store.integrity() == "ok"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


def test_bad_input_does_not_start_network(tmp_path):
    file = tmp_path / "empty.txt"
    file.write_text("# no compounds\n")
    assert main(["run", str(file), "--out", str(tmp_path / "run")]) == 2
