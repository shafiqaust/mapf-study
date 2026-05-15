#script (python)

###########
# Usage:
#clingo g-v2-graph.lp test_1.map test_1_1.agents -c mapf="test_1" -c agentf="test_1_1"
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

ORDER = []
START = []
GOAL  = []
STORE = []
DEPOT = []
AGENT = []
GROUP = []
TASK = []

def __on_model(m):
    print("\n=== Extracting atoms from ordering program")
    print(m)
    for i in shown_symbols(m):
        if symbol_name(i) == "order":
            ORDER.append(i)
        elif symbol_name(i) == "at":
            START.append(i)
        elif symbol_name(i) == "goal":
            GOAL.append(i)
        elif symbol_name(i) == "agent":
            AGENT.append(i)
        elif symbol_name(i) == "group":
            GROUP.append(i)
        elif symbol_name(i) == "store":
            STORE.append(i)
        elif symbol_name(i) == "depot":
            DEPOT.append(i)
        elif symbol_name(i) == "task":
            TASK.append(i)

    print(ORDER)
    print("\n")
    print(START)
    print("\n")
    print(GOAL)
    print("\n")

def get(val, default):
    return val if val != None else default

def main(prg):
    mapf = const_value(prg, "mapf")
    agentf = const_value(prg, "agentf")

    picked_group = 0

    start_time = datetime.datetime.now()

    imin   = get(const_value(prg, "imin"), 1)
    imax   = const_value(prg, "imax")
    istop  = get(const_value(prg, "istop"), "SAT")

    step   = 0

    ground(prg, [("base", [])])
    ground(prg, [("ordering", [])])
    ret = solve(prg, on_model=__on_model)

    o = open("outs.txt", "w")

    for idx in range(1, len(ORDER)+1):
         order = [x for x in ORDER if symbol_args(x)[1] == idx]
         goals = [x for x in GOAL if symbol_args(x)[3] == idx]
         tasksset =  set([symbol_args(y)[1] for y in goals])
         tasks = [x for x in TASK if symbol_args(x)[0] in tasksset]
         stores = [x for x in STORE if symbol_args(x)[0] in tasksset]
         depots = [x for x in DEPOT if symbol_args(x)[0] in tasksset]
         groups = [x for x in GROUP if symbol_args(x)[0] == symbol_args(order[0])[0]]
         print(order)
         print(groups)
         print(goals)
         print(tasksset)
         print(tasks)
         print("==== create file ")

         o.write("f" + str(idx) + ".agents\n")

         f = open("f" + str(idx) + ".agents", "w")
         for a in AGENT:
             f.write(str(a) + ".\n")
         for x in order :
             y = "order("+str(symbol_args(x)[0]) +",1)"
             f.write(y + ".\n")
         for x in groups:
             f.write(str(x) + ".\n")
         for x in goals :
             y = "goal("+str(symbol_args(x)[0]) +","+str(symbol_args(x)[1]) +","+ str(symbol_args(x)[2]) +",1)"
             f.write(y + ".\n")
             f.write("active("+str(symbol_args(x)[0]) +").\n")
         for x in stores:
             f.write(str(x) + ".\n")
         for x in depots:
             f.write(str(x) + ".\n")
         for x in tasks :
             f.write(str(x) + ".\n")

         f.close()

         print("==== end file ")

    o.close()

#end.

#const istop  = "SAT".
#const imin   = 1.
#const imax   = 60.
#const mapf   = "".
#const agentf = "".

#program ordering.

%% count total of groups

job(1..C) :-  C = #count {ID: group(ID, _) }.

%% ordering of the groups

1 {order(ID, O) :  job(O)} 1 :- group(ID, _).

:- order(ID, O), order(ID1, O), ID!=ID1.

%% assign agents to targets

1 {goal(AGENT, ID, GOAL, O) : agent(AGENT, _, TYPE) } 1 :-
        task(ID, GROUP, GOAL, TYPE), order(GROUP, O).

%% all agents have to be assigned if it is possible

% :- agent(R, _, T), agent(R1, _, T), {goal(R, _, _,_)} 0, 2{goal(R1, _, _,_)}, R!=R1.

ntask(R, ID, T, N) :- group(ID, _), order(ID, O), agent(R, _, T), N = #count {TID1: goal(R, TID1, _,O) }.

:- group(ID, _), agent(R, _, T), agent(R1, _, T),   R!=R1,  ntask(R, ID, T, 0), ntask(R1, ID, T, N), N > 1 .

at(X,  L, 0) :- agent(X, L, _).

njobs(GID, N) :- group(GID,_), N = #count {ID : task(ID, GID, _, _)}.


