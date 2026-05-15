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

EDGES = []
VERTICES = []
PODS  = []
EGROUPS = []
ECONNECTED = []
PODS  = []

def __on_model(m):
    print("\n=== Extracting atoms from ordering program")
    print(m)
    eEDGES = []
    eVERTICES = []
    ePODS  = []
    eEGROUPS = []
    eECONNECTED = []

    for i in shown_symbols(m):
        if symbol_name(i) == "nedge":
            eEDGES.append(i)
        elif symbol_name(i) == "nvertice":
            eVERTICES.append(i)
        elif symbol_name(i) == "pods":
            ePODS.append(i)
        elif symbol_name(i) == "egroup":
            eEGROUPS.append(i)
        elif symbol_name(i) == "pods":
            ePODS.append(i)
        elif symbol_name(i) == "is_connected":
            eECONNECTED.append(i)

    EDGES.append(eEDGES)
    VERTICES.append(eVERTICES)
    PODS.append(ePODS)
    EGROUPS.append(eEGROUPS)
    ECONNECTED.append(eECONNECTED)

    print(EDGES)
    print("\n")
    print(VERTICES)
    print("\n")
    print(PODS)
    print("\n")

def get(val, default):
    return val if val != None else default

def main(prg):

    ground(prg, [("base", [])])
    ground(prg, [("simplifying", [])])
    ret = solve(prg, on_model=__on_model)

    print("==== create file ")
    f = open("__tmp.map" , "w")

    for v in VERTICES[-1]:
        f.write("vertice("+str(symbol_args(v)[0]) +").\n")

    for e in EDGES[-1]:
        f.write("edge("+str(symbol_args(e)[0]) +","  +str(symbol_args(e)[1]) +  ").\n")

    for p in PODS[-1]:
        f.write(str(p) + ".\n")

    for e in ECONNECTED[-1]:
        f.write(str(e) + ".\n")

    for v in EGROUPS[-1]:
        f.write(str(v) + ".\n")

    f.close()

    print("==== end file ")

#end.

#const istop  = "SAT".
#const imin   = 1.
#const imax   = 60.
#const mapf   = "".
#const agentf = "".

#show nvertice/1.
#show nedge/2.
#show is_connected/2.
#show egroup/1.
#show pods/1.
#show vertice_3/1.

#program simplifying.

%%% only simplify the set of nodes that are connected to pods and are closed to each other

p_vertice(X) :- vertice(X), pods(Y), edge(X, Y).

vertice_3(X) :- vertice(X), #count {Y : edge(Y, X)} == 3, p_vertice(X).

%%% creating groups
%%% each group is a collection of nodes that are connected to pods in the same row

same_group(X, Y):- vertice_3(X), vertice_3(Y), edge(X, Y).
same_group(X, Y):- vertice_3(X), vertice_3(Y), X!=Y,  same_group(X,Z), edge(Z, Y).

%%% select a node in this one as a

{egroup(Z)} 1 :- p_vertice(Z).

is_connected(Z, Z):- egroup(Z).
is_connected(Z, ZG):- is_connected(Z1, ZG), p_vertice(Z), edge(Z, Z1).
is_connected(Z, ZG):- is_connected(Z1, ZG), vertice_3(Z), edge(Z, Z1).

:- p_vertice(Z), not is_connected(Z, _).

nvertice(V) :- vertice(V), not p_vertice(V).

nvertice(V) :- vertice(V), egroup(V).

nedge(X, Y):- edge(X,Y), not p_vertice(X), not p_vertice(Y).

nedge(X, Z):- edge(X,Y), not p_vertice(X), p_vertice(Y),  egroup(Z), is_connected(Y, Z).

nedge(X, Y):- nedge(Y,X).

:- egroup(Z), egroup(X), same_group(X, Z).


%
%vertice_3(X) :- vertice(X), #count {Y : edge(Y, X)} == 3, p_vertice(X).
%
%same_group(X, Y):- vertice_3(X), vertice_3(Y), edge(X, Y).
%same_group(X, Y):- vertice_3(X), vertice_3(Y), X!=Y,  same_group(X,Z), edge(Z, Y).
%
%p_vertice(X) :- vertice(X), pods(Y), edge(X, Y).
%
%{egroup(Z)} 1 :- p_vertice(Z).
%{egroup(Z)} 1 :- vertice_3(Z).
%
%%:- egroup(Z), depot(_, Z).
%%:- egroup(Z), store(_, Z).
%%:- egroup(Z), task(_,_, Z,_).
%
%same_group(X, Y):- p_vertice(X), p_vertice(Y), edge(X, Y).
%same_group(X, Y):- p_vertice(X), p_vertice(Y), X!=Y,  same_group(X,Z), edge(Z, Y).
%
%
%is_connected(Z, Z):- egroup(Z).
%is_connected(Z, ZG):- is_connected(Z1, ZG), p_vertice(Z), edge(Z, Z1).
%is_connected(Z, ZG):- is_connected(Z1, ZG), vertice_3(Z), edge(Z, Z1).
%
%:- p_vertice(Z), not is_connected(Z, _).
%
%nvertice(V) :- vertice(V), not p_vertice(V).
%
%nvertice(V) :- vertice(V), egroup(V).
%
%nedge(X, Y):- edge(X,Y), not p_vertice(X), not p_vertice(Y).
%
%nedge(X, Z):- edge(X,Y), not p_vertice(X), p_vertice(Y),  egroup(Z), is_connected(Y, Z).
%
%nedge(X, Y):- nedge(Y,X).
%
%:- egroup(Z), egroup(X), same_group(X, Z).
%
% #minimize {1,Z : egroup(Z)}.


