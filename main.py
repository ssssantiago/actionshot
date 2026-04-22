"""ActionShot - Record desktop interactions for AI-powered automation."""

import argparse
import sys


BANNER = """
    ╔═══════════════════════════════════════╗
    ║           ActionShot                  ║
    ║   Desktop Interaction Recorder        ║
    ║   for AI-Powered Automation           ║
    ╚═══════════════════════════════════════╝
"""


def cmd_status(args):
    from actionshot.terminal_ui import TerminalDashboard
    dash = TerminalDashboard(recordings_dir=getattr(args, "recordings", "recordings"))
    dash.show_status()


def cmd_show(args):
    from actionshot.terminal_ui import TerminalDashboard
    dash = TerminalDashboard()
    dash.show_session(args.session)


def cmd_metrics(args):
    from actionshot.terminal_ui import TerminalDashboard
    dash = TerminalDashboard()
    dash.show_metrics(workflow_id=getattr(args, "workflow", None))


def cmd_record(args):
    from actionshot.recorder import Recorder
    from actionshot.config import load_config
    print(BANNER)

    config = load_config(getattr(args, "config", None))

    recorder = Recorder(
        output_dir=args.output or config["output_dir"],
        enable_video=args.video or config["video"],
        enable_ocr=not args.no_ocr and config["ocr"],
        video_fps=args.fps or config["video_fps"],
        image_format=args.format or config["image_format"],
        image_quality=args.quality or config["image_quality"],
    )
    try:
        recorder.start()
    except KeyboardInterrupt:
        recorder.stop()


def cmd_init(args):
    from actionshot.config import create_default_config
    create_default_config(args.path)


def cmd_replay(args):
    from actionshot.replay import Replayer
    print(BANNER)
    replayer = Replayer(args.session, speed=args.speed)
    replayer.run(dry_run=args.dry_run)


def cmd_generate(args):
    from actionshot.generator import ScriptGenerator
    gen = ScriptGenerator(args.session)
    gen.generate(output_path=args.output)


def cmd_ai(args):
    from actionshot.ai_agent import AIAgent
    agent = AIAgent(args.session)
    if args.export_api:
        agent.export_for_api(include_screenshots=args.screenshots)
    else:
        agent.generate_ai_prompt()


def cmd_claude(args):
    from actionshot.claude_api import ClaudeAutomator
    automator = ClaudeAutomator(args.session, api_key=args.api_key)
    if args.analyze:
        automator.analyze_workflow()
    else:
        automator.generate_script(
            include_screenshots=not args.no_screenshots,
            max_screenshots=args.max_screenshots,
        )


def cmd_analyze(args):
    from actionshot.patterns import PatternDetector
    detector = PatternDetector(args.session)
    detector.analyze()


def cmd_diff(args):
    from actionshot.diff import SessionDiff
    differ = SessionDiff(args.session_a, args.session_b)
    if args.json:
        import os
        output = os.path.join(args.session_a, "diff_report.json")
        differ.compare(output_path=output)
    else:
        differ.print_diff()


def cmd_export(args):
    from actionshot.export import WorkflowExporter
    exporter = WorkflowExporter(args.session)
    if args.format == "n8n":
        exporter.export_n8n()
    elif args.format == "zapier":
        exporter.export_zapier()
    else:
        exporter.export_n8n()
        exporter.export_zapier()


def cmd_schedule(args):
    from actionshot.scheduler import Scheduler
    sched = Scheduler()

    if args.action == "add":
        sched.add(
            name=args.name,
            script_path=args.script,
            cron_expr=args.cron,
            interval_minutes=args.interval,
        )
    elif args.action == "remove":
        sched.remove(args.id)
    elif args.action == "list":
        sched.print_schedules()
    elif args.action == "run":
        try:
            sched.run_daemon()
        except KeyboardInterrupt:
            sched.stop()


def cmd_tray(args):
    from actionshot.tray import TrayApp
    app = TrayApp(output_dir=args.output)
    app.run()


def cmd_gui(args):
    from actionshot.gui import ActionShotGUI
    app = ActionShotGUI()
    app.run()


