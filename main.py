from enum import Enum
from typing import Iterable
import mido


class Note:
    __LITERAL_VALS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'C#', 'A', 'A#', 'B']

    midi_value: int
    octave: int
    playtime: int
    literal: str

    def __init__(self, midi_value: int, playtime: int):

        if not (21 <= midi_value <= 108):
            raise ValueError('Cannot create note: invalid midi_value')
        elif playtime < 0:
            raise ValueError('Cannot create note: invalid playtime')

        self.midi_value = midi_value
        self.playtime = playtime
        self.octave = (midi_value - 12) // 12
        self.literal = Note.__LITERAL_VALS[midi_value % 12]

    def is_half_tone(self):
        return (self.midi_value % 12) in [1, 3, 6, 8, 10]


class Chord:
    class Pattern(Enum):
        MAJOR = [0, 4, 7]
        MINOR = [0, 3, 7]
        DIMINISHED = [0, 3, 9]

    notes: [Note]
    string_value: str

    def __init__(self, note: Note, pattern: Pattern):
        if not isinstance(pattern.value, Iterable):
            raise TypeError('Pattern value is not an iterable object')

        chord_midi_values = map(lambda i: i + note.midi_value, pattern.value)

        self.notes = list(map(lambda i: Note(i, note.playtime), chord_midi_values))
        self.string_value = note.literal + pattern.name[0:3].lower()


def midi_event_pair(note: Note) -> (mido.Message, mido.Message):
    return (
        mido.Message('note_on', note=note.midi_value, time=0, velocity=50),
        mido.Message('note_off', note=note.midi_value, time=note.playtime, velocity=0)
    )


def append_track(
        file: mido.MidiFile,
        notes: [Note],
        track_type: str = 'track_name',
        track_name: str = 'Elec. Piano (Classic)'
):
    new_track = mido.MidiTrack()
    new_track.append(mido.MetaMessage(track_type, name=track_name))
    new_track.append(mido.Message('program_change', program=12, time=0))

    for note in notes:
        new_track += list(midi_event_pair(note))

    file.tracks.append(new_track)


def collect_notes(track: mido.MidiTrack) -> [Note]:
    filtered = filter(lambda msg: msg.type == 'note_off', track)
    return list(map(lambda msg: Note(msg.note, msg.time), filtered))


f = mido.MidiFile('input.mid')
append_track(f, [Note(37, 192), Note(38, 192)])
f.save('output.mid')
