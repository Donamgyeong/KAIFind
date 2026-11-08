"""Download a fixed model revision; inference itself never accesses the network."""
import argparse
import hashlib
import json
from pathlib import Path

from library.text_analysis_types import MODEL_ID, MODEL_REVISION
from library.translation_runtime import OPTIONAL_ASSETS, REQUIRED_ASSETS


ASSETS = REQUIRED_ASSETS + OPTIONAL_ASSETS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, default=Path('/app/.cache/text-analysis'))
    args = parser.parse_args()
    from huggingface_hub import snapshot_download

    directory = args.directory
    directory.mkdir(parents=True, exist_ok=True)
    snapshot_download(MODEL_ID, revision=MODEL_REVISION, allow_patterns=list(ASSETS), local_dir=directory)
    missing = [name for name in REQUIRED_ASSETS if not (directory / name).is_file()]
    if missing:
        raise SystemExit('Model download incomplete')
    manifest = {
        'model_name': MODEL_ID, 'revision': MODEL_REVISION,
        'files': {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                  for name in sorted(ASSETS) if (directory / name).is_file()},
    }
    temporary = directory / 'assets.json.tmp'
    temporary.write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
    temporary.replace(directory / 'assets.json')
    print(f'Prepared {MODEL_ID} at revision {MODEL_REVISION}')


if __name__ == '__main__':
    main()
