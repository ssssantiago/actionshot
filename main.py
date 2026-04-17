"""ActionShot - Record desktop interactions for AI-powered automation."""

import argparse
import sys

from actionshot.recorder import Recorder


def main():
    parser = argparse.ArgumentParser(
        description="ActionShot - Record desktop interactions for AI-powered automation",
    )
    parser.add_argument(
        "-o", "--output",
        default="recordings",
        help="Output directory for recordings (default: recordings)",
    )
    args = parser.parse_args()

    print("""
    ╔═══════════════════════════════════════╗
    ║           ⚡ ActionShot ⚡            ║
    ║   Desktop Interaction Recorder        ║
    ║   for AI-Powered Automation           ║
    ╚═══════════════════════════════════════╝
    """)

    recorder = Recorder(output_dir=args.output)

    try:
        recorder.start()
    except KeyboardInterrupt:
        recorder.stop()
        sys.exit(0)


if __name__ == "__main__":
    main()
