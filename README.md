# Documentation claim auditor

An offline static auditor that compares documentation promises with Python call evidence. It reads the root README and Markdown files beneath any docs directory. Source is parsed as syntax and never executed. No network or telemetry is used.

## Installation and usage

Requires Python 3.9 or newer.

```sh
python3 -m pip install .
music-transcription-claim-audit /path/to/project
python3 -m music_transcription_claim_audit /path/to/project --json
music-transcription-claim-audit --version
```

Use `--verbose` for inspected paths and evidence flags, `--ignore PATH` for a repeatable relative path prefix, and `--fail-on MEDIUM` to fail on test evidence alone. The default threshold is HIGH. Exit status is 0 below the threshold, 2 for findings meeting it, and 1 for usage or I/O errors.

## Rules

Documentation is matched by exact normalized phrases with word boundaries. Normalization lowercases text, expands negative contractions, replaces hyphens with spaces, and collapses whitespace. Negative spans are removed before affirmative matching. Fenced blocks are excluded; inline code counts.

Each source module is inspected independently. Symbol aliases are resolved statically. Local function and method definitions suppress generic evidence. Symlinks and source under fixtures, docs, or examples directories are excluded. Test evidence is recorded separately. Invalid syntax supplies no evidence.

The recognized call patterns and finding identifiers are:

```text
basic_pitch: predict or predict_and_save
piano_transcription_inference: PianoTranscription plus transcribe
Generic named operations: see music_transcription_claim_audit/ audit.py
documented-music-transcription-claim-false HIGH
Same identifier with MEDIUM when evidence exists only in tests
documented-no-music-transcription-claim-false HIGH
```

These are static indicators, not proof of runtime correctness. Imports alone and adjacent audio operations supply no evidence. A positive promise without source produces a finding; a negative promise without source passes.

## Development

```sh
python3 -m unittest discover
python3 -m build
```

MIT licensed.
