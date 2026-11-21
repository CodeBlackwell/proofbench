"""The path: the step log, the rules and the judge that grade it, and the controls they face."""
import json
import shutil
from pathlib import Path

import pytest

from proofbench import config, controls, engine, gates, judge, paths, runner, steps
from proofbench.util import HarnessError

from .test_gates import check, demo, recorded  # noqa: F401 (demo is a fixture)
from .test_grader import entry, write_config

LOGGED = [{"tool": "search", "input": {"name": "Sundqvist"}, "result": "one thesis"},
          {"tool": "lookup", "input": {"id": 7}, "result": "Per Pettersson"}]
WRITE_LOG = ("    import os\n    with open(os.environ['PROOFBENCH_STEPS'], 'w') as log:\n"
             f"        log.write({''.join(json.dumps(step) + chr(10) for step in LOGGED)!r})\n")
PATH = ("path:\n  rules:\n    - called: lookup\n    - before: [search, lookup]\n"
        "    - max_steps: 3\n    - script: rules/named.sh\n  judge: path-judge.md\n")
NAMED = ('#!/bin/sh\ngrep -q Pettersson "$1" && echo "the name was met" && exit 0\n'
         'echo "the path never met the name"\nexit 1\n')
# The shape of CLI 2.1.319's stream: other lines around the events, and a result that is not last.
STREAM = "\n".join(["a hook printed this", *map(json.dumps, [
    {"type": "system", "subtype": "init"},
    {"type": "user", "message": {"content": "the prompt, as a plain string"}},
    {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {"file_path": "a.py"}}]}},
    {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "toolu_1", "content": "1\tx = 1\n"}]}},
    {"type": "assistant", "message": {"content": [
        {"type": "text", "text": "Listing."},
        {"type": "tool_use", "id": "toolu_2", "name": "Bash", "input": {"command": "ls"}},
        {"type": "tool_use", "id": "toolu_3", "name": "Edit", "input": {}}]}},
    {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "toolu_2", "content": [{"type": "text", "text": "a.py"}]}]}},
    {"type": "result", "total_cost_usd": 0.005, "num_turns": 2,
     "usage": {"input_tokens": 4, "output_tokens": 168}},
    {"type": "system", "subtype": "task_summary"}])])


def sound_if_ordered(prompt, model, limit_kb, name):
    agent_path = prompt.split("===== AGENT_PATH =====")[1]
    return {"sound": int(0 <= agent_path.find('"search"') < agent_path.find('"lookup"'))}, 0.02


@pytest.fixture
def pathed(demo, monkeypatch):  # noqa: F811
    """The question demo with an arm that logs two steps, four rules and a path judge."""
    root, asked = demo.parent, "    asked = json.loads(sys.stdin.read())\n"
    arm = root / "arms" / "oracle-tier1.py"
    arm.write_text(arm.read_text().replace(asked, asked + WRITE_LOG))
    (root / "rules").mkdir()
    (root / "rules" / "named.sh").write_text(NAMED)
    (root / "rules" / "named.sh").chmod(0o755)
    (root / "path-judge.md").write_text("Rule the path sound or not.\n")
    demo.write_text(demo.read_text() + PATH)
    monkeypatch.setattr(judge, "ask", sound_if_ordered)
    return demo


def record(pathed, tmp_path):
    """Run the eval once and keep one attempt's path as the recorded good one."""
    cfg = config.load(pathed)
    leg = engine.bench(cfg, tmp_path / "runs" / "first", cfg.models)["stub"]
    kept = pathed.parent / "paths" / "LQ-0001"
    shutil.copytree(tmp_path / "runs" / "first" / "stub" / "LQ-0001" / "trial-1", kept)
    return leg


