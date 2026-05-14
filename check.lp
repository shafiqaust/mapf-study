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
ATS = []  
INDEX = [] 
ROBOTS = [] 

 
def __on_check(m):
    print "\n=== Extracting atoms for checking "
    print m
    
    for i in m.atoms():
        if i.name() == "path":
            PATHS.append(i) 
        if i.name() == "at":
            ATS.append(i)  
        if i.name() == "index":
            INDEX.append(i)  
 
 
def skey(item):
    if item.name() == "at":
         return (item.args()[2], 0) 
    if item.name() == "path":
         return (item.args()[3], item.args()[2]) 

 
def main(prg):
     
    prg.ground([("base", [])])
    prg.ground([("checking", [])]) 
    ret = prg.solve(on_model = __on_check) 

                     
    print PATHS
    print ATS
    print INDEX
    
    print "\n"    
    
    INDICES = set([i.args()[0] for i in INDEX])
    
    ROBOTS = set ([i.args()[0] for i in PATHS]) 
    
    print  "============ ROBOTS: ", ROBOTS
    
    for r in ROBOTS:
         PR1 = [p for p in PATHS if r==p.args()[0]] 
         PR2 = [a for a in ATS if r==a.args()[0] and  a.args()[2] not in INDICES] 
         print PR1
         print PR2 
         PR = PR1 + PR2
         print "============ PATH OF: ", r
         print PR
         SPR = sorted(PR, key = skey) 
         print "============ ORDERED PATH OF: ", r
         print SPR
         final = [a.args()[1] for a in SPR] 
         print "============ PATH OF: ", r
         print final
          
                
#end.
 
#program checking.

loc(R, L, 0):- at(R, L, 0), not index(0).
loc(R, L, 0):- path(R, L, 0, 0), index(0). 

total_index(I, M) :- index(I), M = #max {T : path(_, _, T, I)}. 

 

