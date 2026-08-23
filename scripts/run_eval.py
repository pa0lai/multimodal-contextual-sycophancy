#!/usr/bin/env python3
"""Deprecated compatibility alias for the paid LLM judging command."""

import warnings
from run_judge import main

if __name__ == "__main__":
    warnings.warn("run_eval.py is deprecated and performs paid LLM judging; use run_judge.py. For offline metrics use summarize_results.py.", FutureWarning, stacklevel=1)
    main()

