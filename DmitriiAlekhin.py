from random import random, randint, sample
from enum import Enum
from os import listdir, curdir
from re import match, sub
from sys import argv

import mido
import music21


class Note:
    """
    MIDI note class. Supports all notes with values [0, 127]
    according to Standard MIDI-File format Spec. 1.1, updated:
    https://www.music.mcgill.ca/~ich/classes/mumt306/StandardMIDIfileformat.html
    """

    midi_value: int
    """
    MIDI note value, supports all MIDI values according to 
    "Appendix 1.3 - Table of MIDI Note Numbers":
    https://www.music.mcgill.ca/~ich/classes/mumt306/StandardMIDIfileformat.html
    """

    octave_value: int
    """
    A relative note value, e.g. MIDI value % 12
    """

    octave: int
    """
    Number of octave of the note, supports all octaves according to
    "Appendix 1.3 - Table of MIDI Note Numbers":
    https://www.music.mcgill.ca/~ich/classes/mumt306/StandardMIDIfileformat.html
    """

    start_delay: int
    """
    Some notes in MIDI are suspended, so this field contains a starting delay 
    of the note, in ticks
    """

    playtime: int
    """
    Note playtime (not including start delay), in ticks
    """

    def __init__(self, midi_value: int, start_delay: int, playtime: int):
        """
        Inits a note by the given values from MIDI event according to
        "Appendix 1 - MIDI Messages":
        https://www.music.mcgill.ca/~ich/classes/mumt306/StandardMIDIfileformat.html
        :param midi_value: "note" field from MIDI-event
        :param start_delay: "time" filed from MIDI-event "note_on"
        :param playtime: "time" filed from MIDI-event "note_off"
        """
        if not (0 <= midi_value <= 127):
            raise ValueError('Cannot create note: invalid midi_value')
        elif playtime < 0:
            raise ValueError('Cannot create note: invalid playtime')
        elif start_delay < 0:
            raise ValueError('Cannot create note: invalid start_delay')

        self.midi_value = midi_value
        self.octave_value = midi_value % 12
        self.start_delay = start_delay
        self.playtime = playtime
        self.octave = (midi_value - 12) // 12

    def change_octave(self, factor: int):
        """
        Changes the octave of the note by the given factor
        :param factor: factor of changing the octave, e.g. +2 means increment
        by 2 octaves, -3 means decrement by 3 octaves
        :return: Note with changed octave by the given factor
        """
        return Note(self.midi_value + 12 * factor, self.start_delay, self.playtime)

    def __eq__(self, other: "Note"):
        return self.octave_value == other.octave_value

    def __len__(self):
        return self.start_delay + self.playtime


class Mode(Enum):
    """
    Chord and Key mode enum representation
    """

    MAJOR = [0, 4, 7]
    """
    Major mode with the list according to 0-4-7 rule:
    https://en.wikipedia.org/wiki/Triad_(music)#Construction
    ALSO USED as the mode of Key
    """

    MINOR = [0, 3, 7]
    """
    Minor mode with the list according to 3/4 rule:
    https://en.wikipedia.org/wiki/Triad_(music)#Construction
    ALSO USED as the mode of Key
    """

    DIM = [0, 3, 6]
    """
    Diminished mode with the list according to 3/4 rule:
    https://en.wikipedia.org/wiki/Triad_(music)#Construction
    NOT USED as the mode of Key
    """


