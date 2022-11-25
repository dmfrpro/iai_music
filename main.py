import random
from enum import Enum
from typing import Union

import mido
import music21


class Note:
    midi_value: int
    octave_value: int
    octave: int

    start_delay: int
    playtime: int

    def __init__(self, midi_value: int, start_delay: int, playtime: int):

        if not (21 <= midi_value <= 108):
            raise ValueError('Cannot create note: invalid midi_value')
        elif playtime < 0:
            raise ValueError('Cannot create note: invalid playtime')

        self.midi_value = midi_value
        self.octave_value = midi_value % 12
        self.start_delay = start_delay
        self.playtime = playtime
        self.octave = (midi_value - 12) // 12

    def __eq__(self, other):
        return isinstance(other, Note) and self.octave_value == other.octave_value

    def __len__(self):
        return self.start_delay + self.playtime


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
        self.notes = [Note(i, 0, note.playtime) for i in chord_midi_values]
        self.pattern = pattern
        self.order_index = order_index

    def fitness(
            self,
            scale: "Scale",
            playing_bar: "Bar",
            equal_pattern_factor: int = 2000,
            equal_note_factor: int = 10e5,
            preferred_distance: int = 4,
            distance_penalty: int = 10e9
    ) -> int:
        value = equal_pattern_factor if scale.pattern == self.pattern else 0

        for i in range(len(self.notes)):
            for j in range(len(playing_bar.notes)):
                if self.notes[i] == playing_bar.notes[j]:
                    value += equal_note_factor * (len(self.notes) - i)

        distances = [
            abs(playing_note.octave_value - note.octave_value)
            for playing_note in playing_bar.notes for note in self.notes
        ]

        if any(distance < preferred_distance for distance in distances):
            value -= distance_penalty

        return value

    def __eq__(self, other):
        return isinstance(other, Chord) and self.notes == other.notes


class Scale:
    __MAJOR_STEPS = [0, 2, 4, 5, 7, 9, 11]
    __MINOR_STEPS = [0, 2, 3, 5, 7, 8, 10]

    __SHARP_LITERALS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'C#', 'A', 'A#', 'B']
    __FLAT_LITERALS = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B']

    __MAJOR_PATTERNS = [
        Pattern.MAJOR,
        Pattern.MINOR,
        Pattern.MINOR,
        Pattern.MAJOR,
        Pattern.MAJOR,
        Pattern.MINOR,
        Pattern.DIMINISHED
    ]

    __MINOR_PATTERNS = [
        Pattern.MINOR,
        Pattern.DIMINISHED,
        Pattern.MAJOR,
        Pattern.MINOR,
        Pattern.MINOR,
        Pattern.MAJOR,
        Pattern.MAJOR
    ]

    initial_note: Note
    pattern: Pattern
    chords: list[Chord]

    def __init__(self, melody: "Melody", literal: str, pattern: Pattern, playtime: int = 384):
        midi_value = Scale.__SHARP_LITERALS.index(literal) + 24 + 12 * max(melody.notes[0].octave - 3, 2)

        self.initial_note = Note(midi_value, 0, playtime)
        self.pattern = pattern

        patterns = Scale.__MAJOR_PATTERNS if pattern == Pattern.MAJOR else Scale.__MINOR_PATTERNS
        steps = Scale.__MAJOR_STEPS if pattern == Pattern.MAJOR else Scale.__MINOR_STEPS

        if len(patterns) != len(steps):
            raise ValueError('Different lengths of patterns and steps while generating consonant chords')

        notes = [
            Note(self.initial_note.midi_value + i, 0, playtime)
            for i in steps
        ]

        self.chords = [
            Chord(notes[i], patterns[i], playtime)
            for i in range(len(patterns))
        ]

    def __str__(self):
        value = Scale.__FLAT_LITERALS[self.initial_note.octave_value]
        return value + 'm' if self.pattern == Pattern.MINOR else value


class Progression:
    chords: list[Chord]

    def __init__(self, chords: list[Chord]):
        self.chords = chords

    @staticmethod
    def random_progression(scale: Scale, melody: "Melody") -> "Progression":
        chords = [
            scale.chords[random.randint(0, len(scale.chords) - 1)]
            for _ in range(len(melody.bars))
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
            scale: Scale,
            invoke_prob: float = 0.2,
            change_prob: float = 0.8,
            shift_limit: int = 3
    ) -> "Progression":
        if random.random() < invoke_prob:
            for i in range(len(self.chords)):
                if random.random() > change_prob:
                    new_index = \
                        (self.chords[i].order_index + random.randint(0, shift_limit - 1)) \
                        % len(scale.chords)

                    self.chords[i] = scale.chords[new_index]

        return self

    def fitness(
            self,
            scale: Scale,
            melody: "Melody",
            perfect_chord_factor: int = 500,
            imperfect_chord_penalty: int = 3000,
            equal_scale_factor: int = 500,
            repetition_factor: int = 1000,
            repetition_penalty: int = -10e6
    ):
        value = 0

        previous_chord = None
        for i in range(len(self.chords)):
            value += self.chords[i].fitness(scale, melody.bars[i]) * perfect_chord_factor

            value += equal_scale_factor \
                if (self.chords[i].pattern == scale.pattern) else -imperfect_chord_penalty

            value += repetition_factor \
                if self.chords[i] != previous_chord else repetition_penalty

            previous_chord = self.chords[i]

        return value


class Bar:
    notes: list[Note]

    def primary_note(self) -> Union[Note, None]:
        if len(self.notes) == 0:
            return None

        return sorted(self.notes, key=lambda note: note[0].playtime)[0]

    def __init__(self, notes: list[Note]):
        self.notes = notes

    def __len__(self):
        return sum(len(note) for note in self.notes)


