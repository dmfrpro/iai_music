from random import random, randint, sample
from enum import Enum
from os import listdir, curdir
from re import match, sub

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


class Mode(Enum):
    MAJOR = [0, 4, 7]
    MINOR = [0, 3, 7]
    DIM = [0, 3, 6]


class Chord:
    notes: list[Note]
    mode: Mode
    playtime: int

    def __init__(self, note: Note, mode: Mode, playtime: int = 384):
        if not isinstance(mode.value, list):
            raise TypeError('Pattern value is not an iterable object')

        chord_midi_values = (i + note.midi_value for i in mode.value)
        self.notes = [Note(i, 0, playtime) for i in chord_midi_values]
        self.mode = mode
        self.playtime = playtime

    def fitness(
            self,
            key_chords: "KeyChords",
            playing_bar: "Bar",
            equal_pattern_factor: int = 2000,
            equal_note_factor: int = 10e5,
            preferred_distance: int = 4,
            distance_penalty: int = 10e10
    ) -> int:
        value = equal_pattern_factor if key_chords.pattern == self.mode else 0
        for i in range(len(self.notes)):

            ordered = playing_bar.ordered()
            for j in range(len(ordered)):
                if self.notes[i] == ordered[j]:
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


class KeyChords:
    __MAJOR_STEPS = [0, 2, 4, 5, 7, 9, 11]
    __MINOR_STEPS = [0, 2, 3, 5, 7, 8, 10]

    __SHARP_LITERALS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'C#', 'A', 'A#', 'B']
    __MAJOR_MODES = [Mode.MAJOR, Mode.MINOR, Mode.MINOR, Mode.MAJOR, Mode.MAJOR, Mode.MINOR, Mode.DIM]
    __MINOR_MODES = [Mode.MINOR, Mode.DIM, Mode.MAJOR, Mode.MINOR, Mode.MAJOR, Mode.MAJOR, Mode.DIM]

    initial_note: Note
    pattern: Mode
    chords: list[Chord]

    def __init__(self, melody: "Melody", literal: str, pattern: Mode, playtime: int = 384):
        midi_value = KeyChords.__SHARP_LITERALS.index(literal) + 24 + 12 * max(melody.notes[0].octave - 3, 2)

        self.initial_note = Note(midi_value, 0, playtime)
        self.pattern = pattern

        patterns = KeyChords.__MAJOR_MODES if pattern == Mode.MAJOR else KeyChords.__MINOR_MODES
        steps = KeyChords.__MAJOR_STEPS if pattern == Mode.MAJOR else KeyChords.__MINOR_STEPS

        if len(patterns) != len(steps):
            raise ValueError('Different lengths of patterns and steps while generating consonant chords')

        notes = [Note(self.initial_note.midi_value + i, 0, playtime) for i in steps]

        chords = [Chord(notes[i], patterns[i], playtime) for i in range(len(patterns))]
        self.chords = chords

    def __str__(self):
        value = KeyChords.__SHARP_LITERALS[self.initial_note.octave_value]
        return value + 'm' if self.pattern == Mode.MINOR else value


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
            perfect_chord_factor: int = 750,
            imperfect_chord_penalty: int = 10e6,
            max_distance: int = 15,
            distance_penalty: int = 10e8,
            equal_key_chords_factor: int = 500,
            repetition_penalty: int = 10e10
    ):
        value = 0

        previous_chord = None
        previous_bar = None

        for i in range(len(self.chords)):
            value += self.chords[i].fitness(key_chords, melody.bars[i]) * perfect_chord_factor

            value += equal_key_chords_factor \
                if (self.chords[i].mode == key_chords.pattern) else -imperfect_chord_penalty

            if self.chords[i] == previous_chord \
                    and melody.bars[i].notes != previous_bar.notes \
                    and len(previous_bar.notes) != 0:
                value -= repetition_penalty

            if previous_chord is not None:
                max_midi_value = max(note.midi_value for note in self.chords[i].notes + previous_chord.notes)
                min_midi_value = min(note.midi_value for note in self.chords[i].notes + previous_chord.notes)

                if max_midi_value - min_midi_value > max_distance:
                    value -= distance_penalty

            previous_chord = self.chords[i]
            previous_bar = melody.bars[i]

        return value


class Bar:
    MAX_LENGTH = 384
    notes: list[Note]
    __length: int

    def ordered(self) -> list[Note]:
        return sorted(self.notes, key=lambda note: note.playtime)

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
    def __append_track(file: mido.MidiFile, notes: list[Note], track_type: str = 'track_name', velocity: int = 25):
        new_track = mido.MidiTrack()
        new_track.append(mido.MetaMessage(track_type))
        new_track.append(mido.Message('program_change', program=0, time=0))

        for note in notes:
            new_track += MidiHelper.__midi_event_pair(note, velocity=velocity)

        new_track.append(mido.MetaMessage('end_of_track', time=0))
        file.tracks.append(new_track)

    @staticmethod
    def append_progression(file: mido.MidiFile, progression: Progression):
        for i in range(len(progression.chords[0].notes)):
            MidiHelper.__append_track(file, [chord.notes[i] for chord in progression.chords])

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


filenames = sorted(filter(lambda x: match(r'input\d+\.mid', x), listdir(curdir)))
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
