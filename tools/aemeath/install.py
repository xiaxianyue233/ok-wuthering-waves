"""Deploy the v3.8.9 Aemeath changes into a closed Windows OK-WW installation."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
from shutil import copy2
import subprocess
from tempfile import TemporaryDirectory, mkdtemp
from urllib.parse import quote
from urllib.request import Request, urlopen
from zipfile import ZIP_DEFLATED, ZipFile

from rotations import optimize_script


TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parents[1]
BACKEND_PREFIX = 'ok/device/interaction_methods/'
TITLE = "'gui_title': 'Aemeath 助手'"


def load_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def normalized_hash(data):
    return sha256(data.replace(b'\r\n', b'\n')).hexdigest()


def read_snapshot(local_source):
    snapshot = load_json(TOOLS / 'workshop-snapshot.json')
    base = f'https://raw.githubusercontent.com/GodRaymond233/xjtu-ww/{snapshot["commit"]}/workshop_bundle/'

    def load(item):
        name, expected = item
        if local_source is not None:
            data = (local_source / name).read_bytes()
        else:
            request = Request(base + quote(name), headers={'User-Agent': 'Aemeath-Workshop-Setup'})
            with urlopen(request, timeout=20) as response:
                data = response.read(2_000_000)
        if sha256(data).hexdigest() != expected:
            raise ValueError(f'Workshop file SHA-256 mismatch: {name}')
        return name, data

    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(pool.map(load, snapshot['files'].items()))


def patch_archive(name, content):
    with ZipFile(BytesIO(content)) as source:
        metadata = {item.filename: item for item in source.infolist()}
        files = {name: source.read(item) for name, item in metadata.items()}
    edits = {}
    for filename, data in files.items():
        if not filename.endswith('.py'):
            continue
        original = data.decode('utf-8-sig').replace('\r\n', '\n')
        patched = optimize_script(name, filename, original)
        if patched != original:
            edits[filename] = (original, patched)
    if not edits:
        return content, edits
    for filename, (_, patched) in edits.items():
        files[filename] = patched.encode('utf-8')
    buffer = BytesIO()
    with ZipFile(buffer, 'w', compression=ZIP_DEFLATED) as output:
        for filename, data in files.items():
            output.writestr(metadata[filename], data, compress_type=ZIP_DEFLATED)
    return buffer.getvalue(), edits


def backend_files(working, known_hashes):
    desired = {}
    originals = {}
    for rel in known_hashes:
        if not rel.startswith(BACKEND_PREFIX):
            continue
        content = (working / rel).read_bytes()
        if b'from ok.util.combat_pacing import before_press, tap_duration' in content:
            desired[rel] = content.replace(b'from ok.util.combat_pacing import', b'from src.combat.InputPacing import')
        elif b'from src.combat.InputPacing import before_press, tap_duration' not in content:
            originals[rel] = content
    if not originals:
        return desired
    with TemporaryDirectory(prefix='aemeath-input-') as directory:
        stage = Path(directory)
        for rel, data in originals.items():
            path = stage / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data.replace(b'\r\n', b'\n'))
        for rel in originals:
            subprocess.run(['git', 'apply', f'--include={rel}', str(TOOLS / 'input-backends.patch')],
                           cwd=stage, check=True)
            desired[rel] = (stage / rel).read_bytes()
    return desired


def prepare_app(working):
    known = load_json(TOOLS / 'source-hashes.json')
    upgrades = backend_files(working, known)
    for rel in (TOOLS / 'app-files.txt').read_text(encoding='utf-8').splitlines():
        upgrades[rel] = (REPO / rel).read_bytes()
    for rel, data in upgrades.items():
        path = working / rel
        if path.is_file():
            current = path.read_bytes()
            if normalized_hash(current) not in known[rel] and normalized_hash(current) != normalized_hash(data):
                raise ValueError(f'Conflicting local edit, review before installing: {rel}')
    config = (working / 'config.py').read_bytes()
    if b'version = "v3.8.9"' not in config:
        raise ValueError('Install this patch into an OK-WW v3.8.9 working directory.')
    previous_title = b"'gui_title': 'OK-WW'"
    if previous_title in config:
        upgrades['config.py'] = config.replace(previous_title, TITLE.encode('utf-8'), 1)
    for filename in ('manifest.json', 'workshop_entry.py'):
        rel = f'ok_import/local_workshop_entry/{filename}'
        data = (TOOLS / 'workshop_entry' / filename).read_bytes()
        if (working / rel).is_file() and normalized_hash((working / rel).read_bytes()) != normalized_hash(data):
            raise ValueError(f'Conflicting local workshop entry: {rel}')
        upgrades[rel] = data
    return upgrades


def prepare_workshop(working, source, app_upgrades):
    bundle = read_snapshot(source)
    catalog = json.loads(bundle['teams.json'])
    assert catalog['totalTeams'] == 54 and catalog['totalCodes'] == 82
    upgrades = {f'workshop_bundle/{name}': data for name, data in bundle.items()}
    optimized = 0
    patched_by_source = {}
    local_teams = working / "configs" / "custom_teams"
    for team in catalog['teams']:
        for item in team['codes']:
            name = item['filename']
            rel = f'workshop_bundle/codes/{name}'
            patched, edits = patch_archive(name, upgrades[rel])
            upgrades[rel] = patched
            if edits:
                optimized += 1
                for filename, (original, changed) in edits.items():
                    patched_by_source[(filename, original)] = changed
                    prior_patch = changed.replace("from src.combat.InputPacing import",
                                                  "from ok.util.combat_pacing import")
                    if prior_patch != changed:
                        patched_by_source[(filename, prior_patch)] = changed
        preferred = max(team['codes'], key=lambda item: (int(item.get('timestamp') or 0), item['filename']))
        with ZipFile(BytesIO(upgrades[f'workshop_bundle/codes/{preferred["filename"]}'])) as archive:
            members = sorted((Path(item).stem for item in archive.namelist() if item.endswith('.py')), key=str.casefold)
            assert len(members) == 3 and all(member.isidentifier() for member in members)
            key = '__'.join(members)
            if (local_teams / key).exists():
                continue
            prefix = f'configs/custom_teams/{key}'
            manifest = json.loads(archive.read('team.json'))
            manifest['code_mode'] = 'builtin'
            upgrades[f'{prefix}/team.json'] = json.dumps(manifest, indent=2, ensure_ascii=False).encode('utf-8')
            for member in members:
                builtin_path = f'src/char/{member}.py'
                upgrades[f'{prefix}/{member}.py'] = app_upgrades.get(builtin_path) or (working / builtin_path).read_bytes()
                upgrades[f'{prefix}/{member}.import.py'] = archive.read(f'{member}.py')
    assert optimized == 20
    # Update pre-imported or active copies only when their source exactly matches a snapshot version.
    if local_teams.is_dir():
        for folder in local_teams.iterdir():
            if not folder.is_dir():
                continue
            for path in folder.glob('*.py'):
                filename = path.name.replace('.import.py', '.py')
                updated = patched_by_source.get((filename, path.read_text(encoding='utf-8-sig')))
                if updated is not None:
                    upgrades[path.relative_to(working).as_posix()] = updated.encode('utf-8')
    return upgrades


def install_files(working, upgrades):
    upgrades = {rel: data for rel, data in upgrades.items()
                if not (working / rel).is_file() or (working / rel).read_bytes() != data}
    if not upgrades:
        print('All files are current.')
        return
    backup = Path(mkdtemp(prefix='aemeath-backup-', dir=working.parent))
    new_files = []
    for rel in upgrades:
        path = working / rel
        if path.is_file():
            target = backup / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            copy2(path, target)
        else:
            new_files.append(rel)
    (backup / 'added-files.json').write_text(json.dumps(new_files, ensure_ascii=False, indent=2), encoding='utf-8')
    written = []
    try:
        for rel, data in upgrades.items():
            path = working / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            stage = path.with_name(path.name + '.aemeath-tmp')
            try:
                stage.write_bytes(data)
                os.replace(stage, path)
            finally:
                stage.unlink(missing_ok=True)
            written.append(rel)
    except BaseException:
        for rel in reversed(written):
            if rel in new_files:
                (working / rel).unlink(missing_ok=True)
            else:
                copy2(backup / rel, working / rel)
        raise
    print(f'Updated {len(upgrades)} files. Backup: {backup}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--working', type=Path, required=True)
    parser.add_argument('--bundle-source', type=Path, help='Use a local copy of the original v1.3.0 workshop_bundle.')
    parser.add_argument('--app-only', action='store_true', help='Install application changes without syncing workshop archives.')
    args = parser.parse_args()
    target = args.working.resolve(strict=True)
    upgrades = prepare_app(target)
    if not args.app_only:
        upgrades.update(prepare_workshop(target, args.bundle_source, upgrades))
    install_files(target, upgrades)


if __name__ == '__main__':
    main()