class Chord:
    """
    Triad chord representation class.
    """

    __DISSONANT_DISTANCES = [0, 1, 2, 6, 9, 10, 11]
    """
    Dissonant distances
    """

    notes: list[Note]
    """
    List of MIDI notes, length is always 3
    """

    mode: Mode
    """
    Chord mode: MAJOR, MINOR, or DIM
    """

    playtime: int
    """
    Chord playtime, e.g. playtime value for all it's notes in notes: list[Note],
    start_delay for all chord's notes is 0
    """

    is_inverted: bool
    """
    Boolean flag indicating is the chord an inverted one or two times
    """

    def __init__(self, note: Note, mode: Mode, playtime: int = 384):
        """
        Initializes a chord by the given first note and mode values list
        :param note: first note of the chord (index = 0)
        :param mode: mode values list
        :param playtime: common playtime of all chord's notes
        """
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
            inverted_or_dim_chord_penalty: int = 400,
            perfect_chord_factor: int = 600,
            too_high_chord_factor: int = 10e3,
            equal_note_factor: int = 600,
            distance_factor: int = 10e4
    ) -> int:
        """
        Fitness function for the chord (used in Progression's fitness function)
        :param key_chords: available chords build from the determined key
        :param playing_bar: currently playing bar
        :param inverted_or_dim_chord_penalty: penalty factor if the chord is inverted or its mode is DIM
        :param perfect_chord_factor: fit factor if the chord is in the list of perfect chords
        :param too_high_chord_factor: fit/miss factor is the chord is too high rather than playing bar notes
        :param equal_note_factor: fit factor if the chord has the same note(s) as in playing bar notes
        playing_bar's note octave value and chord's note octave value
        :param distance_factor: factor if the distance is greater than preferred distance
        (e.g. chord is dissonant with playing_bar's notes)
        :return: evaluation result of how good is chord with respect to the playing bar
        """
        value = -inverted_or_dim_chord_penalty if self.is_inverted else inverted_or_dim_chord_penalty
        value += -inverted_or_dim_chord_penalty if self.mode is Mode.DIM else inverted_or_dim_chord_penalty
        value += perfect_chord_factor if self in key_chords.perfect_chords else -perfect_chord_factor

        value += -too_high_chord_factor if any(
            note.octave_value > playing_note.octave_value
            for note in self.notes
            for playing_note in playing_bar.notes
        ) else too_high_chord_factor

        for i in range(len(self.notes)):
            for j in range(len(playing_bar.notes)):
                if self.notes[i] == playing_bar.notes[j]:
                    value += equal_note_factor * (len(self.notes) - j)

        distances = [
            abs(playing_note.octave_value - note.octave_value)
            for playing_note in playing_bar.notes for note in self.notes
        ]

        value += -distance_factor \
            if any(min(distance, abs(12 - distance)) in Chord.__DISSONANT_DISTANCES for distance in distances) \
            else distance_factor

        return value

    def first_inverse(self) -> "Chord":
        """
        First inverse of the chord (only MINOR and MAJOR chords are supported) according to
        https://www.musikalessons.com/blog/2017/09/chord-inversions/
        :return: first inverse of the chord
        """
        if self.mode == Mode.DIM:
            raise TypeError('Chord is not invertible')

        instance = Chord(self.notes[0], self.mode, self.playtime)
        instance.notes = self.notes[1:]

        root = self.notes[0]
        instance.notes.append(Note(root.midi_value + 12, root.start_delay, root.playtime))
        instance.is_inverted = True

        return instance

    def second_inverse(self) -> "Chord":
        """
        Second inverse of the chord (with decremented octave for all its notes) according to
        https://www.musikalessons.com/blog/2017/09/chord-inversions/
        :return: first inverse of the chord with decremented octave
        """
        instance = self.first_inverse().first_inverse()
        instance.notes = [note.change_octave(-1) for note in instance.notes]
        return instance

    def __eq__(self, other):
        return isinstance(other, Chord) and self.notes == other.notes


