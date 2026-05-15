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

INDEX = []
INIT = []

def __on_index(m):
    print("\n=== Extracting atoms from indexing program")
    print(m)

    for i in shown_symbols(m):
        if symbol_name(i) == "one_at_abstract":
            INDEX.append(i)

    print(INDEX)
    print("\n")

def __on_init(m):
    print("\n=== Extracting atoms from adjusting ")
    print(m)
    iINIT = []

    for i in shown_symbols(m):
        if symbol_name(i) == "begin":
            iINIT.append(i)
        if symbol_name(i) == "end":
            iINIT.append(i)

    INIT.append(iINIT)
    print(INIT)
    print("\n")

def adjust_idx(prg, file, idx, first):
    print("Process index ", idx)
    ground(prg, [("adjusting", [idx])])
    prg.assign_external(make_fun("index", [idx]), True)
    prg.assign_external(make_fun("first", []), first)

    ret = solve(prg, on_model=__on_init)

    file.write("__init."+str(idx)+"\n")

    f = open("__init."+str(idx) , "w")

    f.write("index("+str(idx) + ").\n")

    for v in INIT[-1]:
         f.write(symbol_name(v)+"("+str(symbol_args(v)[0])+"," + str(symbol_args(v)[1]) +").\n")

    f.close()

    print("==== end file ")

    prg.assign_external(make_fun("first", []), False)
    prg.assign_external(make_fun("index", [idx]), False)
    print("Done process index ", idx)


def main(prg):

    ground(prg, [("base", [])])
    ground(prg, [("indexing", [])])
    ret = solve(prg, on_model=__on_index)
    isfirst   = const_value(prg, "first")

    indexes = set([symbol_args(y)[0] for y in INDEX])

    print("=====================================")
    print("Indices needed to adjest: ",  indexes)
    print("=====================================")

    f = open("__list_init" , "w")

    if isfirst == 1:
         adjust_idx(prg, f, 0, True)

    for idx in indexes:
         if isfirst == 0 or idx > 0:
             adjust_idx(prg, f, idx, False)

    f.close()

#end.

#program indexing.

#show one_at_abstract/1.

%%% this predicate records the positions that need to be adjusted
%%% one_at_abstract(I) means that the index I needs to be reconsidered
%%% since the edge to the next index is not available in the original map

one_at_abstract(I) :- at (R, L1, I), move(R, L, I), I > 0, not edge(L1, L).

#program adjusting(i).
#external index(i).
#external first.

%%% this part of the program records the begin and the end of the
%%% segment that needs to be adjusted
%%% begin(R, L1, i) and end(R, L2, i) mean that it needs to go from L1 to L2

begin(R, L, i) :- i==0, agent(R, L, _), index(i), first.

begin(R, L, i) :- i==0, at(R, L, i), index(i), not first.

begin(R, L, i) :- i>0, at(R, L, i), index(i).

end(R, L, i) :- at(R, L, i+1), index(i).

#show begin/3.
#show end/3.



