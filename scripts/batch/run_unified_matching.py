#!/usr/bin/env python
"""
Unified Matching CLI Runner

Convenience wrapper for running the matching module.

Usage:
    python run_unified_matching.py --list
    python run_unified_matching.py mergent_to_f7 --save
    python run_unified_matching.py mergent_to_f7 --save --diff
    python run_unified_matching.py --all --save
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.matching.cli import main

if __name__ == '__main__':
    main()