class KeyChords:
    """
    A set of chords that are the most harmonic with the use of detected key.
    Selection of chords is done by performing roman numeral analysis:
    Major scale - https://en.wikipedia.org/wiki/Major_scale#Triad_qualities
    Minor Scale - https://en.wikipedia.org/wiki/Minor_scale#Harmony
    """

    __MAJOR_STEPS = [0, 2, 4, 5, 7, 9, 11]
    """
    Major steps: https://en.wikipedia.org/wiki/Major_scale#Structure
    """

    __MINOR_STEPS = [0, 2, 3, 5, 7, 8, 10]
    """
    Minor steps: https://en.wikipedia.org/wiki/Minor_scale#Intervals
    """

    __SHARP_LITERALS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'C#', 'A', 'A#', 'B']
    """
    Note sharp literals
    """

    __MAJOR_MODES = [Mode.MAJOR, Mode.MINOR, Mode.MINOR, Mode.MAJOR, Mode.MAJOR, Mode.MINOR, Mode.DIM]
    """
    Roman numeral analysis for the major scale triads: 
    https://en.wikipedia.org/wiki/Major_scale#Triad_qualities
    """

    __MINOR_MODES = [Mode.MINOR, Mode.DIM, Mode.MAJOR, Mode.MINOR, Mode.MAJOR, Mode.MAJOR, Mode.DIM]
    """
    Roman numeral analysis for the minor scale triads: 
    https://en.wikipedia.org/wiki/Minor_scale#Harmony
    """

    initial_note: Note
    """
    Key's initial note
    """

    mode: Mode
    """
    Key's mode
    """

    chords: list[Chord]
    """
    List of all possible good chords (chords from roman numeral analysis + their inverses)
    """

    perfect_chords: list[Chord]
    """
    A sample from chords: list[Chord] with equal mode, 
    e.g. for MINOR key it contains MINOR chords
    """

    def __init__(self, melody: "Melody", literal: str, mode: Mode, playtime: int = 384):
        """
        Initializes all sufficiently good chords according to roman numeral analysis
        :param melody: input melody
        :param literal: detected key literal
        :param mode: detected key mode
        :param playtime: overridden playtime for the chords
        """
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

        perfect_chords = list(filter(lambda chord: chord.mode is mode, chords))
        perfect_first_inverses = [chord.first_inverse() for chord in perfect_chords]
        perfect_second_inverses = [chord.second_inverse() for chord in perfect_chords]
        self.perfect_chords = perfect_chords + perfect_first_inverses + perfect_second_inverses

        first_inverses = [chord.first_inverse() for chord in chords if chord.mode is not Mode.DIM]
        second_inverses = [chord.second_inverse() for chord in chords if chord.mode is not Mode.DIM]
        self.chords = chords + first_inverses + second_inverses

    def __str__(self):
        value = KeyChords.__SHARP_LITERALS[self.initial_note.octave_value]
        return value + 'm' if self.mode == Mode.MINOR else value


