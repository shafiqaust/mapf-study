#script (python) 

###########
# Usage:
#clingo simplify.lp x.map  
###########

import gringo
import datetime
import re  
from subprocess import call
import sys
import os

PATHS = [] 

 
def __on_index(m):
    print "\n=== Extracting atoms from insert program"
    print m
    
    for i in m.atoms():
        if i.name() == "path":
            PATHS.append(i) 
        if i.name() == "index":
            PATHS.append(i) 
         
                     
    print PATHS
    print "\n"

def get(val, default):
    return val if val != None else default
         
def main(prg):

    imin   = get(prg.get_const("imin"), 1)
    imax   = prg.get_const("imax")
    istop  = get(prg.get_const("istop"), "SAT")
         
    prg.ground([("base", [])])
    prg.ground([("insert", [])])  
                      
    ret = gringo.SolveResult.UNKNOWN
    
    step   = 0
         
    while ((imax is None or step < imax) and
               (step == 0   or step < imin or (
                  (istop == "SAT"     and ret != gringo.SolveResult.SAT) or
                  (istop == "UNSAT"   and ret != gringo.SolveResult.UNSAT) or
                  (istop == "UNKNOWN" and ret != gringo.SolveResult.UNKNOWN)))):
            print "=== Add cumulative rules to program for " + str(step) 
           
            prg.ground([("cumulative", [step])]) 
            
            print "=== Set external query(" + str(step) +  ") to be true "
            prg.assign_external(gringo.Fun("query", [step]), True)

            ret = prg.solve(on_model = __on_index )
            
            if ret == gringo.SolveResult.SAT: 
                   print "=== Found path " 
                   break

            print "=== Release external query(" + str(step) + ")   "
            prg.assign_external(gringo.Fun("query", [step]), False)

            step = step+1

    f = open("__out.result" , "wb")

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
