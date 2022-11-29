from random import random, randint, sample
from enum import Enum
from os import listdir, curdir
from re import match, sub
from sys import argv

import mido
import music21


class Note:
    midi_value: int
    octave_value: int
    octave: int

    start_delay: int
    playtime: int

    def change_octave(self, factor: int):
        return Note(self.midi_value + 12 * factor, self.start_delay, self.playtime)

    def __init__(self, midi_value: int, start_delay: int, playtime: int):
        if not (0 <= midi_value <= 127):
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


class Mode(Enum):
    MAJOR = [0, 4, 7]
    MINOR = [0, 3, 7]
    DIM = [0, 3, 6]


class Chord:
    notes: list[Note]
    mode: Mode
    playtime: int
    is_inverted: bool

    def __init__(self, note: Note, mode: Mode, playtime: int = 384):
        if not isinstance(mode.value, list):
            raise TypeError('Pattern value is not an iterable object')

        chord_midi_values = (i + note.midi_value for i in mode.value)
        self.notes = [Note(i, 0, playtime) for i in chord_midi_values]
        self.mode = mode
        self.playtime = playtime
        self.is_inverted = False

    def fitness(
            self,
            key_chords: "KeyChords",
            playing_bar: "Bar",
            inverted_chord_penalty: int = 200,
            perfect_chord_factor: int = 80,
            equal_note_factor: int = 400,
            preferred_distance: int = 6,
            distance_penalty: int = 10e4
    ) -> int:
        value = -inverted_chord_penalty if self.is_inverted else 0
        value += perfect_chord_factor if self in key_chords.perfect_chords else -perfect_chord_factor

        for i in range(len(self.notes)):
            for j in range(len(playing_bar.notes)):
                if self.notes[i] == playing_bar.notes[j]:
                    value += equal_note_factor * (len(self.notes) - j)

        distances = [
            abs(playing_note.octave_value - note.octave_value)
            for playing_note in playing_bar.notes for note in self.notes
        ]

        if any(distance < preferred_distance for distance in distances):
            value -= distance_penalty

        return value

    def first_inverse(self) -> "Chord":
        instance = self.__copy__()
        instance.notes = self.notes[1:]

        root = self.notes[0]
        instance.notes.append(Note(root.midi_value + 12, root.start_delay, root.playtime))
        instance.is_inverted = True

        return instance

    def second_inverse(self) -> "Chord":
        instance = self.first_inverse().first_inverse()
        instance.notes = [note.change_octave(-1) for note in instance.notes]
        return instance

    def __eq__(self, other):
        return isinstance(other, Chord) and self.notes == other.notes

    def __copy__(self):
        return Chord(self.notes[0], self.mode, self.playtime)


class KeyChords:
    __MAJOR_STEPS = [0, 2, 4, 5, 7, 9, 11]
    __MINOR_STEPS = [0, 2, 3, 5, 7, 8, 10]

    __SHARP_LITERALS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'C#', 'A', 'A#', 'B']
    __MAJOR_MODES = [Mode.MAJOR, Mode.MINOR, Mode.MINOR, Mode.MAJOR, Mode.MAJOR, Mode.MINOR, Mode.DIM]
    __MINOR_MODES = [Mode.MINOR, Mode.DIM, Mode.MAJOR, Mode.MINOR, Mode.MAJOR, Mode.MAJOR, Mode.DIM]

    initial_note: Note
    mode: Mode

    chords: list[Chord]
    perfect_chords: list[Chord]

    def __init__(self, melody: "Melody", literal: str, mode: Mode, playtime: int = 384):
        min_octave = min(note.octave for note in melody.notes)
        midi_value = KeyChords.__SHARP_LITERALS.index(literal) + 12 * max(min_octave - 1, 2)

        self.initial_note = Note(midi_value, 0, playtime)
        self.mode = mode

        patterns = KeyChords.__MAJOR_MODES if mode == Mode.MAJOR else KeyChords.__MINOR_MODES
        steps = KeyChords.__MAJOR_STEPS if mode == Mode.MAJOR else KeyChords.__MINOR_STEPS

        if len(patterns) != len(steps):
            raise ValueError('Different lengths of patterns and steps while generating consonant chords')

        notes = [Note(self.initial_note.midi_value + i, 0, playtime) for i in steps]
        chords = [Chord(notes[i], patterns[i], playtime) for i in range(len(patterns))]

        self.perfect_chords = list(filter(lambda chord: chord.mode is mode, chords))

        first_inverses = [chord.first_inverse() for chord in chords if chord.mode is not Mode.DIM]
        second_inverses = [chord.second_inverse() for chord in chords if chord.mode is not Mode.DIM]
        self.chords = chords + first_inverses + second_inverses

    def __str__(self):
        value = KeyChords.__SHARP_LITERALS[self.initial_note.octave_value]
        return value + 'm' if self.mode == Mode.MINOR else value