class Progression:
    """
    Triads chord progression
    """

    chords: list[Chord]
    """
    Chord progression list
    """

    def __init__(self, chords: list[Chord]):
        self.chords = chords

    @staticmethod
    def random_progression(key_chords: KeyChords, melody: "Melody") -> "Progression":
        """
        Generates random progression from the given set from key_chords
        :param key_chords: key chords
        :param melody: input melody
        :return: random progression from key chords
        """
        chords = [
            key_chords.chords[randint(0, len(key_chords.chords) - 1)]
            for _ in range(len(melody.bars))
        ]

        return Progression(chords)

    @staticmethod
    def crossover(parent1: "Progression", parent2: "Progression", prob: float = 0.2) -> "Progression":
        """
        Returns a crossed progression from the given two parents
        :param parent1: first parent
        :param parent2: second parent
        :param prob: probability of replacement to second parent's chord
        :return: crossed progression from the given two parents
        """
        chords = [
            parent2.chords[i] if random() > prob else parent1.chords[i]
            for i in range(min(len(parent1.chords), len(parent2.chords)))
        ]

        return Progression(chords)

    def mutate(self, invoke_prob: float = 0.1, swap_prob: float = 0.5) -> "Progression":
        """
        Swap mutation of the chord progression
        :param invoke_prob: probability of invoke of mutation
        :param swap_prob: probability of swapping
        :return: self, but mutated
        """
        if random() < invoke_prob:
            for i in range(len(self.chords)):
                if random() > swap_prob:
                    random_index = randint(0, len(self.chords) - 1)
                    self.chords[i], self.chords[random_index] = self.chords[random_index], self.chords[i]

        return self

    def fitness(
            self,
            key_chords: KeyChords,
            melody: "Melody",
            perfect_chord_factor: int = 10,
            equal_key_chords_penalty: int = 1000,
            equal_key_chords_factor: int = 7,
            preferred_distance: int = 5,
            distance_factor: int = 10e5,
            repetition_penalty: int = 10e7
    ):
        """
        fitness function for the chord progression
        :param key_chords: key chords
        :param melody: input melody
        :param perfect_chord_factor: multiplication factor for the output of chord's fitness function
        :param equal_key_chords_penalty: penalty for the chord with not equal mode
        :param equal_key_chords_factor: fit for the chord with equal mode
        :param preferred_distance: max distance between the highest notes between neighbor chords
        :param distance_factor: fit/penalty for the good/bad distance
        :param repetition_penalty: penalty for repeated chord
        :return: evaluation result for the chord progression
        """
        value = 0
        previous_chord = None

        for i in range(len(self.chords)):
            value += self.chords[i].fitness(key_chords, melody.bars[i]) * perfect_chord_factor

            value += equal_key_chords_factor \
                if (self.chords[i].mode == key_chords.mode) else -equal_key_chords_penalty

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
    """
    Melody can be split on bars with equal time signature,
    this class represents the bars of the melody
    """

    TIME_SIGN = 384
    """
    Constant time signature
    """

    notes: list[Note]
    """
    Bar's notes list
    """

    __length: int
    """
    Bar's length (with respect to notes' delays)
    """

    def append_delay(self, delay: int):
        """
        Appends a delay to the bar
        """
        if self.__length + delay > Bar.TIME_SIGN:
            raise ValueError('Bar length overflow error')

        self.__length += delay

    def append_note(self, note: Note):
        """
        Appends a note WITHOUT DELAY to the bar
        """
        if self.__length + len(note) > Bar.TIME_SIGN:
            raise ValueError('Bar length overflow error')

        self.notes.append(note)
        self.__length += note.start_delay + note.playtime

    def __init__(self):
        self.notes = []
        self.__length = 0

    def __len__(self):
        return self.__length


