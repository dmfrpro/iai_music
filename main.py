import mido


class Note:
    __literal_vals = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'C#', 'A', 'A#', 'B']

    value: int = 0
    playtime: int = 0
    literal: str = ''

    def __init__(self, value: int, playtime: int):
        self.value = value
        self.playtime = playtime
        self.literal = Note.__literal_vals[value % 12]


def midi_event_pair(note: Note) -> (mido.Message, mido.Message):
    return (
        mido.Message('note_on', note=note.value, time=0, velocity=50),
        mido.Message('note_off', note=note.value, time=note.playtime, velocity=0)
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
