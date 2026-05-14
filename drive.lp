#script (python) 

###########
# Usage:
#clingo g-v2-graph.lp test_1.map test_1_1.agents -c mapf="test_1" -c agentf="test_1_1"
###########

import gringo
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
    print "\n=== Extracting atoms from ordering program"
    print m
    for i in m.atoms():
        if i.name() == "order":
            ORDER.append(i)
        elif i.name() == "at":    
            START.append(i)
        elif i.name() == "goal":
            GOAL.append(i)
        elif i.name() == "agent":
            AGENT.append(i)
        elif i.name() == "group":
            GROUP.append(i)
        elif i.name() == "store":
            STORE.append(i)
        elif i.name() == "depot":
            DEPOT.append(i)
        elif i.name() == "task":
            TASK.append(i)
          
    print ORDER
    print "\n"
    print START
    print "\n"
    print GOAL
    print "\n"

def get(val, default):
    return val if val != None else default

def main(prg):
    mapf = prg.get_const("mapf")
    agentf = prg.get_const("agentf")
    
    picked_group = 0
    
    start_time = datetime.datetime.now()

    imin   = get(prg.get_const("imin"), 1)
    imax   = prg.get_const("imax")
    istop  = get(prg.get_const("istop"), "SAT")
    
    step   = 0

    prg.ground([("base", [])])
    prg.ground([("ordering", [])]) 
    ret = prg.solve(on_model = __on_model) 
             
    o = open("outs.txt", "wb") 
      
    for idx in range(1, len(ORDER)+1): 
         order = filter(lambda x: x.args()[1] == idx, ORDER)  
         goals = filter(lambda x: x.args()[3] == idx, GOAL)
         tasksset =  set(map(lambda y: y.args()[1], goals)) 
         tasks = filter(lambda x: x.args()[0] in tasksset, TASK)         
         stores = filter(lambda x: x.args()[0] in tasksset, STORE)      
         depots = filter(lambda x: x.args()[0] in tasksset, DEPOT)
         groups = filter(lambda x: x.args()[0] == order[0].args()[0] , GROUP)
         print order
         print groups 
         print goals 
         print tasksset
         print tasks
         print "==== create file "

         o.write("f" + str(idx) + ".agents\n")
          
         f = open("f" + str(idx) + ".agents", "wb")          
         for a in AGENT:
             f.write(str(a) + ".\n")
         for x in order :
             y = "order("+str(x.args()[0]) +",1)"
             f.write(y + ".\n")
         for x in groups: 
             f.write(str(x) + ".\n")
         for x in goals :
             y = "goal("+str(x.args()[0]) +","+str(x.args()[1]) +","+ str(x.args()[2]) +",1)"
             f.write(y + ".\n")
             f.write("active("+str(x.args()[0]) +").\n")
         for x in stores: 
             f.write(str(x) + ".\n")
         for x in depots:
             f.write(str(x) + ".\n")
         for x in tasks :
             f.write(str(x) + ".\n")
         
         f.close()
         
         print "==== end file "

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

 
