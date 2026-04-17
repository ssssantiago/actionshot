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


def cmd_record(args):
    from actionshot.recorder import Recorder
    print(BANNER)
    recorder = Recorder(output_dir=args.output)
    try:
        recorder.start()
    except KeyboardInterrupt:
        recorder.stop()


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


def cmd_gui(args):
    from actionshot.gui import ActionShotGUI
    app = ActionShotGUI()
    app.run()


def main():
    parser = argparse.ArgumentParser(
        description="ActionShot - Record desktop interactions for AI-powered automation",
    )
    sub = parser.add_subparsers(dest="command")

    # record
    rec = sub.add_parser("record", help="Start recording interactions")
    rec.add_argument("-o", "--output", default="recordings", help="Output directory")
    rec.set_defaults(func=cmd_record)

    # replay
    rep = sub.add_parser("replay", help="Replay a recorded session")
    rep.add_argument("session", help="Path to session folder")
    rep.add_argument("-s", "--speed", type=float, default=1.0, help="Playback speed multiplier")
    rep.add_argument("--dry-run", action="store_true", help="Print steps without executing")
    rep.set_defaults(func=cmd_replay)

    # generate
    gen = sub.add_parser("generate", help="Generate a standalone Python script from a session")
    gen.add_argument("session", help="Path to session folder")
    gen.add_argument("-o", "--output", default=None, help="Output script path")
    gen.set_defaults(func=cmd_generate)

    # ai
    ai = sub.add_parser("ai", help="Generate AI prompt or API payload from a session")
    ai.add_argument("session", help="Path to session folder")
    ai.add_argument("--export-api", action="store_true", help="Export as API payload instead of markdown")
    ai.add_argument("--screenshots", action="store_true", help="Include screenshots in API payload")
    ai.set_defaults(func=cmd_ai)

    # gui
    gui = sub.add_parser("gui", help="Launch the graphical interface")
    gui.set_defaults(func=cmd_gui)

    args = parser.parse_args()
    if not args.command:
        # Default: launch GUI
        cmd_gui(args)
    else:
        args.func(args)


if __name__ == "__main__":
    main()