class Melody:
    """
    An abstraction over the melody: notes + bars
    """

    notes: list[Note]
    """
    Melody's all notes
    """

    bars: list[Bar]
    """
    Bars list of the melody
    """

    def __predicate(self, bar_index: int, note_index: int) -> bool:
        """
        Returns flag indicating if bar and note are still available
        :param bar_index: current bar index
        :param note_index: current note index
        :return: flag indicating if bar and note are still available
        """
        return bar_index != len(self.bars) and note_index != len(self.notes)

    def __init__(self, notes: list[Note]):
        """
        Initializes notes and bars
        :param notes: input notes from MIDI file
        """
        self.notes = notes

        total_length = sum(len(note) for note in notes)
        self.bars = [Bar() for _ in range(total_length // Bar.TIME_SIGN)]

        bar_index = 0
        note_index = 0

        while self.__predicate(bar_index, note_index):
            current_note = self.notes[note_index]

            start_delay = current_note.start_delay
            playtime = current_note.playtime

            while start_delay != 0 and self.__predicate(bar_index, note_index):
                remainder = Bar.TIME_SIGN - len(self.bars[bar_index])
                if remainder == 0:
                    bar_index += 1
                    continue

                partial_playtime = min(remainder, start_delay)
                self.bars[bar_index].append_delay(partial_playtime)
                start_delay -= partial_playtime

            while playtime != 0 and self.__predicate(bar_index, note_index):
                remainder = Bar.TIME_SIGN - len(self.bars[bar_index])
                if remainder == 0:
                    bar_index += 1
                    continue

                partial_playtime = min(remainder, playtime)
                self.bars[bar_index].append_note(Note(current_note.midi_value, 0, partial_playtime))
                playtime -= partial_playtime

            note_index += 1


class EvolutionaryAlgorithm:
    """
    Evolutionary algorithm utility class
    """

    def __init__(self):
        raise AssertionError('Utility class EvolutionaryAlgorithm cannot be directly created')

    @staticmethod
    def best_progression(
            melody: "Melody",
            key_chords: KeyChords,
            generation_limit: int = 2000,
            population_size: int = 100,
            selection_factor: int = 10
    ) -> Progression:
        """
        Core implementation of evolutionary algorithm.
        crossover + mutation are used in the implementation,
        stops after generation_limit reached
        :param melody: input melody
        :param key_chords: key chords
        :param generation_limit: limit of generations tested
        :param population_size: max size of the population
        :param selection_factor: how many survived progressions left
        :return: best progression
        """
        print('Learning process started...')
        population = [Progression.random_progression(key_chords, melody) for _ in range(population_size)]

        for i in range(generation_limit):
            population = sorted(population, key=lambda p: p.fitness(key_chords, melody), reverse=True)
            survived = population[0:selection_factor]

            for _ in range(population_size - selection_factor):
                random_index = randint(0, selection_factor - 1)
                parent1, parent2 = tuple(sample(survived, 2))
                survived += [survived[random_index].crossover(parent1, parent2).mutate()]

            if i % 100 == 0:
                print(f'Processed generation {i} of {generation_limit}')

            population = survived

        population = sorted(population, key=lambda p: p.fitness(key_chords, melody), reverse=True)
        print('Learning process ended.')
        return population[0]


class MidiHelper:
    """
    Utility class for MIDI I/O
    """

    def __init__(self):
        raise AssertionError('Utility class MidiHelper cannot be directly created')

    @staticmethod
    def __midi_event_pair(note: Note, velocity: int = 30):
        """
        Returns a pair <note_on, note_off> MIDI events
        :param note: note
        :param velocity: note's overridden velocity
        :return: pair <note_on, note_off> MIDI events
        """
        return [
            mido.Message('note_on', note=note.midi_value, time=0, velocity=velocity),
            mido.Message('note_off', note=note.midi_value, time=note.playtime, velocity=0)
        ]

    @staticmethod
    def __append_track(
            file: mido.MidiFile,
            notes: list[Note],
            name: str = 'unnamed_track',
            velocity: int = 30
    ):
        """
        Appends a valid track to the MIDI file
        :param file: MIDI file
        :param notes: list of notes
        :param name: track name
        :param velocity: overridden velocity for all notes
        """
        new_track = mido.MidiTrack()
        new_track.append(mido.MetaMessage('track_name', name=name))
        new_track.append(mido.Message('program_change', program=0, time=0))

        for note in notes:
            new_track += MidiHelper.__midi_event_pair(note, velocity=velocity)

        new_track.append(mido.MetaMessage('end_of_track', time=0))
        file.tracks.append(new_track)

    @staticmethod
    def append_progression(file: mido.MidiFile, progression: Progression):
        """
        Appends a chord progression to the given MIDI file
        :param file: MIDI file
        :param progression: chord progression
        """
        for i in range(len(progression.chords[0].notes)):
            MidiHelper.__append_track(
                file, [chord.notes[i] for chord in progression.chords],
                name=f'chord_track{i}'
            )

    @staticmethod
    def melody(file: mido.MidiFile) -> "Melody":
        """
        Parses an input file to Melody instance
        :param file: input MIDI file
        :return: Melody instance
        """
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

    index_str = sub(r'\D', '', filename)
    index = int(index_str) if match(r'\d+', index_str) else filename.replace('.mid', '')

    print(f'Output file is: DmitriiAlekhinOutput{index}-{detected_key_chords}.mid\n')
    input_file.save(f'DmitriiAlekhinOutput{index}-{detected_key_chords}.mid')