class Progression:
    chords: list[Chord]

    def __init__(self, chords: list[Chord]):
        self.chords = chords

    @staticmethod
    def random_progression(key_chords: KeyChords, melody: "Melody") -> "Progression":
        chords = [
            key_chords.chords[randint(0, len(key_chords.chords) - 1)]
            for _ in range(len(melody.bars))
        ]

        return Progression(chords)

    @staticmethod
    def crossover(parent1: "Progression", parent2: "Progression", prob: float = 0.2) -> "Progression":
        chords = [
            parent2.chords[i] if random() > prob else parent1.chords[i]
            for i in range(min(len(parent1.chords), len(parent2.chords)))
        ]

        return Progression(chords)

    def mutate(self, invoke_prob: float = 0.05, change_prob: float = 0.5) -> "Progression":
        if random() < invoke_prob:
            for i in range(len(self.chords)):
                if random() > change_prob:
                    random_index = randint(0, len(self.chords) - 1)
                    self.chords[i], self.chords[random_index] = self.chords[random_index], self.chords[i]

        return self

    def fitness(
            self,
            key_chords: KeyChords,
            melody: "Melody",
            perfect_chord_factor: int = 10,
            imperfect_chord_penalty: int = 1000,
            equal_key_chords_factor: int = 7,
            preferred_distance: int = 5,
            distance_factor: int = 10e5,
            repetition_penalty: int = 10e7
    ):
        value = 0
        previous_chord = None

        for i in range(len(self.chords)):
            value += self.chords[i].fitness(key_chords, melody.bars[i]) * perfect_chord_factor

            value += equal_key_chords_factor \
                if (self.chords[i].mode == key_chords.mode) else -imperfect_chord_penalty

            if previous_chord is not None:
                max_midi_previous = max(note.midi_value for note in previous_chord.notes)
                max_midi_current = max(note.midi_value for note in self.chords[i].notes)

                value += distance_factor \
                    if abs(max_midi_current - max_midi_previous) <= preferred_distance else -distance_factor

            if self.chords[i] == previous_chord:
                value -= repetition_penalty

            previous_chord = self.chords[i]
        return value


class Bar:
    MAX_LENGTH = 384
    notes: list[Note]
    __length: int

    def append_delay(self, delay: int):
        if self.__length + delay > Bar.MAX_LENGTH:
            raise ValueError('Bar length overflow error')

        self.__length += delay

    def append_note(self, note: Note):
        if self.__length + len(note) > Bar.MAX_LENGTH:
            raise ValueError('Bar length overflow error')

        self.notes.append(note)
        self.__length += note.start_delay + note.playtime

    def __init__(self):
        self.notes = []
        self.__length = 0

    def __len__(self):
        return self.__length


