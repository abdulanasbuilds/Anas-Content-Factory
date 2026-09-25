import json

def run(job):
    report={"job":str(job),"passed":True,"checks":[]}
    for path in job.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".mp4",".mov",".mkv"}:
            size=path.stat().st_size
            passed=size>0
            report["checks"].append({"file":str(path),"size":size,"passed":passed})
            report["passed"]=report["passed"] and passed
    (job/"analysis"/"qc-report.md").write_text(json.dumps(report,indent=2),encoding="utf-8")
    return report
