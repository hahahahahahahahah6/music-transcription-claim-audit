import ast
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from music_transcription_claim_audit.audit import audit, claims, evidence, main, GENERIC
from music_transcription_claim_audit.phrases import TRANSCRIPTION, NOTRANSCRIPTION

EXPECTED_POS = ('music transcription', 'transcribes music', 'transcribes audio to midi', 'transcribes music to midi', 'transcribes songs to midi', 'converts audio to midi', 'converts music to midi', 'converts songs to midi', 'audio to midi transcription', 'music to midi transcription', 'audio to midi conversion', 'transcribes audio into midi', 'converts audio into midi', 'detects notes in audio', 'detects musical notes', 'extracts notes from audio', 'extracts musical notes', 'transcribes notes from audio', 'identifies notes in music', 'identifies musical notes', 'transcribes a song to notes', 'transcribes music to notes', 'converts audio to notes', 'audio transcription to midi', 'song transcription', 'transcribes songs', 'detects the notes', 'extracts the notes', 'outputs midi from audio', 'generates midi from audio', 'returns midi for audio', 'produces midi from audio', 'creates midi from audio', 'audio to note transcription', 'note transcription', 'musical note transcription', 'transcribes audio to notes', 'transcribes music into midi', 'converts music into midi', 'detects notes in a song', 'identifies notes in a song', 'extracts notes from music', 'transcribes a song into midi', 'transcribes audio into notes', 'converts a song to midi', 'converts a song into midi', 'generates a midi file from audio', 'outputs a midi file from audio', 'produces notes from audio', 'automatic music transcription')
EXPECTED_NEG = ('no music transcription', 'does not transcribe music', 'without music transcription', 'no audio to midi transcription', 'does not transcribe audio to midi', 'does not convert audio to midi', 'does not transcribe music to midi', 'does not convert music to midi', 'does not detect notes in audio', 'does not extract notes from audio', 'does not transcribe notes from audio', 'does not identify musical notes', 'does not transcribe songs to midi', 'does not convert songs to midi', 'no note transcription', 'does not transcribe a song to notes', 'does not transcribe music to notes', 'does not convert audio to notes', 'does not output midi from audio', 'does not generate midi from audio', 'does not return midi for audio', 'music transcription not supported', 'audio to midi not supported', 'no midi transcription')

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def put(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)

    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            status = main([str(self.root), *args])
        return status, out.getvalue()

    def test_phrase_oracle(self):
        phrase_file = Path(__file__).resolve().parents[1] / "music_transcription_claim_audit" / "phrases.py"
        parsed = {node.targets[0].id: ast.literal_eval(node.value)
                  for node in ast.parse(phrase_file.read_text()).body
                  if isinstance(node, ast.Assign)}
        self.assertEqual(parsed["TRANSCRIPTION"], EXPECTED_POS)
        self.assertEqual(parsed["NOTRANSCRIPTION"], EXPECTED_NEG)
        self.assertEqual(TRANSCRIPTION, EXPECTED_POS)
        self.assertEqual(NOTRANSCRIPTION, EXPECTED_NEG)
        self.assertEqual(len(TRANSCRIPTION), 50)
        self.assertEqual(len(NOTRANSCRIPTION), 24)
        for phrase in EXPECTED_POS:
            self.assertEqual(claims(phrase), (True, False))
        for phrase in EXPECTED_NEG:
            self.assertEqual(claims(phrase), (False, True))

    def test_good_bad_denial(self):
        self.put('README.md', 'This transcribes music.')
        self.assertEqual(self.run_cli()[0], 2)
        result = audit(self.root)
        self.assertEqual(result['findings'][0]['id'], 'documented-music-transcription-claim-false')
        self.assertEqual(result['findings'][0]['severity'], 'HIGH')
        self.put('app.py', 'engine.transcribe_music(audio)')
        self.assertEqual(self.run_cli()[0], 0)
        self.put('README.md', 'No music transcription')
        self.assertEqual(self.run_cli()[0], 2)
        self.assertEqual(audit(self.root)['findings'][0]['id'], 'documented-no-music-transcription-claim-false')

    def test_no_source_and_no_claim(self):
        self.put('README.md', 'No music transcription')
        self.assertEqual(audit(self.root)['verdict'], 'PASS')
        self.put('README.md', 'transcribes music')
        self.assertEqual(self.run_cli()[0], 2)
        self.put('README.md', 'A useful utility')
        self.assertEqual(audit(self.root)['verdict'], 'PASS')

    def test_test_only(self):
        self.put('README.md', 'transcribes music')
        for name in ['tests/helper.py', 'test_app.py', 'app_test.py']:
            with self.subTest(name=name):
                self.put(name, 'engine.audio_to_midi(x)')
                self.assertEqual(audit(self.root)['findings'][0]['severity'], 'MEDIUM')
                self.assertEqual(self.run_cli()[0], 0)
                self.assertEqual(self.run_cli('--fail-on', 'MEDIUM')[0], 2)

    def test_markdown(self):
        for fence in ['```', '~~~', '   ````']:
            self.assertEqual(claims(fence+'\ntranscribes music\n'+fence), (False, False))
        self.assertEqual(claims('`transcribes music`'), (True, False))
        self.assertEqual(claims("doesn't transcribe music"), (False, True))
        self.assertEqual(claims('AUTOMATIC MUSIC-TRANSCRIPTION'), (True, False))
        self.assertEqual(claims('xtranscribes musicology'), (False, False))
        self.assertEqual(claims('transcribes\n\nmusic'), (False, False))
        self.put('nested/docs/guide.md', 'transcribes music')
        self.assertEqual(self.run_cli()[0], 2)
        self.assertEqual(self.run_cli('--ignore', 'nested')[0], 0)

    def test_basic_routes(self):
        for source in [
            'import basic_pitch; basic_pitch.predict(x)',
            'import basic_pitch as bp; bp.inference.predict(x)',
            'import basic_pitch.inference; basic_pitch.inference.predict_and_save(x)',
            'from basic_pitch.inference import predict as p; p(x)',
            'from basic_pitch.inference import predict_and_save; predict_and_save(x)',
            'import basic_pitch as bp\ndef predict(x): pass\nbp.predict(x)',
        ]:
            with self.subTest(source=source): self.assertTrue(evidence(source))

    def test_piano_routes(self):
        for source in [
            'import piano_transcription_inference as p; model=p.PianoTranscription(); model.transcribe(x)',
            'import piano_transcription_inference; piano_transcription_inference.api.PianoTranscription().transcribe(x)',
            'from piano_transcription_inference import PianoTranscription as P; m=P(); m.transcribe(x)',
            'from piano_transcription_inference import PianoTranscription as P; P().transcribe(x)',
            'from piano_transcription_inference import PianoTranscription; m: object = PianoTranscription(); m.transcribe(x)',
        ]:
            with self.subTest(source=source): self.assertTrue(evidence(source))

    def test_generic_routes(self):
        for name in GENERIC:
            for source in ['engine.'+name+'(x)', 'from engine import '+name+' as f; f(x)', 'import '+name+' as f; f(x)']:
                with self.subTest(source=source): self.assertTrue(evidence(source))
            self.assertFalse(evidence(name+'(x)'))
            self.assertFalse(evidence('def '+name+'(x): pass\nengine.'+name+'(x)'))
            self.assertFalse(evidence('from engine import '+name+' as f\ndef f(x): pass\nf(x)'))

    def test_not_evidence(self):
        sources = [
            'import basic_pitch', 'import piano_transcription_inference',
            'librosa.load(x)', 'soundfile.read(x)', 'wave.open(x).readframes(1)', 'torchaudio.load(x)',
            'mic.listen()', 'mic.record()', 'sounddevice.rec()', 'pyaudio.open().read()', 'audio.play()',
            'whisper.transcribe(x)', 'recognizer.recognize_google(x)', 'engine.stt(x)', 'engine.say(x)',
            'webrtcvad.is_speech(x)', 'silero.get_speech_timestamps(x)', 'pyannote.segmentation(x)',
            'pvporcupine.create(); openwakeword.Model().predict(x); engine.detect_keyword(x)',
            'speechbrain.verify_files(x,y); resemblyzer.VoiceEncoder(); engine.verify_speaker(x)',
            'pyannote.Pipeline.from_pretrained(x); engine.diarize(x)',
            'noisereduce.reduce_noise(x); df.enhance(x); engine.suppress_noise(x); engine.remove_noise(x)',
            'acoustid.fingerprint_file(x); Dejavu().recognize(x); engine.fingerprint_audio(x)',
            'PANNs.AudioTagging().inference(x); YAMNet(x); engine.detect_sound_event(x)',
            'pipeline("audio-classification")(x)', 'demucs.separate(x); spleeter.Separator().separate(x); engine.separate_stems(x)',
            'librosa.beat.beat_track(x); aubio.tempo(x); essentia.RhythmExtractor()(x)',
            'librosa.yin(x); librosa.piptrack(x); crepe.predict(x); aubio.pitch(x); parselmouth.to_pitch(x)',
            'librosa.onset.onset_detect(x); librosa.onset.onset_strength(x); engine.detect_onsets(x)',
            'librosa.feature.chroma_cqt(x); librosa.feature.chroma_cens(x); librosa.feature.chroma_stft(x); librosa.feature.mfcc(x); essentia.Chromagram()(x)',
            'essentia.ChordsDetection()(x); essentia.ChordsDetectionBeats()(x); engine.detect_chords(x)',
            'essentia.KeyExtractor()(x); engine.detect_key(x)',
            'pretty_midi.PrettyMIDI(); pretty_midi.Instrument(0); pretty_midi.Note(1,2,3,4); music21.Note(x); music21.Stream(x); music21.Part(x)',
            'music21.render(x); verovio.render(x); lilypond.render(x)', 'hashlib.md5(x); hashlib.sha256(x)',
            'engine.filter(x); engine.equalize(x)', 'engine.mix(x)', 'engine.normalize(x)',
            'engine.detect_language(x)', 'engine.translate(x)',
            'basic_pitch.predict(x)', 'other.predict(x)',
            'import piano_transcription_inference as p; p.PianoTranscription()', 'other.transcribe(x)',
            'subprocess.run(["basic-pitch", "input.wav"])', '"basic_pitch.predict(x)"',
            'import basic_pitch; basic_pitch.predict', 'invalid syntax !',
            'class Local:\n def detect_notes(self): pass\nengine.detect_notes(x)',
        ]
        for source in sources:
            with self.subTest(source=source): self.assertFalse(evidence(source))

    def test_single_module(self):
        self.put('README.md', 'transcribes music')
        self.put('a.py', 'import piano_transcription_inference as p; model=p.PianoTranscription()')
        self.put('b.py', 'model.transcribe(x)')
        self.assertFalse(audit(self.root)['production_evidence'])

    def test_exclusions(self):
        self.put('README.md', 'transcribes music')
        for name in ['fixtures/a.py', 'docs/a.py', 'examples/a.py']:
            self.put(name, 'engine.detect_notes(x)')
        self.assertFalse(audit(self.root)['production_evidence'])
        outside = self.root.parent / (self.root.name + '-external.py')
        outside.write_text('engine.detect_notes(x)')
        self.addCleanup(outside.unlink)
        (self.root/'linked.py').symlink_to(outside)
        (self.root/'linked_dir').symlink_to(self.root/'fixtures', target_is_directory=True)
        self.assertFalse(audit(self.root)['production_evidence'])

    def test_cli(self):
        self.put('README.md', 'transcribes music')
        status, output = self.run_cli('--json')
        data = json.loads(output)
        self.assertEqual(status, 2)
        self.assertEqual(data['verdict'], 'FAIL')
        self.assertIn('message', data['findings'][0])
        self.assertIn('documents', self.run_cli('--verbose')[1])
        self.assertEqual(main([str(self.root/'missing')]), 1)
        for args in [[], ['--unknown'], [str(self.root), '--fail-on', 'wrong']]:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
                main(args)
            self.assertEqual(cm.exception.code, 1)
        proc = subprocess.run([sys.executable, '-m', 'music_transcription_claim_audit', '--version'], capture_output=True, text=True)
        self.assertEqual((proc.returncode, proc.stdout.strip()), (0, '0.1.0'))

    def test_self_audit(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(audit(root)['verdict'], 'PASS')

if __name__ == '__main__':
    unittest.main()
