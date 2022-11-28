import music21.meter
from music21.note import Note
from music21.chord import Chord
from music21.key import Key
from music21.roman import RomanNumeral
from music21.converter import parse

from os import listdir, curdir
from re import match


def harmonic_triads(key: Key) -> list[Chord]:
    numerals = ['I', 'ii', 'iii', 'IV', 'V', 'vi', 'vii/o'] \
        if key.mode == 'major' else ['i', 'ii/o', 'III+', 'iv', 'V', 'VI', 'vii/o']

    return [RomanNumeral(numeral, key) for numeral in numerals]


class Progression:
    triads: list[Chord]

    def __init__(self, triads: list[Chord]):
        self.triads = triads

    def fitness(self) -> int:
        pass


class ProgressionFactory:
    @staticmethod
    def random(sample_triads: list[Chord]) -> Progression:
        pass

    @staticmethod
    def crossed(parent1: Progression, parent2: Progression, prob: float = 0.2) -> Progression:
        pass


filenames = filter(lambda x: match(r'input\d\.mid', x), listdir(curdir))
for i, path in enumerate(filenames):
    score = parse(path)

    for el in score.recurse():
        pass

    detected_key = score.analyze('key')
    perfect_triads = harmonic_triads(detected_key)
