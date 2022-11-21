from enum import Enum
import random
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

    def __eq__(self, other):
        return isinstance(other, Note) and self.octave_value == other.octave_value


class Pattern(Enum):
    MAJOR = [0, 4, 7]
    MINOR = [0, 3, 7]
    DIMINISHED = [0, 3, 6]


class Chord:
    notes: list[Note]
    pattern: Pattern
    order_index: int

    def __init__(self, note: Note, pattern: Pattern, order_index: int):
        if not isinstance(pattern.value, list):
            raise TypeError('Pattern value is not an iterable object')

        chord_midi_values = (i + note.midi_value for i in pattern.value)
        self.notes = [Note(i, note.playtime) for i in chord_midi_values]
        self.pattern = pattern
        self.order_index = order_index

    def fitness(self, playing_note: Note, equal_note_factor: int = 5, distance_factor: int = 1) -> int:
        value = 0

        for i in range(len(self.notes)):
            if self.notes[i] == playing_note:
                value += equal_note_factor * (3 - (i + 1))

            value -= distance_factor * (11 - self.notes[i].octave_value - playing_note.octave_value)

        return value

    def __eq__(self, other):
        return isinstance(other, Chord) and self.notes == other.notes


class MidiHelper:

    def __init__(self):
        raise AssertionError('Utility class MidiHelper cannot be directly created')

    @staticmethod
    def __midi_event_pair(note: Note, velocity: int = 30):
        return [
            mido.Message('note_on', note=note.midi_value, time=0, velocity=velocity),
            mido.Message('note_off', note=note.midi_value, time=note.playtime, velocity=0)
        ]

    @staticmethod
    def __append_track(
            file: mido.MidiFile,
            notes: list[Note],
            track_type: str = 'track_name',
            track_name: str = 'Elec. Piano (Classic)',
            velocity: int = 30
    ):
        new_track = mido.MidiTrack()
        new_track.append(mido.MetaMessage(track_type, name=track_name))
        new_track.append(mido.Message('program_change', program=0, time=0))

        for note in notes:
            new_track += MidiHelper.__midi_event_pair(note, velocity=velocity)

        new_track.append(mido.MetaMessage('end_of_track', time=0))
        file.tracks.append(new_track)

    @staticmethod
    def append_chords(file: mido.MidiFile, chords: list[Chord], velocity: int = 30):
        for i in range(len(chords[0].notes)):
            MidiHelper.__append_track(
                file,
                [chord.notes[i] for chord in chords],
                track_name=f'chord_{i}',
                velocity=velocity
            )

    @staticmethod
    def collect_notes(file: mido.MidiFile) -> list[Note]:
        all_notes = []

        for track in file.tracks:
            all_notes += [msg for msg in track]

        filtered = filter(lambda x: x.type == 'note_off', all_notes)
        return [Note(msg.note, msg.time) for msg in filtered]


class Key:
    __MAJOR_STEPS = [0, 2, 4, 5, 7, 9, 11]

    __MAJOR_PATTERNS = [
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
    def __best_key(notes: list[Note]) -> (Note, Pattern):
        if notes is None or len(notes) == 0:
            raise ValueError('Notes list is invalid')

        major_styles = {}

        for note in notes:
            major_styles[note.octave_value] = \
                {(i + note.octave_value) % 12 for i in Key.__MAJOR_STEPS}

        notes_octave_values = {note.octave_value for note in notes}
        result = {}
        octave_value = -1

        for note, styles in major_styles.items():
            common_major = notes_octave_values & styles

            if len(common_major) > len(result):
                result = common_major
                octave_value = note

        return Note((octave_value + 24) + 12, notes[0].playtime), Pattern.MAJOR

    def __init__(self, notes: list[Note]):
        self.initial_note, pattern = Key.__best_key(notes)

        midi_value = self.initial_note.midi_value
        playtime = self.initial_note.playtime

        self.chords = [
            Chord(Note(midi_value + i, playtime), Key.__MAJOR_PATTERNS[i], i)
            for i in range(len(Key.__MAJOR_PATTERNS))
        ]

    def __str__(self):
        literals = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'C#', 'A', 'A#', 'B']
        return literals[self.initial_note.octave_value]


class Progression:
    chords: list[Chord]

    def __init__(self, chords: list[Chord]):
        self.chords = chords

    @staticmethod
    def random_progression(key: Key, notes: list[Note]) -> "Progression":
        chords = [
            key.chords[random.randint(0, len(key.chords) - 1)]
            for _ in range(len(notes))
        ]

        return Progression(chords)

    @staticmethod
    def crossover(
            parent1: "Progression",
            parent2: "Progression",
            prob: float = 0.2
    ) -> "Progression":
        chords = [
            parent2.chords[i] if random.random() > prob else parent1.chords[i]
            for i in range(min(len(parent1.chords), len(parent2.chords)))
        ]

        return Progression(chords)

    def mutate(
            self,
            key: Key,
            invoke_prob:
            float = 0.05,
            change_prob: float = 0.1,
            shift_limit: int = 3
    ) -> "Progression":
        if random.random() < invoke_prob:
            for i in range(len(self.chords)):
                if random.random() > change_prob:
                    new_index = \
                        (self.chords[i].order_index + random.randint(0, shift_limit - 1)) \
                        % len(key.chords)

                    self.chords[i] = key.chords[new_index]

        return self

    def fitness(
            self,
            notes: [Note],
            equal_note_factor: int = 20,
            repetition_factor: int = 10
    ):
        value = 0

        previous_chord = None
        for i in range(len(self.chords)):
            value += self.chords[i].fitness(notes[i]) * equal_note_factor

            value += repetition_factor \
                if self.chords[i] != previous_chord else -repetition_factor

            previous_chord = self.chords[i]

        return value


class EvolutionaryAlgorithm:

    @staticmethod
    def __get_random_parents(survived: list[Progression]) -> (Progression, Progression):
        return tuple(random.sample(survived, 2))

    @staticmethod
    def best_progression(
            notes: list[Note],
            key: Key,
            generation_limit: int = 500,
            population_size: int = 100,
            selection_factor: int = 10
    ) -> Progression:
        if selection_factor > population_size:
            raise AttributeError('Invalid selection factor')

        population = [Progression.random_progression(key, notes) for _ in range(population_size)]

        for _ in range(generation_limit):
            survived = sorted(population, key=lambda p: p.fitness(notes))[:selection_factor]

            for _ in range(population_size - selection_factor):
                random_index = random.randint(0, selection_factor - 1)
                parent1, parent2 = EvolutionaryAlgorithm.__get_random_parents(survived)

                survived.append(survived[random_index].crossover(parent1, parent2).mutate(key))

            population = survived

        population = sorted(population, key=lambda p: p.fitness(notes))
        return population[0]


filenames = ['barbiegirl_mono.mid', 'input1.mid', 'input2.mid', 'input3.mid']
for index, filename in enumerate(filenames):
    input_file = mido.MidiFile(filename)

    input_notes = MidiHelper.collect_notes(input_file)
    detected_key = Key(input_notes)

    progression = EvolutionaryAlgorithm.best_progression(input_notes, detected_key)

    MidiHelper.append_chords(input_file, progression.chords, velocity=30)
    input_file.save(f'DmitriiAlekhinOutput{index + 1}-{detected_key}.mid')
