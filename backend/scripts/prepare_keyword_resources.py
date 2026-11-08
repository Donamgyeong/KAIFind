"""Prepare fixed WordNet data; spaCy model is installed by requirements.txt."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

from library.keyword_resources import WORDNET_REVISION, WORDNET_URL, resource_directory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, default=resource_directory())
    args = parser.parse_args()
    directory = args.directory
    directory.mkdir(parents=True, exist_ok=True)
    corpora = directory / 'corpora'
    corpora.mkdir(exist_ok=True)
    temporary = corpora / 'wordnet.zip.tmp'
    with urllib.request.urlopen(WORDNET_URL, timeout=60) as source, temporary.open('wb') as target:
        while data := source.read(1024 * 1024):
            target.write(data)
    temporary.replace(corpora / 'wordnet.zip')
    import nltk
    nltk.data.path.insert(0, str(directory.resolve()))
    from nltk.corpus import wordnet as reader

    if reader.get_version() != '3.0':
        raise SystemExit('Unexpected WordNet corpus version')
    manifest = {
        'revision': WORDNET_REVISION, 'version': reader.get_version(),
        'sha256': hashlib.sha256((corpora / 'wordnet.zip').read_bytes()).hexdigest(),
    }
    temporary = directory / 'assets.json.tmp'
    temporary.write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
    temporary.replace(directory / 'assets.json')
    print('Prepared local WordNet 3.0 resources')


if __name__ == '__main__':
    main()
