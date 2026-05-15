#script (python)

###########
# Usage:
#clingo simplify.lp x.map
###########

import clingo

SAT = "SAT"
UNSAT = "UNSAT"
UNKNOWN = "UNKNOWN"

def to_symbol(value):
    if isinstance(value, clingo.Symbol):
        return value
    if isinstance(value, int):
        return clingo.Number(value)
    if isinstance(value, str):
        return clingo.String(value)
    return value

def symbol_value(symbol):
    if not isinstance(symbol, clingo.Symbol):
        return symbol
    if symbol.type == clingo.SymbolType.Number:
        return symbol.number
    if symbol.type == clingo.SymbolType.String:
        return symbol.string
    return symbol

def symbol_name(symbol):
    return symbol.name

def symbol_args(symbol):
    return [symbol_value(arg) for arg in symbol.arguments]

def shown_symbols(model):
    return model.symbols(shown=True)

def make_fun(name, args=None):
    return clingo.Function(name, [to_symbol(arg) for arg in (args or [])])

def const_value(prg, name):
    value = prg.get_const(name)
    if value is None:
        return None
    return symbol_value(value)

def ground(prg, parts):
    converted = []
    for name, args in parts:
        converted.append((name, [to_symbol(arg) for arg in args]))
    return prg.ground(converted)

def solve_status(result):
    if result.satisfiable:
        return SAT
    if result.unsatisfiable:
        return UNSAT
    return UNKNOWN

def solve(prg, on_model=None):
    if on_model is None:
        return solve_status(prg.solve())
    return solve_status(prg.solve(on_model=on_model))

import datetime
import re
from subprocess import call
import sys
import os

PATHS = []
ATS = []
INDEX = []
ROBOTS = []


def __on_check(m):
    print("\n=== Extracting atoms for checking ")
    print(m)

    for i in shown_symbols(m):
        if symbol_name(i) == "path":
            PATHS.append(i)
        if symbol_name(i) == "at":
            ATS.append(i)
        if symbol_name(i) == "index":
            INDEX.append(i)


def skey(item):
    if symbol_name(item) == "at":
         return (symbol_args(item)[2], 0)
    if symbol_name(item) == "path":
         return (symbol_args(item)[3], symbol_args(item)[2])


def main(prg):

    ground(prg, [("base", [])])
    ground(prg, [("checking", [])])
    ret = solve(prg, on_model=__on_check)


    print(PATHS)
    print(ATS)
    print(INDEX)

    print("\n")

    INDICES = set([symbol_args(i)[0] for i in INDEX])

    ROBOTS = set ([symbol_args(i)[0] for i in PATHS])

    print("============ ROBOTS: ", ROBOTS)

    for r in ROBOTS:
         PR1 = [p for p in PATHS if r==symbol_args(p)[0]]
         PR2 = [a for a in ATS if r==symbol_args(a)[0] and  symbol_args(a)[2] not in INDICES]
         print(PR1)
         print(PR2)
         PR = PR1 + PR2
         print("============ PATH OF: ", r)
         print(PR)
         SPR = sorted(PR, key = skey)
         print("============ ORDERED PATH OF: ", r)
         print(SPR)
         final = [symbol_args(a)[1] for a in SPR]
         print("============ PATH OF: ", r)
         print(final)


#end.

#program checking.

loc(R, L, 0):- at(R, L, 0), not index(0).
loc(R, L, 0):- path(R, L, 0, 0), index(0).

total_index(I, M) :- index(I), M = #max {T : path(_, _, T, I)}.