def cmd_multi_record(args):
    from actionshot.recorder import Recorder
    print(BANNER)

    name = args.name
    count = args.count
    output = args.output

    try:
        from actionshot.multi_recorder import MultiRecordingSession, MultiRecordingDiff
    except ImportError:
        print("Error: multi_recorder module not available.")
        sys.exit(1)

    session = MultiRecordingSession(
        workflow_name=name,
        num_recordings=count,
        output_dir=output,
    )

    for i in range(1, count + 1):
        if i > 1:
            input(f"\nPress Enter to start recording {i} of {count}...")
        print(f"\n--- Recording {i} of {count}. Press ESC to stop this recording. ---\n")

        recorder = Recorder(
            output_dir=output,
            enable_video=args.video,
            enable_ocr=not args.no_ocr,
        )
        try:
            recorder.start()
        except KeyboardInterrupt:
            recorder.stop()

        if recorder.session:
            print(f"Recording {i} saved: {recorder.session.name} ({recorder.session.step_count} steps)")
            session.add_recording(recorder.session)
        else:
            print(f"Warning: recording {i} produced no session data.")

    print("\n--- All recordings complete. Running diff + variable inference... ---\n")
    diff = MultiRecordingDiff(session)
    result = diff.run()
    print(f"Analysis complete. Enriched IR saved.")


def cmd_curate(args):
    from actionshot.patterns import PatternDetector
    print(BANNER)
    detector = PatternDetector(args.session)
    result = detector.curate_session()
    print(f"Curation complete: {len(result.get('steps', []))} steps retained.")


def cmd_compile(args):
    from actionshot.ir_compiler import IRCompiler
    print(BANNER)
    compiler = IRCompiler(args.session)
    output = compiler.compile_and_save(output_path=args.output)
    print(f"IR compiled and saved to: {output}")


def cmd_redact(args):
    from actionshot.redact import redact_session
    print(BANNER)
    output = redact_session(args.session)
    print(f"Redacted copy created at: {output}")


def cmd_ollama(args):
    import json
    from actionshot.ollama import OllamaClient
    print(BANNER)

    client = OllamaClient(model=args.model)
    if not client.is_available():
        print("Error: Ollama is not running at", client.host)
        print("Start it with: ollama serve")
        sys.exit(1)

    # Load IR from session
    import os
    ir_path = os.path.join(args.session, "ir.json")
    if not os.path.exists(ir_path):
        print(f"Error: IR file not found at {ir_path}")
        print("Run 'python main.py compile <session>' first.")
        sys.exit(1)

    with open(ir_path, "r", encoding="utf-8") as f:
        ir = json.load(f)

    print(f"Generating script with Ollama ({args.model})...")
    script = client.generate_script(ir)
    print("\n" + script)


def cmd_audit(args):
    from actionshot.audit import AuditLog
    audit = AuditLog()

    if args.audit_action == "list":
        entries = audit.get_audit_trail(
            workflow_id=getattr(args, "workflow", None),
            user=getattr(args, "user", None),
            days=args.days,
        )
        if not entries:
            print("No audit entries found.")
        else:
            for entry in entries:
                ts = entry.get("timestamp", "?")
                event = entry.get("event", "?")
                user = entry.get("user") or entry.get("approver") or "?"
                print(f"  [{ts}] {event:25s} user={user}")
    elif args.audit_action == "export":
        audit.export_report(args.path, days=args.days)


def cmd_retention(args):
    from actionshot.audit import RetentionPolicy
    policy = RetentionPolicy()

    if args.dry_run:
        policy.dry_run(args.recordings)
    else:
        policy.enforce(args.recordings)


def cmd_approval(args):
    from actionshot.audit import ApprovalWorkflow
    import getpass
    wf = ApprovalWorkflow()

    if args.approval_action == "request":
        user = getpass.getuser()
        wf.request_approval(args.workflow_id, user, args.description)
    elif args.approval_action == "approve":
        approver = getpass.getuser()
        wf.approve(args.workflow_id, approver)
    elif args.approval_action == "reject":
        approver = getpass.getuser()
        wf.reject(args.workflow_id, approver, args.reason or "No reason given")
    elif args.approval_action == "list":
        pending = wf.list_pending()
        if not pending:
            print("No pending approvals.")
        else:
            for item in pending:
                wf_id = item["workflow_id"]
                req = item.get("requester", "?")
                desc = item.get("description", "")
                print(f"  {wf_id:30s} requester={req}  {desc}")