class Melody:
    notes: list[Note]
    bars: list[Bar]

    def __put_note(self, note: Note, sep: int = 384):
        if len(self.bars) == 0:
            self.bars.append(Bar([]))

        if len(self.bars[-1]) + len(note) < sep:
            self.bars[-1].notes.append(note)

        elif len(self.bars[-1]) + len(note) == sep:
            self.bars[-1].notes.append(note)
            self.bars.append(Bar([]))

        elif len(self.bars[-1]) + note.start_delay == sep:
            self.bars.append(Bar([Note(note.midi_value, 0, note.playtime)]))

        elif len(self.bars[-1]) + note.start_delay > sep:
            patched = Note(
                note.midi_value,
                note.start_delay - (sep - len(self.bars[-1])),
                note.playtime
            )

            self.bars.append(Bar([patched]))

        else:

            #  TODO: Include spacing

            first_half = Note(note.midi_value, note.start_delay, sep - len(self.bars[-1]))
            self.bars[-1].notes.append(first_half)

            for _ in range((note.playtime - first_half.playtime) // sep):
                partial = Note(note.midi_value, 0, sep)
                self.bars.append(Bar([partial]))

            remainder = (note.playtime - first_half.playtime) % sep
            if remainder > 0:
                partial_remainder = Note(note.midi_value, 0, remainder)
                self.bars.append(Bar([partial_remainder]))

    def __init__(self, notes: list[Note]):
        self.notes = notes
        self.bars = []

        for note in self.notes:
            self.__put_note(note)

        del self.bars[-1]


class EvolutionaryAlgorithm:

    @staticmethod
    def __get_random_parents(survived: list[Progression]) -> (Progression, Progression):
        return tuple(random.sample(survived, 2))

    @staticmethod
    def __normalized(progression: Progression, melody: Melody) -> Progression:
        if len(melody.bars) != len(progression.chords):
            raise ValueError('Different progression and melody quarts length')

        if len(melody.bars[0].notes) == 0 and len(progression.chords) > 1:
            progression.chords[0] = progression.chords[1]

        for i in range(1, len(progression.chords)):
            if len(melody.bars[i].notes) == 0:
                progression.chords[i] = progression.chords[i - 1]

        return progression

    @staticmethod
    def best_progression(
            melody: "Melody",
            scale: Scale,
            generation_limit: int = 1000,
            population_size: int = 100,
            selection_factor: int = 10
    ) -> Progression:
        if selection_factor > population_size:
            raise AttributeError('Invalid selection factor')

        print('Learning process started...')

        population = [
            Progression.random_progression(scale, melody)
            for _ in range(population_size)
        ]

        for _ in range(generation_limit):
            population = sorted(population, key=lambda p: p.fitness(scale, melody))
            survived = population[-selection_factor:]

            for _ in range(population_size - selection_factor):
                random_index = random.randint(0, selection_factor - 1)
                parent1, parent2 = EvolutionaryAlgorithm.__get_random_parents(survived)

                survived.append(survived[random_index].crossover(parent1, parent2).mutate(scale))

            population = survived

        population = sorted(population, key=lambda p: p.fitness(scale, melody))
        print('Learning process ended.')

        return EvolutionaryAlgorithm.__normalized(population[-1], melody)


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
            track_name: str = 'Grand Piano (Classic)',
            velocity: int = 25
    ):
        new_track = mido.MidiTrack()
        new_track.append(mido.MetaMessage(track_type, name=track_name))
        new_track.append(mido.Message('program_change', program=0, time=0))

        for note in notes:
            new_track += MidiHelper.__midi_event_pair(note, velocity=velocity)

        new_track.append(mido.MetaMessage('end_of_track', time=0))
        file.tracks.append(new_track)

    @staticmethod
    def append_progression(
            file: mido.MidiFile,
            progression: Progression,
            track_type: str = 'track_name',
            track_name: str = 'Grand Piano (Classic)',
            velocity: int = 25
    ):
        for i in range(len(progression.chords[0].notes)):
            MidiHelper.__append_track(
                file,
                [chord.notes[i] for chord in progression.chords],
                track_type=track_type,
                track_name=track_name,
                velocity=velocity
            )

    @staticmethod
    def melody(file: mido.MidiFile) -> "Melody":
        all_notes = []

        for track in file.tracks:
            all_notes += [msg for msg in track]

        notes = []
        start_delay = 0

        for msg in all_notes:
            if msg.type == 'note_on':
                start_delay = msg.time
            elif msg.type == 'note_off':
                notes.append(Note(msg.note, start_delay, msg.time))

        return Melody(notes)


filenames = ['barbiegirl_mono.mid', 'input1.mid', 'input2.mid', 'input3.mid']
for index, filename in enumerate(filenames):
    input_file = mido.MidiFile(filename)
    input_melody = MidiHelper.melody(input_file)
    print(f'Successfully parsed {filename}')

    detected_key = music21.converter.parse(filename).analyze('key')
    input_literal, pattern_str = detected_key.name.split()
    print(f'Detected key: {input_literal} {pattern_str}')

    detected_scale = Scale(input_melody, input_literal, Pattern[pattern_str.upper()])
    best_progression = EvolutionaryAlgorithm.best_progression(input_melody, detected_scale)
    MidiHelper.append_progression(input_file, best_progression)

    print(f'Output file is: DmitriiAlekhinOutput{index + 1}-{detected_scale}.mid\n')
    input_file.save(f'DmitriiAlekhinOutput{index + 1}-{detected_scale}.mid')