def test_a_claude_stream_becomes_steps_and_its_result_is_found_wherever_it_sits():
    assert steps.from_claude(STREAM) == [
        {"tool": "Read", "input": {"file_path": "a.py"}, "result": "1\tx = 1\n"},
        {"tool": "Bash", "input": {"command": "ls"}, "result": "a.py"},
        {"tool": "Edit", "input": {}, "result": None}]
    assert runner._claude_meta(STREAM)["cost_usd"] == 0.005
    assert "stream-json" in runner._claude("go", "weak", 5, True)
    assert "stream-json" not in runner._claude("go", "weak", 5, False)


def test_a_step_log_that_is_missing_or_malformed_is_a_hard_stop(tmp_path):
    with pytest.raises(HarnessError, match="no step log"):
        steps.read(tmp_path / steps.FILE)
    (tmp_path / steps.FILE).write_text('{"tool": "search", "input": {}}\n')
    with pytest.raises(HarnessError, match="is not a step"):
        steps.read(tmp_path / steps.FILE)


def test_an_adapter_is_told_an_absolute_file_so_it_may_change_directory():
    assert Path(runner._env(Path("runs") / steps.FILE)[steps.ENV]).is_absolute()


@pytest.mark.parametrize("rule, tools, held", [
    (("called", "b"), ["a", "b"], True), (("called", "b"), ["a"], False),
    (("never_called", "b"), ["a"], True), (("never_called", "b"), ["b"], False),
    (("max_steps", 2), ["a", "b"], True), (("max_steps", 1), ["a", "b"], False),
    (("before", ["a", "b"]), ["a", "b", "a"], True), (("before", ["a", "b"]), ["c"], True),
    (("before", ["a", "b"]), ["b", "a"], False), (("before", ["a", "b"]), ["b"], False)])
def test_each_fixed_rule_holds_or_not_on_the_tools_called(rule, tools, held):
    assert paths._holds(*rule, tools)[0] is held


@pytest.mark.parametrize("bad", ["path: {}\n", "path:\n  rules:\n    - visited: x\n",
                                 "path:\n  rules:\n    - before: [a]\n",
                                 "path:\n  rules:\n    - script: no-such-rule.sh\n",
                                 "path:\n  judge: no-such-rubric.md\n"])
def test_a_path_key_that_could_grade_nothing_is_refused_at_load(demo, bad):  # noqa: F811
    demo.write_text(demo.read_text() + bad)
    with pytest.raises(HarnessError, match="path"):
        config.load(demo)


def test_a_run_grades_the_path_beside_the_answer(pathed, tmp_path):
    leg = record(pathed, tmp_path)
    first = leg["records"][0]
    assert (leg["rules_held_rate"], leg["path_sound_rate"], leg["accuracy"]) == (1.0, 1.0, 0.667)
    assert first["rules"]["script:named.sh"] == {"held": True, "why": "the name was met"}
    assert set(first["rules"]) == {"called:lookup", "before:search>lookup", "max_steps:3",
                                   "script:named.sh"}
    assert gates._spent(leg) == 0.06


def test_the_path_judge_sees_the_recorded_path_and_never_the_answer(pathed, tmp_path, monkeypatch):
    record(pathed, tmp_path)
    seen = []
    monkeypatch.setattr(judge, "ask", lambda prompt, *rest: seen.append(prompt) or ({"sound": 1}, 0))
    cfg = config.load(pathed)
    engine.bench(cfg, tmp_path / "runs" / "second", cfg.models)
    assert sum("EXAMPLE_PATH" in prompt for prompt in seen) == 1
    assert not any("answer_ids" in prompt for prompt in seen)


def test_a_rule_script_that_crashes_stops_the_run(pathed, tmp_path):
    (pathed.parent / "rules" / "named.sh").write_text("#!/bin/sh\nexit 2\n")
    with pytest.raises(HarnessError, match="exited 2"):
        record(pathed, tmp_path)


