"""
Entry point for running the matching module as a script.

Usage:
    python -m scripts.matching run --list
    python -m scripts.matching run mergent_to_f7 --save
"""

from .cli import main

if __name__ == '__main__':
    main()
