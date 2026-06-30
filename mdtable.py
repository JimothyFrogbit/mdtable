#!/usr/bin/env python3
"""mdtable — Format ragged markdown tables into neat aligned columns.

Usage:
    mdtable README.md          # Fix tables in-place
    mdtable < README.md        # Read from stdin, print to stdout
    cat doc.md | mdtable       # Pipe mode (same as above)
    mdtable --check <file>     # Dry-run: exit 1 if tables need formatting
    mdtable --check < doc.md   # Check on stdin
    mdtable --version          # Show version
    mdtable --help             # Show this message
"""

import sys
import re
import os

VERSION = "1.1.0"


def parse_cells(row):
    """Split a table row into individual cells, handling escaped pipes."""
    content = row.strip()
    if content.startswith('|'):
        content = content[1:]
    if content.endswith('|'):
        content = content[:-1]

    # Protect escaped pipes (\| → placeholder) before splitting on real pipes
    PLACEHOLDER = '\x00'
    escaped = content.replace('\\|', PLACEHOLDER)

    cells = []
    current = ''
    for char in escaped:
        if char == '|':
            cells.append(current.strip().replace(PLACEHOLDER, '|'))
            current = ''
        else:
            current += char
    cells.append(current.strip().replace(PLACEHOLDER, '|'))
    return cells


def parse_alignment(sep):
    """Parse alignment from separator row. Returns list of alignments."""
    cells = parse_cells(sep)
    alignments = []
    for cell in cells:
        cell = cell.strip()
        if cell.startswith(':') and cell.endswith(':'):
            alignments.append('center')
        elif cell.endswith(':'):
            alignments.append('right')
        else:
            alignments.append('left')
    return alignments


def parse_table(lines, start):
    """Parse a markdown table starting at `start` in `lines`.

    Returns (header, separator, rows, end_index) or None.
    Handles tables without a separator row (returns header only).
    Handles tables with only header + separator, no data rows.
    """
    if not lines[start].strip().startswith('|'):
        return None

    header = lines[start].rstrip()
    if start + 1 >= len(lines):
        return None

    sep = lines[start + 1].rstrip()
    # The separator row must contain only |, -, :, and spaces
    sep_content = sep.strip().strip('|').strip()
    if not re.match(r'^[\s\-:|]+$', sep_content):
        return None

    rows = []
    end = start + 2
    while end < len(lines):
        line = lines[end].rstrip()
        if not line.strip().startswith('|'):
            break
        rows.append(line)
        end += 1

    return (header, sep, rows, end)


def format_separator(widths, alignments):
    """Build a formatted separator row."""
    parts = []
    for w, a in zip(widths, alignments):
        # width + 2 accounts for mandatory space padding in data rows
        dashes = '-' * max(3, w + 2)
        if a == 'center':
            parts.append(f':{dashes[1:-1]}:')
        elif a == 'right':
            parts.append(f'{dashes[:-1]}:')
        else:
            parts.append(dashes)
    return '|' + '|'.join(parts) + '|'


def format_row(cells, widths, alignments):
    """Format a data row with proper padding."""
    parts = []
    for cell, w, a in zip(cells, widths, alignments):
        if a == 'right':
            parts.append(cell.rjust(w))
        elif a == 'center':
            left = (w - len(cell)) // 2
            right = w - len(cell) - left
            parts.append(' ' * left + cell + ' ' * right)
        else:
            parts.append(cell.ljust(w))
    return '| ' + ' | '.join(parts) + ' |'


def format_table(header, sep, rows):
    """Reformat an entire markdown table."""
    header_cells = parse_cells(header)
    alignments = parse_alignment(sep)

    all_rows = [header_cells]
    for row in rows:
        all_rows.append(parse_cells(row))

    # Calculate max widths
    ncols = max(len(r) for r in all_rows)
    widths = [0] * ncols
    if len(alignments) < ncols:
        alignments = alignments + ['left'] * (ncols - len(alignments))
    else:
        alignments = alignments[:ncols]

    for row in all_rows:
        for i, cell in enumerate(row):
            if i < ncols:
                widths[i] = max(widths[i], len(cell))

    # Ensure min width for separator readability
    widths = [max(w, 3) for w in widths]

    # Build output
    out = [format_row(header_cells, widths, alignments)]
    out.append(format_separator(widths, alignments))
    for row in rows:
        cells = parse_cells(row)
        cells = cells[:ncols] + [''] * (ncols - len(cells))
        out.append(format_row(cells, widths, alignments))

    return out


def process_markdown(text):
    """Process markdown text, formatting all tables.

    Returns (result_text, change_count).
    """
    lines = text.split('\n')
    result = []
    i = 0
    changes = 0

    while i < len(lines):
        table = parse_table(lines, i)
        if table:
            header, sep, rows, end = table
            original_block = '\n'.join([header, sep] + rows)
            formatted = format_table(header, sep, rows)
            if '\n'.join(formatted) != original_block:
                changes += 1
            result.extend(formatted)
            i = end
        else:
            result.append(lines[i])
            i += 1

    return '\n'.join(result), changes


def main():
    args = sys.argv[1:]

    # Help: explicit --help or -h
    if args and args[0] in ('-h', '--help'):
        print(__doc__.strip())
        return

    # Version
    if args and args[0] == '--version':
        print(f"mdtable v{VERSION}")
        return

    # Parse --check flag
    if args and args[0] == '--check':
        check_mode = True
        files = args[1:]
    else:
        check_mode = False
        files = args

    if not files:
        # No file arguments — read from stdin
        text = sys.stdin.read()
        result, changes = process_markdown(text)
        if check_mode:
            if changes > 0:
                print(f"stdin: {changes} table(s) need formatting", file=sys.stderr)
            sys.exit(0 if changes == 0 else 1)
        sys.stdout.write(result)
        return

    # File mode
    exit_code = 0
    for path in files:
        if not os.path.exists(path):
            print(f"mdtable: file not found: {path}", file=sys.stderr)
            sys.exit(1)

        with open(path, 'r') as f:
            text = f.read()

        result, changes = process_markdown(text)

        if check_mode:
            if changes > 0:
                print(f"{path}: {changes} table(s) need formatting")
                exit_code = 1
        else:
            if changes > 0:
                with open(path, 'w') as f:
                    f.write(result)
                print(f"{path}: {changes} table(s) formatted")
            else:
                print(f"{path}: no tables to format")

    sys.exit(exit_code)


if __name__ == '__main__':
    main()