def test_an_adapter_that_logs_no_steps_fails_its_gate(pathed, tmp_path):
    assert check(pathed, "adapter", tmp_path)
    assert "2 steps" in recorded(pathed, "adapter")["detail"]
    arm = pathed.parent / "arms" / "oracle-tier1.py"
    arm.write_text(arm.read_text().replace(WRITE_LOG, ""))
    assert not gates.check(config.load(pathed), "adapter", tmp_path / "runs" / "again")
    assert "no step log" in recorded(pathed, "adapter")["detail"]


def test_a_recorded_path_yields_controls_the_path_graders_must_score_as_predicted(pathed, tmp_path):
    record(pathed, tmp_path)
    cfg = config.load(pathed)
    assert controls.build(cfg) == 14
    predictions = json.loads((controls.folder(cfg) / "predictions.json").read_text())
    assert predictions["LQ-0001/good.path"] == {"rules_held": [1, 1], "path_sound": [1, 1]}
    for ruined in ("empty", "removed", "reordered"):
        assert predictions[f"LQ-0001/{ruined}.path"] == {"rules_held": [0, 0], "path_sound": [0, 0]}
    turned = steps.read(controls.folder(cfg) / "LQ-0001" / "reordered.path" / steps.FILE)
    assert [step["tool"] for step in turned] == ["lookup", "search"]
    assert check(pathed, "controls", tmp_path)
    assert "4 of them for the path" in recorded(pathed, "controls")["detail"]


def test_the_controls_gate_fails_a_path_judge_that_calls_every_path_sound(pathed, tmp_path,
                                                                         monkeypatch):
    record(pathed, tmp_path)
    controls.build(config.load(pathed))
    monkeypatch.setattr(judge, "ask", lambda *args: ({"sound": 1}, 0.02))
    assert not check(pathed, "controls", tmp_path)
    assert "LQ-0001/empty.path" in recorded(pathed, "controls")["detail"]


def test_a_graded_path_with_no_path_control_fails_the_controls_gate(pathed, tmp_path):
    controls.build(config.load(pathed))
    assert not check(pathed, "controls", tmp_path)
    assert "0 of them for the path" in recorded(pathed, "controls")["detail"]


def test_a_gate_goes_stale_only_on_what_it_depends_on(pathed, tmp_path):
    for gate in ("adapter", "coverage"):
        assert check(pathed, gate, tmp_path)
    pathed.write_text("# a reworded comment\n" + pathed.read_text())
    assert set(gates.status(config.load(pathed)).values()) == {"passed", "not run"}
    pathed.write_text(pathed.read_text().replace("max_steps: 3", "max_steps: 4"))
    assert set(gates.status(config.load(pathed)).values()) == {"passed", "not run"}
    pathed.write_text(pathed.read_text().replace(PATH.replace("3", "4"), ""))
    states = gates.status(config.load(pathed))
    assert (states["adapter"], states["coverage"]) == ("stale", "passed")


def test_a_repo_runner_is_told_where_to_log_and_never_where_the_run_is(repo, tmp_path, monkeypatch):
    agent = tmp_path / "agent.sh"
    agent.write_text('#!/bin/sh\necho "x = 2" > a.py\nprintf \'{"tool": "edit", "input": {}, '
                     '"result": "%s"}\\n\' "$PROOFBENCH_STEPS" > "$PROOFBENCH_STEPS"\n')
    agent.chmod(0o755)
    cfg = config.load(write_config(repo, entry(repo), (
        f"judge: default\nrunner: {agent}\npath:\n  rules:\n    - called: edit\n")))
    monkeypatch.setattr(judge, "grade", lambda *args, **named: ({"recall": 1.0}, 0.01))
    leg = engine.bench(cfg, tmp_path / "run", cfg.models)["weak"]
    told = steps.read(tmp_path / "run" / "weak" / "fix" / steps.FILE)[0]["result"]
    assert (leg["macro_rules_held"], leg["macro_recall"]) == (1.0, 1.0)
    assert str(tmp_path / "run") not in told
