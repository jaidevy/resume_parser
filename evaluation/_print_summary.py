import json, sys

def show(path, label):
    try:
        d = json.load(open(path))
    except Exception as e:
        print(f"  Could not read {path}: {e}")
        return
    print(f"\n{'='*60}")
    print(f"{label}")
    print(f"{'='*60}")
    if "per_resume" in d:
        total = d.get("total_field_checks", 0)
        passed = d.get("total_passed", 0)
        acc = d.get("overall_accuracy", 0)
        print(f"Resumes: {d.get('resumes_evaluated',0)}  Fields: {total}  Passed: {passed}  Accuracy: {acc:.1%}")
        for r in d.get("per_resume", []):
            mark = "PASS" if r.get("accuracy", 0) >= 1.0 else "FAIL"
            name = r.get("resume", "")[:40]
            print(f"  [{mark}] {name:<42} {r.get('passed',0)}/{r.get('total_fields',0)}  {r.get('accuracy',0):.0%}")
    elif isinstance(d, list):
        total = sum(r.get("total_checks", 0) for r in d)
        passed = sum(r.get("score", 0) for r in d)
        acc = passed / total if total else 0
        print(f"Test cases: {len(d)}  Checks: {total}  Passed: {passed}  Accuracy: {acc:.1%}")
        for r in d:
            mark = "PASS" if r.get("accuracy", 0) >= 1.0 else "FAIL"
            print(f"  [{mark}] {r.get('test_case_name',''):<42} {r.get('score',0)}/{r.get('total_checks',0)}  {r.get('accuracy',0):.0%}")
    else:
        acc = d.get("overall_accuracy", d.get("overall_agent_accuracy", 0))
        print(f"Overall accuracy: {acc:.1%}")

show("evaluation/evaluation_results.json",      "EVALUATION SHEET  (extracted vs expected, 15 resumes)")
show("evaluation/prompt_evaluation_results.json","PROMPT EVAL       (LLM prompt quality, 5 test cases)")
show("evaluation/agent_evaluation_results.json", "AGENT EVAL        (end-to-end pipeline)")
