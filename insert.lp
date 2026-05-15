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


def __on_index(m):
    print("\n=== Extracting atoms from insert program")
    print(m)

    for i in shown_symbols(m):
        if symbol_name(i) == "path":
            PATHS.append(i)
        if symbol_name(i) == "index":
            PATHS.append(i)


    print(PATHS)
    print("\n")

def get(val, default):
    return val if val != None else default

def main(prg):

    imin   = get(const_value(prg, "imin"), 1)
    imax   = const_value(prg, "imax")
    istop  = get(const_value(prg, "istop"), "SAT")

    ground(prg, [("base", [])])
    ground(prg, [("insert", [])])

    ret = UNKNOWN

    step   = 0

    while ((imax is None or step < imax) and
               (step == 0   or step < imin or (
                  (istop == "SAT"     and ret != SAT) or
                  (istop == "UNSAT"   and ret != UNSAT) or
                  (istop == "UNKNOWN" and ret != UNKNOWN)))):
            print("=== Add cumulative rules to program for " + str(step))

            ground(prg, [("cumulative", [step])])

            print("=== Set external query(" + str(step) +  ") to be true ")
            prg.assign_external(make_fun("query", [step]), True)

            ret = solve(prg, on_model=__on_index)

            if ret == SAT:
                   print("=== Found path ")
                   break

            print("=== Release external query(" + str(step) + ")   ")
            prg.assign_external(make_fun("query", [step]), False)

            step = step+1

    f = open("__out.result" , "w")

    for v in PATHS:
         f.write(str(v) +".\n")

    f.close()


#end.


#const istop  = "SAT".
#const imin   = 1.
#const imax   = 100.

#show path/4.
#show need_to_move/1.
#show begin/2.
#show end/2.
#show index/1.
#show need_to_visit/2.
#show visited/4.
#show did_visit/3.

#program insert.

need_to_visit(R, RealGoal):- visited(R, RealGoal, AbstractGoal, I), index(I), RealGoal != AbstractGoal.

path(R, L, 0, I) :- begin(R, L), index(I).

need_to_move(R) :- begin(R, L), end(R, L1), not edge(L, L1).

#program cumulative(t).

step(t).

%% move to the next vertice (written with one parameter fewer than usual)
%% will work in this case

path(R, L1, t, I) :- path(R, L, t-1, I), end(R, L1), not need_to_move(R), index(I).

1{path(R, L1, t, I) : edge(L, L1); path(R, L, t, I)} 1:- path(R, L, t-1, I), need_to_move(R), index(I).

:- path(R, L, t, I), path(R1, L, t, I), R != R1, index(I).

:- path(R, L, t, I), path(R1, L1, t, I), R!=R1, path(R1, L, t-1, I), path(R,  L1, t-1, I), edge(L, L1), index(I).

did_visit(R, L, t):- need_to_visit(R, L), path(R, L, t, _).

did_visit(R, L, t):- did_visit(R, L, t-1).

#external query(t).
% Goal checking

:- not path(R, L, t, I), end(R, L), query(t), index(I).
:- not did_visit(R, L, t), need_to_visit(R, L), query(t).
