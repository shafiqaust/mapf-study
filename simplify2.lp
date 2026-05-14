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

EDGES = []
VERTICES = []
PODS  = []
EGROUPS = [] 
ECONNECTED = []
PODS  = []
 
def __on_model(m):
    print "\n=== Extracting atoms from ordering program"
    print m
    eEDGES = []
    eVERTICES = []
    ePODS  = []
    eEGROUPS = [] 
    eECONNECTED = []

    for i in m.atoms():
        if i.name() == "nedge":
            eEDGES.append(i)
        elif i.name() == "nvertice":    
            eVERTICES.append(i)
        elif i.name() == "pods":
            ePODS.append(i) 
        elif i.name() == "egroup" or i.name() == "egroup_3":
            eEGROUPS.append(i) 
        elif i.name() == "pods":
            ePODS.append(i) 
        elif i.name() == "is_connected" or i.name() == "is_connected_3":
            eECONNECTED.append(i) 
          
    EDGES.append(eEDGES)
    VERTICES.append(eVERTICES) 
    PODS.append(ePODS) 
    EGROUPS.append(eEGROUPS) 
    ECONNECTED.append(eECONNECTED)
           
    print EDGES
    print "\n"
    print VERTICES
    print "\n"
    print PODS
    print "\n"

def get(val, default):
    return val if val != None else default

def main(prg):
     
    prg.ground([("base", [])])
    prg.ground([("simplifying", [])]) 
    ret = prg.solve(on_model = __on_model) 
        
    print "==== create file "
    f = open("__tmp.map" , "wb")

    for v in VERTICES[-1]: 
        f.write("vertice("+str(v.args()[0]) +").\n")

    for e in EDGES[-1]: 
        f.write("edge("+str(e.args()[0]) +","  +str(e.args()[1]) +  ").\n")

    for p in PODS[-1]: 
        f.write(str(p) + ".\n")

    for e in ECONNECTED[-1]: 
        f.write(str(e) + ".\n")

    for v in EGROUPS[-1]: 
        f.write(str(v) + ".\n")

    f.close()
         
    print "==== end file "
               
#end.

#const istop  = "SAT".
#const imin   = 1.
#const imax   = 60.
#const mapf   = "".
#const agentf = "".

#show nvertice/1. 
#show nedge/2. 
#show is_connected/2.
#show is_connected_3/2.
#show egroup/1.
#show egroup_3/1.
#show pods/1. 
#show vertice_3/1.
#show p_vertice/1. 
 
#program simplifying.
 
p_vertice(X) :- vertice(X), pods(Y), edge(X, Y).  

vertice_3(X) :- vertice(X), #count {Y : edge(Y, X), not pods(Y)} == 3, has_neighbor_3(X).   

has_neighbor_3(Y):- edge(Y,X), #count {Z : edge(Z,X), not pods(Z)} == 3.

same_group_3(X, Y):- vertice_3(X), vertice_3(Y), edge(X, Y). 
same_group_3(X, Y):- vertice_3(X), vertice_3(Y), X!=Y,  same_group_3(X,Z), edge(Z, Y). 
 
p_vertice(X) :- vertice(X), pods(Y), edge(X, Y).  

{egroup(Z)} 1 :- p_vertice(Z).
{egroup_3(Z)} 1 :- vertice_3(Z). 

%:- egroup(Z), depot(_, Z). 
%:- egroup(Z), store(_, Z). 
%:- egroup(Z), task(_,_, Z,_). 

same_group(X, Y):- p_vertice(X), p_vertice(Y), edge(X, Y). 
same_group(X, Y):- p_vertice(X), p_vertice(Y), X!=Y,  same_group(X,Z), edge(Z, Y). 


is_connected_3(Z, Z):- egroup_3(Z).
is_connected_3(Z, ZG):- is_connected_3(Z1, ZG), vertice_3(Z), edge(Z, Z1). 

is_connected(Z, Z):- egroup(Z).
is_connected(Z, ZG):- is_connected(Z1, ZG), p_vertice(Z), edge(Z, Z1). 

:- p_vertice(Z), not is_connected(Z, _). 
:- vertice_3(Z), not is_connected_3(Z, _). 

nvertice(V) :- vertice(V), not p_vertice(V), not vertice_3(V). 

nvertice(V) :- vertice(V), egroup(V). 
nvertice(V) :- vertice(V), egroup_3(V). 

special_node(X) :- p_vertice(X). 
special_node(X) :- vertice_3(X).

nedge(X, Y):- edge(X,Y), not special_node(X), not special_node(Y). 

nedge(X, Z):- edge(X,Y), not special_node(X), p_vertice(Y),  egroup(Z), is_connected(Y, Z).

nedge(X, Z):- edge(X,Y), not special_node(X), vertice_3(Y),  egroup_3(Z), is_connected_3(Y, Z).

nedge(Z1, Z):- edge(X,Y), p_vertice(X), egroup(Z1), is_connected(X,Z1), vertice_3(Y),  egroup_3(Z), is_connected_3(Y, Z).

nedge(X, Y):- nedge(Y,X). 