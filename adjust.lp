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

INDEX = [] 
INIT = [] 
 
def __on_index(m):
    print "\n=== Extracting atoms from indexing program"
    print m
    
    for i in m.atoms():
        if i.name() == "one_at_abstract":
            INDEX.append(i) 
                     
    print INDEX
    print "\n"

def __on_init(m):
    print "\n=== Extracting atoms from adjusting "
    print m
    iINIT = []
    
    for i in m.atoms():
        if i.name() == "begin":
            iINIT.append(i) 
        if i.name() == "end":
            iINIT.append(i) 
    
    INIT.append(iINIT)                  
    print INIT
    print "\n"    
    
def adjust_idx(prg, file, idx, first):
    print "Process index ", idx 
    prg.ground([("adjusting", [idx])])
    prg.assign_external(gringo.Fun("index", [idx]), True) 
    prg.assign_external(gringo.Fun("first", []), first) 

    ret = prg.solve(on_model = __on_init) 

    file.write("__init."+str(idx)+"\n") 

    f = open("__init."+str(idx) , "wb")
    
    f.write("index("+str(idx) + ").\n")

    for v in INIT[-1]: 
         f.write(v.name()+"("+str(v.args()[0])+"," + str(v.args()[1]) +").\n")
 
    f.close()
         
    print "==== end file "

    prg.assign_external(gringo.Fun("first", []), False) 
    prg.assign_external(gringo.Fun("index", [idx]), False)    
    print "Done process index ", idx 
    

def main(prg):
     
    prg.ground([("base", [])])
    prg.ground([("indexing", [])]) 
    ret = prg.solve(on_model = __on_index) 
    isfirst   = prg.get_const("first") 

    indexes = set(map(lambda y: y.args()[0], INDEX)) 
    
    print "====================================="
    print "Indices needed to adjest: ",  indexes
    print "====================================="
    
    f = open("__list_init" , "wb")
    
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



