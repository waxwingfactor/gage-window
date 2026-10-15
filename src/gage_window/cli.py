"""The supported command-line interface."""
import argparse
from importlib.resources import files
import sys

from . import __version__
from .core import InputError, analyze, publish, review, verify


def main(argv=None):
    parser = argparse.ArgumentParser(description='Reconcile fragmented gauge-use evidence. Does not assess conformance.')
    parser.add_argument('--version', action='version', version=__version__)
    commands = parser.add_subparsers(dest='command', required=True)
    a = commands.add_parser('analyze', help='Reconstruct candidate review cases from explicit mappings/windows')
    a.add_argument('project'); a.add_argument('--out', required=True)
    r = commands.add_parser('review', help='Validate and import a complete case decision worksheet')
    r.add_argument('report'); r.add_argument('--decisions', required=True); r.add_argument('--out', required=True)
    v = commands.add_parser('verify', help='Check report integrity and reproduce supplied-evidence accounting')
    v.add_argument('report')
    e = commands.add_parser('example', help='Create a runnable constructed example in a new directory')
    e.add_argument('directory')
    args = parser.parse_args(argv)
    try:
        if args.command == 'example':
            publish(args.directory, {p.name: p.read_bytes() for p in files('gage_window').joinpath('example').iterdir() if p.is_file()})
            print('Constructed example created. Run analyze on its project.json.')
            return 0
        if args.command == 'analyze':
            analysis = analyze(args.project, args.out)
            print(f"{len(analysis['records'])} records accounted; {len(analysis['cases'])} review cases; unresolved={analysis['counts'].get('unresolved', 0)}")
            print('Report written. All cases start open; exit 0 does not mean review complete or product conforming.')
            return 2 if analysis['counts'].get('unresolved', 0) else 0
        if args.command == 'review':
            decisions = review(args.report, args.decisions, args.out)
            remaining = sum(r['status'] == 'open' for r in decisions)
            print(f'Decisions recorded; open={remaining}. Status is human follow-up, not conformance approval.')
            return 2 if remaining else 0
        analysis, _, decisions = verify(args.report)
        print(f"Verified reproducible evidence accounting: {analysis['analysis_id']}")
        print('Hashes do not establish authenticity, input completeness or measurement correctness.')
        return 0
    except (InputError, OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        print(f'gage-window: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
