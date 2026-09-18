"""Frozen desktop entry point; keep application code in the package."""
import os
import sys
import traceback

if __name__ == '__main__':
    # Windowed Windows executables otherwise hide failures behind a modal dialog.
    diagnostic = os.environ.get('BLOCK_ARCHIVE_STARTUP_LOG')
    try:
        from block_archive.desktop import main
        main()
    except BaseException:
        if not diagnostic:
            raise
        with open(diagnostic, 'w', encoding='utf-8') as output:
            traceback.print_exc(file=output)
        sys.exit(1)