class Melody:
    notes: list[Note]
    bars: list[Bar]

    def __predicate(self, bar_index: int, note_index: int) -> bool:
        return bar_index != len(self.bars) and note_index != len(self.notes)

    def __init__(self, notes: list[Note]):
        self.notes = notes

        total_length = sum(len(note) for note in notes)
        self.bars = [Bar() for _ in range(total_length // Bar.MAX_LENGTH)]

        bar_index = 0
        note_index = 0

        while self.__predicate(bar_index, note_index):
            current_note = self.notes[note_index]

            start_delay = current_note.start_delay
            playtime = current_note.playtime

            while start_delay != 0 and self.__predicate(bar_index, note_index):
                remainder = Bar.MAX_LENGTH - len(self.bars[bar_index])
                if remainder == 0:
                    bar_index += 1
                    continue

                partial_playtime = min(remainder, start_delay)
                self.bars[bar_index].append_delay(partial_playtime)
                start_delay -= partial_playtime

            while playtime != 0 and self.__predicate(bar_index, note_index):
                remainder = Bar.MAX_LENGTH - len(self.bars[bar_index])
                if remainder == 0:
                    bar_index += 1
                    continue

                partial_playtime = min(remainder, playtime)
                self.bars[bar_index].append_note(Note(current_note.midi_value, 0, partial_playtime))
                playtime -= partial_playtime

            note_index += 1


class EvolutionaryAlgorithm:
    @staticmethod
    def best_progression(
            melody: "Melody",
            key_chords: KeyChords,
            generation_limit: int = 1000,
            population_size: int = 100,
            selection_factor: int = 10
    ) -> Progression:
        print('Learning process started...')
        population = [Progression.random_progression(key_chords, melody) for _ in range(population_size)]

        for i in range(generation_limit):
            population = sorted(population, key=lambda p: p.fitness(key_chords, melody), reverse=True)
            survived = population[0:selection_factor]

            for _ in range(population_size - selection_factor):
                random_index = randint(0, selection_factor - 1)
                parent1, parent2 = tuple(sample(survived, 2))
                survived.append(survived[random_index].crossover(parent1, parent2).mutate())

            if i % 100 == 0:
                print(f'Processed generation {i} of {generation_limit}')

            population = survived

        population = sorted(population, key=lambda p: p.fitness(key_chords, melody), reverse=True)
        print('Learning process ended.')
        return population[0]


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
            name: str = 'unnamed_track',
            velocity: int = 20
    ):
        new_track = mido.MidiTrack()
        new_track.append(mido.MetaMessage(track_type, name=name))
        new_track.append(mido.Message('program_change', program=0, time=0))

        for note in notes:
            new_track += MidiHelper.__midi_event_pair(note, velocity=velocity)

        new_track.append(mido.MetaMessage('end_of_track', time=0))
        file.tracks.append(new_track)

    @staticmethod
    def append_progression(file: mido.MidiFile, progression: Progression):
        for i in range(len(progression.chords[0].notes)):
            MidiHelper.__append_track(
                file, [chord.notes[i] for chord in progression.chords],
                name=f'chord_track{i}'
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


filenames = sorted(filter(lambda x: match(r'input\d+\.mid', x), listdir(curdir))) \
    if len(argv) <= 1 else argv[1:]

for filename in filenames:
    input_file = mido.MidiFile(filename)
    input_melody = MidiHelper.melody(input_file)
    print(f'Successfully parsed {filename}')

    detected_key = music21.converter.parse(filename).analyze('key')
    input_literal, pattern_str = detected_key.name.split()
    print(f'Detected key: {input_literal} {pattern_str}')

    detected_key_chords = KeyChords(input_melody, input_literal, Mode[pattern_str.upper()])
    best_progression = EvolutionaryAlgorithm.best_progression(input_melody, detected_key_chords)
    MidiHelper.append_progression(input_file, best_progression)

    index = int(sub(r'\D', '', filename))
    print(f'Output file is: DmitriiAlekhinOutput{index}-{detected_key_chords}.mid\n')
    input_file.save(f'DmitriiAlekhinOutput{index}-{detected_key_chords}.mid')
