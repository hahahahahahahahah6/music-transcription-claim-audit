"""Offline documentation and single-module syntax inspection."""
import argparse
import ast
import json
import os
from pathlib import Path
import re
import sys

from . import __version__
from .phrases import TRANSCRIPTION, NOTRANSCRIPTION

GENERIC = frozenset(('transcribe_music', 'music_transcribe', 'transcribe_to_midi', 'transcribe_audio_to_midi', 'transcribe_audio_to_notes', 'audio_to_midi', 'audio_to_notes', 'convert_audio_to_midi', 'convert_audio_to_notes', 'convert_music_to_midi', 'convert_song_to_midi', 'song_to_midi', 'music_to_midi', 'generate_midi_from_audio', 'transcribe_notes', 'detect_notes', 'extract_notes', 'note_transcription', 'transcribe_song', 'detect_musical_notes', 'extract_musical_notes', 'detect_note_sequence', 'extract_note_sequence', 'predict_notes', 'note_detect', 'transcribe_melody_to_notes', 'transcribe_piano', 'piano_transcription'))


def normalize(text):
    return re.sub(r'\s+', ' ', text.lower().replace("n't", ' not').replace('-', ' ')).strip()


def claims(text):
    lines = []
    fence = None
    for line in text.splitlines():
        match = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence) and not match[2].strip():
                fence = None
            lines.append('')
        elif match:
            fence = match[1]
            lines.append('')
        else:
            lines.append(line)
    positive = negative = False
    for paragraph in re.split(r'\n\s*\n', '\n'.join(lines)):
        value = normalize(paragraph)
        for phrase in sorted(NOTRANSCRIPTION, key=lambda x: (-len(x), x)):
            value, count = re.subn(r'\b' + re.escape(phrase) + r'\b', lambda m: ' ' * len(m[0]), value)
            negative |= bool(count)
        for phrase in sorted(TRANSCRIPTION, key=lambda x: (-len(x), x)):
            if re.search(r'\b' + re.escape(phrase) + r'\b', value):
                positive = True
                value = re.sub(r'\b' + re.escape(phrase) + r'\b', lambda m: ' ' * len(m[0]), value)
    return positive, negative


def evidence(source):
    """Recognize calls within one AST without importing or running it."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    basic, piano, imported, shadow = set(), set(), {}, set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                binding = item.asname or item.name.split('.')[0]
                if item.name.split('.')[0] == 'basic_pitch':
                    basic.add(binding)
                if item.name.split('.')[0] == 'piano_transcription_inference':
                    piano.add(binding)
                imported[binding] = ('', item.name.split('.')[-1])
        elif isinstance(node, ast.ImportFrom):
            for item in node.names:
                imported[item.asname or item.name] = (node.module or '', item.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            shadow.add(node.name)

    def route(func, bindings, module, names):
        if isinstance(func, ast.Name):
            origin, target = imported.get(func.id, ('', ''))
            return origin.split('.')[0] == module and target in names
        if isinstance(func, ast.Attribute) and func.attr in names:
            base = func.value
            while isinstance(base, ast.Attribute):
                base = base.value
            return isinstance(base, ast.Name) and base.id in bindings
        return False

    def construction(node):
        return isinstance(node, ast.Call) and route(
            node.func, piano, 'piano_transcription_inference', {'PianoTranscription'})

    instances = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and construction(node.value):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            instances.update(t.id for t in targets if isinstance(t, ast.Name))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if route(func, basic, 'basic_pitch', {'predict', 'predict_and_save'}):
            return True
        if isinstance(func, ast.Attribute):
            if func.attr == 'transcribe' and (
                construction(func.value) or
                isinstance(func.value, ast.Name) and func.value.id in instances
            ):
                return True
            if func.attr in GENERIC and func.attr not in shadow:
                return True
        elif isinstance(func, ast.Name):
            target = imported.get(func.id, ('', ''))[1]
            if target in GENERIC and target not in shadow and func.id not in shadow:
                return True
    return False


def audit(root, ignore=()):
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise OSError('Root must be a readable directory')
    prefixes = [tuple(Path(x).parts) for x in ignore if x]
    docs, sources = [], []
    production = test = positive = negative = False
    def ignored(rel):
        return any(rel.parts[:len(prefix)] == prefix for prefix in prefixes)
    def failed(error):
        raise error
    for directory, dirs, files in os.walk(root, onerror=failed, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not (Path(directory)/d).is_symlink() and not ignored((Path(directory)/d).relative_to(root)))
        for name in sorted(files):
            path = Path(directory)/name
            rel = path.relative_to(root)
            if path.is_symlink() or ignored(rel):
                continue
            if rel.as_posix() == 'README.md' or (path.suffix == '.md' and 'docs' in rel.parts[:-1]):
                docs.append(rel.as_posix())
                yes, no = claims(path.read_text(encoding='utf-8'))
                positive |= yes
                negative |= no
            if path.suffix != '.py' or set(rel.parts[:-1]) & {'fixtures', 'docs', 'examples'}:
                continue
            sources.append(rel.as_posix())
            found = evidence(path.read_text(encoding='utf-8'))
            is_test = 'tests' in rel.parts[:-1] or name.startswith('test_') or name.endswith('_test.py')
            if is_test:
                test |= found
            else:
                production |= found
    findings = []
    if positive and not production:
        findings.append({'id': 'documented-music-transcription-claim-false', 'severity': 'MEDIUM' if test else 'HIGH', 'message': 'Affirmative documentation lacks production evidence.'})
    if negative and production:
        findings.append({'id': 'documented-no-music-transcription-claim-false', 'severity': 'HIGH', 'message': 'Negative documentation conflicts with production evidence.'})
    return dict(verdict='FAIL' if findings else 'PASS', findings=findings, documents=docs, sources=sources, production_evidence=production, test_evidence=test)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, self.prog + ': error: ' + message + '\n')


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument('root')
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--ignore', action='append', default=[])
    parser.add_argument('--fail-on', choices=['LOW', 'MEDIUM', 'HIGH'], default='HIGH')
    args = parser.parse_args(argv)
    try:
        result = audit(args.root, args.ignore)
    except (OSError, UnicodeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(result['verdict'])
        for finding in result['findings']:
            print('{id} {severity}: {message}'.format(**finding))
        if args.verbose:
            print(json.dumps(result, sort_keys=True))
    levels = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2}
    return 2 if any(levels[f['severity']] >= levels[args.fail_on] for f in result['findings']) else 0
