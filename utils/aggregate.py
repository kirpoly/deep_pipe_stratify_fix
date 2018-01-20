"""Compute some metric across values from json formatted input, fed to stdin"""
import sys
import json
import argparse

import numpy as np

if __name__ == '__main__':
    parser = argparse.ArgumentParser('aggregate')
    parser.add_argument('mode')
    args = parser.parse_args()

    op = getattr(np, args.mode)

    values = list(json.loads(sys.stdin.read()).values())
    print(list(op(values, axis=0)))
