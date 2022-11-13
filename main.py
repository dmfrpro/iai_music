from enum import Enum
from typing import List
import mido


class Note:
    __LITERAL_VALS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'C#', 'A', 'A#', 'B']

    midi_value: int
    octave_value: int
    octave: int
    playtime: int
    literal: str

    def __init__(self, midi_value: int, playtime: int):

        if not (21 <= midi_value <= 108):
            raise ValueError('Cannot create note: invalid midi_value')
        elif playtime < 0:
            raise ValueError('Cannot create note: invalid playtime')

        self.midi_value = midi_value
        self.octave_value = midi_value % 12
        self.playtime = playtime
        self.octave = (midi_value - 12) // 12
        self.literal = Note.__LITERAL_VALS[self.octave_value]

    def is_half_tone(self):
        return (self.midi_value % 12) in [1, 3, 6, 8, 10]


class Chord:
    class Pattern(Enum):
        MAJOR = [0, 4, 7]
        MINOR = [0, 3, 7]
        DIMINISHED = [0, 3, 9]

    notes: List[Note]
    string_value: str

    def __init__(self, note: Note, pattern: Pattern):
        if not isinstance(pattern.value, List):
            raise TypeError('Pattern value is not an iterable object')

        chord_midi_values = (i + note.midi_value for i in pattern.value)

        self.notes = [Note(i, note.playtime) for i in chord_midi_values]
        self.string_value = note.literal + pattern.name[0:3].lower()


def find_harmony(notes: List[Note]) -> (str, Chord.Pattern):
    major_steps = [0, 2, 4, 5, 7, 9, 11]

    all_styles = dict()

    for note in notes:
        all_styles[note.literal] = set((i + note.octave_value) % 12 for i in major_steps)

    notes_octave_values = set(note.octave_value for note in notes)
    result = set()
    result_note = ''
    result_style = ''

    for note, styles in all_styles.items():
        common_major = notes_octave_values & styles

        if len(common_major) > len(result):
            result = common_major
            result_note = note
            result_style = Chord.Pattern.MAJOR

    return result_note, result_style


def append_track(
        file: mido.MidiFile,
        notes: List[Note],
        track_type: str = 'track_name',
        track_name: str = 'Elec. Piano (Classic)'
):
    new_track = mido.MidiTrack()
    new_track.append(mido.MetaMessage(track_type, name=track_name))
    new_track.append(mido.Message('program_change', program=12, time=0))

    for note in notes:
        new_track += [
            mido.Message('note_on', note=note.midi_value, time=0, velocity=50),
            mido.Message('note_off', note=note.midi_value, time=note.playtime, velocity=0)
        ]

    file.tracks.append(new_track)


def collect_notes(file: mido.MidiFile) -> List[Note]:
    all_notes = []

    for track in file.tracks:
        all_notes += [msg for msg in track]

    filtered = (msg for msg in all_notes if msg.type == 'note_off')
    return [Note(msg.note, msg.time) for msg in filtered]


f = mido.MidiFile('input3.mid')
append_track(f, [Note(37, 192), Note(38, 192)])
f.save('output.mid')
