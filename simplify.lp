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
        elif i.name() == "egroup":
            eEGROUPS.append(i) 
        elif i.name() == "pods":
            ePODS.append(i) 
        elif i.name() == "is_connected":
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

 