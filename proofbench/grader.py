"""The command grader: run a command in the agent's clone and read its exit code.

Where something can be run, it is the better grader: free, exact, and the same answer every
time. The files the command checks with are held back on the answer branch and copied in only
after the agent has finished, so an agent can neither read them nor pass by editing them."""
import subprocess

from .util import die, spawn


def _add_hidden(task, work):
    """Copy the held-back paths out of the answer branch, over whatever the agent left there."""
    archive = subprocess.run(["git", "-C", str(task.path), "archive", task.answer_branch, "--",
                              *task.hidden], capture_output=True)
    if archive.returncode != 0:
        die(f"{task.name}: cannot read hidden paths {task.hidden} from {task.answer_branch}: "
            f"{archive.stderr.decode(errors='replace').strip()}")
    subprocess.run(["tar", "-x", "-C", str(work)], input=archive.stdout, check=True)


def run_check(task, work, minutes=None):
    """The grade of one clone: passed is 1 when the command exits 0, and 0 for anything else."""
    if task.hidden:
        _add_hidden(task, work)
    proc = spawn(["sh", "-c", task.check], minutes, cwd=work)
    return {"passed": int(proc.returncode == 0), "graded_by": "command",
            "check_output": (proc.stdout + proc.stderr)[-2000:]}
