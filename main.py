from enum import Enum
from typing import List
import mido


class Note:
    midi_value: int
    octave_value: int
    octave: int
    playtime: int

    def __init__(self, midi_value: int, playtime: int):

        if not (21 <= midi_value <= 108):
            raise ValueError('Cannot create note: invalid midi_value')
        elif playtime < 0:
            raise ValueError('Cannot create note: invalid playtime')

        self.midi_value = midi_value
        self.octave_value = midi_value % 12
        self.playtime = playtime
        self.octave = (midi_value - 12) // 12


class Pattern(Enum):
    MAJOR = [0, 4, 7]
    MINOR = [0, 3, 7]
    DIMINISHED = [0, 3, 9]


class Chord:
    notes: List[Note]

    def __init__(self, note: Note, pattern: Pattern):
        if not isinstance(pattern.value, List):
            raise TypeError('Pattern value is not an iterable object')

        chord_midi_values = (i + note.midi_value for i in pattern.value)
        self.notes = [Note(i, note.playtime) for i in chord_midi_values]


class MidiHelper:

    def __init__(self):
        raise AssertionError('Utility class MidiHelper cannot be directly created')

    @staticmethod
    def __midi_event_pair(note: Note):
        return [
            mido.Message('note_on', note=note.midi_value, time=0, velocity=50),
            mido.Message('note_off', note=note.midi_value, time=note.playtime, velocity=0)
        ]

    @staticmethod
    def __append_track(
            file: mido.MidiFile,
            notes: List[Note],
            track_type: str = 'track_name',
            track_name: str = 'Elec. Piano (Classic)'
    ):
        new_track = mido.MidiTrack()
        new_track.append(mido.MetaMessage(track_type, name=track_name))
        new_track.append(mido.Message('program_change', program=12, time=0))

        for note in notes:
            new_track += MidiHelper.__midi_event_pair(note)

        file.tracks.append(new_track)

    @staticmethod
    def append_chords(file: mido.MidiFile, chords: [Chord]):
        new_tracks_len = max(len(chord.notes) for chord in chords)

        for i in range(new_tracks_len):
            MidiHelper.__append_track(
                file,
                [chord.notes[i] for chord in chords],
                track_name=f'chord_{i}'
            )

    @staticmethod
    def collect_notes(file: mido.MidiFile) -> List[Note]:
        all_notes = []

        for track in file.tracks:
            all_notes += [msg for msg in track]

        filtered = (msg for msg in all_notes if msg.type == 'note_off')
        return [Note(msg.note, msg.time) for msg in filtered]


class MajorKey:
    __MAJOR_STEPS = [0, 2, 4, 5, 7, 9, 11]

    __PATTERNS = [
        Pattern.MAJOR,
        Pattern.MINOR,
        Pattern.MINOR,
        Pattern.MAJOR,
        Pattern.MAJOR,
        Pattern.MINOR,
        Pattern.DIMINISHED
    ]

    initial_note: Note
    chords: [Chord]

    @staticmethod
    def __find_best_major_key(notes: List[Note]) -> Note:
        if notes is None or len(notes) == 0:
            raise ValueError('Notes list is invalid')

        all_styles = {}

        for note in notes:
            all_styles[note.octave_value] = \
                {(i + note.octave_value) % 12 for i in MajorKey.__MAJOR_STEPS}

        notes_octave_values = {note.octave_value for note in notes}
        result = {}
        octave_value = -1

        for note, styles in all_styles.items():
            common_major = notes_octave_values & styles

            if len(common_major) > len(result):
                result = common_major
                octave_value = note

        return Note((octave_value + 24) + 12, notes[0].playtime)

    def __init__(self, notes: List[Note]):
        self.initial_note = MajorKey.__find_best_major_key(notes)

        midi_value = self.initial_note.midi_value
        playtime = self.initial_note.playtime

        self.chords = [
            Chord(Note(midi_value + i, playtime), MajorKey.__PATTERNS[i])
            for i in range(len(MajorKey.__PATTERNS))
        ]

    def __str__(self):
        literals = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'C#', 'A', 'A#', 'B']
        return literals[self.initial_note.octave_value]


filenames = ['barbiegirl_mono.mid', 'input1.mid', 'input2.mid', 'input3.mid']
for index, filename in enumerate(filenames):
    input_file = mido.MidiFile(filename)
    detected_key = MajorKey(MidiHelper.collect_notes(input_file))

    MidiHelper.append_chords(input_file, detected_key.chords)
    input_file.save(f'DmitriiAlekhinOutput{index + 1}-{detected_key}.mid')