def main():
    parser = argparse.ArgumentParser(
        description="ActionShot - Record desktop interactions for AI-powered automation",
    )
    sub = parser.add_subparsers(dest="command")

    # init
    ini = sub.add_parser("init", help="Create default actionshot.yaml config file")
    ini.add_argument("path", nargs="?", default=None, help="Config file path")
    ini.set_defaults(func=cmd_init)

    # record
    rec = sub.add_parser("record", help="Start recording interactions")
    rec.add_argument("-o", "--output", default="recordings", help="Output directory")
    rec.add_argument("-c", "--config", default=None, help="Path to actionshot.yaml")
    rec.add_argument("--video", action="store_true", help="Also record video (MP4)")
    rec.add_argument("--no-ocr", action="store_true", help="Disable OCR text extraction")
    rec.add_argument("--fps", type=int, default=10, help="Video FPS (default: 10)")
    rec.add_argument("--format", choices=["jpeg", "png"], default="jpeg", help="Image format (default: jpeg)")
    rec.add_argument("--quality", type=int, default=85, help="JPEG quality 1-100 (default: 85)")
    rec.set_defaults(func=cmd_record)

    # replay
    rep = sub.add_parser("replay", help="Replay a recorded session")
    rep.add_argument("session", help="Path to session folder")
    rep.add_argument("-s", "--speed", type=float, default=1.0, help="Playback speed")
    rep.add_argument("--dry-run", action="store_true", help="Print steps without executing")
    rep.set_defaults(func=cmd_replay)

    # generate
    gen = sub.add_parser("generate", help="Generate standalone Python script")
    gen.add_argument("session", help="Path to session folder")
    gen.add_argument("-o", "--output", default=None, help="Output script path")
    gen.set_defaults(func=cmd_generate)

    # ai
    ai = sub.add_parser("ai", help="Generate AI prompt or API payload")
    ai.add_argument("session", help="Path to session folder")
    ai.add_argument("--export-api", action="store_true", help="Export as API payload")
    ai.add_argument("--screenshots", action="store_true", help="Include screenshots")
    ai.set_defaults(func=cmd_ai)

    # claude
    cl = sub.add_parser("claude", help="Send session to Claude API for automation")
    cl.add_argument("session", help="Path to session folder")
    cl.add_argument("--api-key", default=None, help="Anthropic API key (or set ANTHROPIC_API_KEY)")
    cl.add_argument("--analyze", action="store_true", help="Get workflow analysis instead of script")
    cl.add_argument("--no-screenshots", action="store_true", help="Don't send screenshots")
    cl.add_argument("--max-screenshots", type=int, default=20, help="Max screenshots to send")
    cl.set_defaults(func=cmd_claude)

    # analyze
    an = sub.add_parser("analyze", help="Detect patterns and loops in a session")
    an.add_argument("session", help="Path to session folder")
    an.set_defaults(func=cmd_analyze)

    # diff
    di = sub.add_parser("diff", help="Compare two sessions")
    di.add_argument("session_a", help="First session path")
    di.add_argument("session_b", help="Second session path")
    di.add_argument("--json", action="store_true", help="Save as JSON instead of printing")
    di.set_defaults(func=cmd_diff)

    # export
    ex = sub.add_parser("export", help="Export to n8n or Zapier workflow")
    ex.add_argument("session", help="Path to session folder")
    ex.add_argument("-f", "--format", choices=["n8n", "zapier", "both"], default="both")
    ex.set_defaults(func=cmd_export)

    # schedule
    sc = sub.add_parser("schedule", help="Manage scheduled automation tasks")
    sc_sub = sc.add_subparsers(dest="action")

    sc_add = sc_sub.add_parser("add", help="Add a scheduled task")
    sc_add.add_argument("name", help="Task name")
    sc_add.add_argument("script", help="Path to Python script")
    sc_add.add_argument("--cron", help='Schedule (e.g., "14:30" or "monday 09:00")')
    sc_add.add_argument("--interval", type=int, help="Run every N minutes")

    sc_sub.add_parser("list", help="List scheduled tasks")

    sc_rm = sc_sub.add_parser("remove", help="Remove a scheduled task")
    sc_rm.add_argument("id", type=int, help="Schedule ID")

    sc_sub.add_parser("run", help="Start scheduler daemon")
    sc.set_defaults(func=cmd_schedule)

    # tray
    tr = sub.add_parser("tray", help="Run in system tray")
    tr.add_argument("-o", "--output", default="recordings", help="Output directory")
    tr.set_defaults(func=cmd_tray)

    # gui
    sub.add_parser("gui", help="Launch graphical interface").set_defaults(func=cmd_gui)

    # status
    st = sub.add_parser("status", help="Show system status in terminal")
    st.add_argument("--recordings", default="recordings", help="Recordings directory")
    st.set_defaults(func=cmd_status)

    # show
    sh = sub.add_parser("show", help="Pretty-print session details in terminal")
    sh.add_argument("session", help="Path to session folder")
    sh.set_defaults(func=cmd_show)

    # metrics
    me = sub.add_parser("metrics", help="Show telemetry metrics in terminal")
    me.add_argument("workflow", nargs="?", default=None, help="Workflow ID (omit for all)")
    me.set_defaults(func=cmd_metrics)

    # multi-record
    mr = sub.add_parser("multi-record", help="Interactive multi-recording session")
    mr.add_argument("--name", required=True, help="Workflow name")
    mr.add_argument("--count", type=int, default=3, help="Number of recordings (default: 3)")
    mr.add_argument("-o", "--output", default="recordings", help="Output directory")
    mr.add_argument("--video", action="store_true", help="Also record video (MP4)")
    mr.add_argument("--no-ocr", action="store_true", help="Disable OCR text extraction")
    mr.set_defaults(func=cmd_multi_record)

    # curate
    cu = sub.add_parser("curate", help="Run curation pipeline on a session")
    cu.add_argument("session", help="Path to session folder")
    cu.set_defaults(func=cmd_curate)

    # compile
    co = sub.add_parser("compile", help="Compile session to IR")
    co.add_argument("session", help="Path to session folder")
    co.add_argument("-o", "--output", default=None, help="Output IR path")
    co.set_defaults(func=cmd_compile)

    # redact
    rd = sub.add_parser("redact", help="Create redacted copy of a session")
    rd.add_argument("session", help="Path to session folder")
    rd.set_defaults(func=cmd_redact)

    # ollama
    ol = sub.add_parser("ollama", help="Generate script using local Ollama model")
    ol.add_argument("session", help="Path to session folder")
    ol.add_argument("--model", default="codellama:13b", help="Ollama model (default: codellama:13b)")
    ol.set_defaults(func=cmd_ollama)

    # audit
    au = sub.add_parser("audit", help="Query or export audit logs")
    au_sub = au.add_subparsers(dest="audit_action")

    au_list = au_sub.add_parser("list", help="List audit entries")
    au_list.add_argument("--workflow", default=None, help="Filter by workflow ID")
    au_list.add_argument("--user", default=None, help="Filter by user")
    au_list.add_argument("--days", type=int, default=30, help="Look back N days (default: 30)")

    au_export = au_sub.add_parser("export", help="Export audit report as CSV")
    au_export.add_argument("path", help="Output CSV file path")
    au_export.add_argument("--days", type=int, default=90, help="Look back N days (default: 90)")

    au.set_defaults(func=cmd_audit)

    # retention
    rt = sub.add_parser("retention", help="Manage data retention (LGPD compliance)")
    rt_sub = rt.add_subparsers(dest="retention_action")

    rt_enforce = rt_sub.add_parser("enforce", help="Run retention policy")
    rt_enforce.add_argument("--dry-run", action="store_true", help="Show what would be deleted")
    rt_enforce.add_argument("--recordings", default="recordings", help="Recordings directory")

    rt.set_defaults(func=cmd_retention, dry_run=False, recordings="recordings")

    # approval
    ap = sub.add_parser("approval", help="Manage workflow approvals")
    ap_sub = ap.add_subparsers(dest="approval_action")

    ap_req = ap_sub.add_parser("request", help="Request approval for a workflow")
    ap_req.add_argument("workflow_id", help="Workflow identifier")
    ap_req.add_argument("--description", required=True, help="Description of the workflow")

    ap_approve = ap_sub.add_parser("approve", help="Approve a workflow")
    ap_approve.add_argument("workflow_id", help="Workflow identifier")

    ap_reject = ap_sub.add_parser("reject", help="Reject a workflow")
    ap_reject.add_argument("workflow_id", help="Workflow identifier")
    ap_reject.add_argument("--reason", default=None, help="Rejection reason")

    ap_sub.add_parser("list", help="List pending approvals")

    ap.set_defaults(func=cmd_approval)

    args = parser.parse_args()
    if not args.command:
        cmd_gui(args)
    else:
        args.func(args)


if __name__ == "__main__":
    main()
