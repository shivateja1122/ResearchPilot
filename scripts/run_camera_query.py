"""
Executes the upgraded Multi-Agent Research System on the benchmark camera phone query:
'Suggest me a good camera mobile under ₹30,000 in India.'
Saves:
- camera_report_output.md
- camera_audit_output.json
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from orchestrator import ResearchOrchestrator
from storage.research_store import ResearchStore

def main():
    print("=" * 70)
    print("Executing Multi-Agent Research System on Benchmark Query:")
    query = "Suggest me a good camera mobile under INR 30,000 in India."
    print(f"Query: {query}")
    print("=" * 70)

    store = ResearchStore()
    orchestrator = ResearchOrchestrator(
        store=store,
        max_research_rounds=2,
        max_follow_up_searches=4
    )

    def on_progress(stage, msg, pct, extra):
        print(f"[{int(pct * 100):02d}%] [{stage.upper()}]: {msg}")

    run = orchestrator.run_research(query, progress_callback=on_progress)

    print("\n" + "=" * 70)
    print("Research Run Completed!")
    print(f"Run ID: {run.run_id}")
    print(f"Accepted Sources: {len(run.sources)}")
    print(f"Rejected Sources: {len(run.rejected_sources)}")
    print(f"Evidence Records: {len(run.evidence_records)}")
    if run.quality_gate_result:
        print(f"Quality Gate Score: {run.quality_gate_result.score * 100:.1f}%")
        print(f"Quality Gate Passed: {run.quality_gate_result.report_passed}")
        print(f"Repairs Applied: {len(run.quality_gate_result.repairs_applied)}")
    print("=" * 70)

    # Save final Markdown report
    if run.final_report:
        with open("camera_report_output.md", "w", encoding="utf-8") as f:
            f.write(run.final_report.markdown_content)
        print("Exported camera_report_output.md")

    # Save separate Research Audit JSON
    if run.research_audit:
        with open("camera_audit_output.json", "w", encoding="utf-8") as f:
            json.dump(run.research_audit.model_dump(), f, indent=2)
        print("Exported camera_audit_output.json")

if __name__ == "__main__":
    main()
