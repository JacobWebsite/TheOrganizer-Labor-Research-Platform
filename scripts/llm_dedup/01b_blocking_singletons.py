"""Run the blocking pipeline against ny_singletons_25k.json instead of the
original ny_sample_20k.json. Imports the existing module and overrides paths.
"""
import importlib.util
import os
import sys

DIR = os.path.dirname(os.path.abspath(__file__))

# Load 01_blocking.py as a module (filename starts with a digit -> can't import normally)
spec = importlib.util.spec_from_file_location('blocking', os.path.join(DIR, '01_blocking.py'))
blocking = importlib.util.module_from_spec(spec)
spec.loader.exec_module(blocking)

# Override input/output paths
blocking.SAMPLE_PATH = os.path.join(DIR, 'ny_singletons_25k.json')
blocking.OUTPUT_PATH = os.path.join(DIR, 'candidates_singletons_scored.json')
blocking.STATS_PATH  = os.path.join(DIR, 'blocking_singletons_stats.json')

if __name__ == '__main__':
    sys.exit(blocking.main())
