from __future__ import annotations

from enum import Enum


class DisciplineCode(str, Enum):
    A = "A"
    S = "S"
    M = "M"
    E = "E"
    P = "P"
    C = "C"
    F = "F"
    G = "G"
    L = "L"
    T = "T"
    I = "I"
    Q = "Q"
    UNKNOWN = "UNKNOWN"


class UnitSystem(Enum):
    UNITLESS = 0
    INCHES = 1
    FEET = 2
    MILES = 3
    MILLIMETERS = 4
    CENTIMETERS = 5
    METERS = 6
    KILOMETERS = 7
    MICROINCHES = 8
    MILS = 9
    YARDS = 10
    DECIMETERS = 13
    DECAMETERS = 14
    HECTOMETERS = 15
