# Build the Level II BASIC training set.
# Downloads listings, detokenizes them, and writes JSONL. Does not run programs
# and does not start a training job.
#
#   python level2_corpus/build.py

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harvest
import build_jsonl


def main():
    # ClassicCMP [BAS].zip files are the bulk of the set. Willus is the same
    # programs one file at a time and is much slower, so it is not the default.
    # Anything already saved under raw/willus is still packed into the JSONL.
    harvest.harvest_classiccmp()
    harvest.copy_local()
    build_jsonl.build()


if __name__ == "__main__":
    main()
