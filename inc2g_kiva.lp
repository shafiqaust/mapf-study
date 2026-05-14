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
GOAL_KIVA = []
STORE = []
DEPOT = []
LOCATIONS = [] 
VERTICES = [] 
EDGES = [] 
GRAPH = {}
SPATH = []
SPATH_INIT = []
ACTIONS = [] 

def __on_model(m):
    print "\n=== Extracting atoms from ordering program"
    # print m
    for i in m.atoms():
        if i.name() == "order":
            ORDER.append(i)
        elif i.name() == "at":    
            START.append(i)
        elif i.name() == "store":    
            STORE.append(i)
        elif i.name() == "depot":
            DEPOT.append(i)
        elif i.name() == "goal":
            GOAL.append(i)
        elif i.name() == "goal_kiva":
            GOAL_KIVA.append(i)
        elif i.name() == "vertice":
            VERTICES.append(i.args()[0])
            GRAPH[i.args()[0]] = []
        elif i.name() == "edge":
            EDGES.append(i.args())
        # else:
            # print i
            
    for e in EDGES:
        GRAPH[e[0]].append(e[1])
         
    # print ORDER
    # print "\n"
    # print START
    # print "\n"
    # print GOAL
    # print "\n"
    # print VERTICES 
    # print "\n"
    # print EDGES
    # print "\n"
    # print STORE
    # print "\n"
    # print DEPOT
    # print "\n"

def dijkstra(source):
    # print 'source ', source
    def minimum_distance(dist, Q):
        candidate = None
        min_dist = float("inf")
        for n in Q:
            if dist[n] < min_dist:
                min_dist = dist[n]
                candidate = n
        return candidate

    def get_neighbours(u):
        return GRAPH[u]
    
    def dist_between(u, v):
        return 1
    
    dist = dict()
    previous = dict()

    for vertex in VERTICES:
        dist[vertex] = float("inf")
        previous[vertex] = None

    dist[source] = 0
    Q = set(VERTICES)
    
    # print "Vertices ", Q 

    while len(Q) > 0:
        u = minimum_distance(dist, Q)
        # print('Currently considering', u, 'with a distance of', dist[u])
        Q.remove(u)

        if dist[u] == float('inf'):
            break

        n = get_neighbours(u)
        for vertex in n:
            alt = dist[u] + dist_between(u, vertex)
            if alt < dist[vertex]:
                dist[vertex] = alt
                previous[vertex] = u

    return previous, dist

def build_graph():
    def backtrack(robot, previous, node, container):
        if node is not None:
            backtrack(robot, previous, previous[node], container)
            if previous[node] is not None: 
                print previous[node] 
                container.append([robot, previous[node], node])
                
    def sequentialize(objectives):
        seq = []
        order_seq = sorted(objectives.keys())
        for o in order_seq:
            seq = seq + objectives[o]
        return seq
        
    robots_config = {}
    
    for s in START:
        robots_config[s.args()[0]] = {}
        robots_config[s.args()[0]]['start'] = s.args()[1]
        robots_config[s.args()[0]]['objectives'] = {}
        
    for g in GOAL_KIVA: 
        # AGENT, ID, GOAL, S, D, O
        robot = g.args()[0]
        goal  = g.args()[2]
        store = g.args()[3]
        depot = g.args()[4]
        order = g.args()[5]
        if order in robots_config[robot]['objectives']:
            robots_config[robot]['objectives'][order].extend([goal, store, depot])
        else:
            robots_config[robot]['objectives'][order] = []
            robots_config[robot]['objectives'][order].extend([goal, store, depot])
            
    print robots_config    
        
    for k, v in robots_config.iteritems():
        print '=== robot', k
        seq = sequentialize(v['objectives'])
        print '=== runs sequence:', seq
        
        source = v['start']
        for i, goal in enumerate(seq):
            previous, dist = dijkstra(source)
            print("=== it is in {}".format(source))
            print("=== shortest path to {} has length {}".format(goal, dist[goal]))
            print("=== by going through")
            if i == 0:
                global SPATH_INIT
                backtrack(k, previous, goal, SPATH_INIT)
            else:
                global SPATH
                backtrack(k, previous, goal, SPATH)
                
            source = goal
        
        
        print('\n')
    return 
    
def _move_stay(m): 
    print "\n=== Extracting moves and stays from  program"
    # print m
    for i in m.atoms():
        if i.name() == "at":
            LOCATIONS.append(i) 
        elif i.name() == "move" or i.name() == "stay" or i.name() == "visited":
            ACTIONS.append(i) 

    # print LOCATIONS
    # print "\n" 
    
def get(val, default):
    return val if val != None else default

def optimal(ms, mapf, agentf):
    lower = 1
    upper = ms
    ret = gringo.SolveResult.UNKNOWN
    print "=== Finding optimal solution"

    if not os.path.exists("trash"):
        os.makedirs("trash")
    
    while lower < upper - 1:   # use < instead of <=
        x = lower + (upper - lower) // 2

        fpath = os.path.join("trash", str(x))
        f = open(fpath, "w+")
        
        print "=== Try step = {}".format(x)
        call(["clingo", "know_makespan.lp", str(mapf) + ".map", str(agentf) + ".agents", "-c", "n=" + str(x)], stdout=f)
        
        f.seek(0,0)
        result = f.read()
        if "UNSATISFIABLE" in result:
            ret = gringo.SolveResult.UNSAT
        elif "SATISFIABLE" in result:
            ret = gringo.SolveResult.SAT
        elif "UNKNOWN" in result: 
            ret = gringo.SolveResult.UNKNOWN
        f.close()
            
        if ret == gringo.SolveResult.SAT:
            upper = x
        elif ret == gringo.SolveResult.UNSAT:
            lower = x
        elif ret == gringo.SolveResult.UNKNOWN:
            print "=== Something is wrong here"
            break
     
    if ret == gringo.SolveResult.SAT:
        print "=== Optimal: {}".format(x)
    else:
        print "=== Optimal: {}".format(upper)
    
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
    
    build_graph() 
    
    # print SPATH_INIT 
    
    for p in SPATH_INIT:
        prg.add("base", [], "next(" + str(p[0]) + "," + str(p[1]) + "," + str(p[2]) + ").")
    
    # print "after add stuffs"

    prg.ground([("base", [])])
         
    ret = gringo.SolveResult.UNKNOWN
        
    idx = 1
        
    robots = set(map(lambda y: y.args()[0], filter(lambda x: x.args()[3] == idx, GOAL)))
                
    print("=== Robots are responsible for running order {}: {}".format(idx, robots))
        
    # print SPATH 
    
    print "==================================" 
        
        # Second, add paths for filtered robots
    for p in SPATH:
            if p[0] in robots:
                # print("=== Add rule: " + "next(" + str(p[0]) + "," + str(p[1]) + "," + str(p[2]) + ").")
                prg.add("base", [], "next(" + str(p[0]) + "," + str(p[1]) + "," + str(p[2]) + ").")
        
    prg.ground([("base", [])])
    
    # print("here **************\n")
    
    prg.solve() 
                        
    while ((imax is None or step < imax) and
               (step == 0   or step < imin or (
                  (istop == "SAT"     and ret != gringo.SolveResult.SAT) or
                  (istop == "UNSAT"   and ret != gringo.SolveResult.UNSAT) or
                  (istop == "UNKNOWN" and ret != gringo.SolveResult.UNKNOWN)))):

            # print "=== Add cumulative rules to program"
            # print "=== Set cumulative(" + str(step)  + ")"
           
            prg.ground([("cumulative", [step])])
            
            # print "=== Set external query(" + str(step) +  ") to be true "
            prg.assign_external(gringo.Fun("query", [step]), True)
            
            ret = prg.solve(on_model = _move_stay)
            # print "=== Release external query(" + str(step) + ")   "
            prg.release_external(gringo.Fun("query", [step]))


            if ret == gringo.SolveResult.SAT: 
                 print "=== Found path "+str(idx) 
                 break 
                                                 
            step = step+1
    
    end_time = datetime.datetime.now()
    
    # print "END ************************************************"
    # print LOCATIONS 
    
    locs = filter(lambda x: x.args()[2] == step, LOCATIONS)
    
    # print "*************************************************"   
    # print locs 
    f = open("loc.tmp", "wb")
    
    for x in locs:
             y = "nstart("+str(x.args()[0]) +","+str(x.args()[1]) +")"
             # print "Write ... ", y
             f.write(y + ".\n")
         
    f.close()
     
    print "*************************************************"   
    
    # print ACTIONS 
    
    name = "__tmp.out" 
    
    out = open(name, "wb") 
    for x in ACTIONS: 
         out.write(str(x)+".\n")     
         
    for x in LOCATIONS:
         out.write(str(x)+".\n")     
         
    out.close() 
          
    elapsed = end_time - start_time 
     
    print " *** Result:   length = ", step, " time = ", elapsed    
        
#end.

#const istop  = "SAT".
#const imin   = 1.
#const imax   = 100.
#const mapf   = "".
#const agentf = "".

#show at/3.
#show goal/4.
#show accomplished/5.
#show order/2.
#show query/1. 
#show move/3.
#show stay/3.
#show vertice/1.
#show edge/2. 
#show activate/1.
#show next/3.
#show possible/4.
#show strong_possible/4.
#show strong_move_count/3.
#show may_conflict/2.
#show store/2.
#show depot/2.
#show goal_kiva/6.
#show njobs/2.
#show visited/4.
#show replaced_by/2.
#show connected_to/2.

#program ordering.
 
%% count total of groups 

job(1..C) :-  C = #count {ID: group(ID, _) }.

%% the culprit was this group of rules 
%% it was missing the first four rules 
%% from simplify.lp to simplify2.lp, I used _3 to indicate different groups of nodes 
%% and the rule was not modified accordingly - it causes some of the goals disappeared 
%% and so the result was wrong  

connected_to(X, Y):- is_connected(X,Y).
connected_to(X, Y):- is_connected_3(X,Y).

representative_group(X) :- egroup(X). 
representative_group(X) :- egroup_3(X). 

replaced_by(X, X):- vertice(X). 
replaced_by(X, Y):- representative_group(Y), connected_to(X,Y), not vertice(X). 
 
goal_kiva(AGENT, ID, S, GOAL, D, O) :- goal(AGENT, ID, GOAL1, O), store(ID, S1), depot(ID, D1), 
                                                                 replaced_by(GOAL1, GOAL), 
                                                                 replaced_by(S1, S), 
                                                                 replaced_by(D1, D).
  
   
  
%% all agents have to be assigned if it is possible  

%:- agent(R, _, T), agent(R1, _, T), {goal(R, _, _,_)} 0, 2{goal(R1, _, _,_)}, R!=R1.
 
step(0).

at(X,  L, 0) :- agent(X, L, _), vertice(L), not new_start(X).

at(X,  L1, 0) :- is_connected(L, L1), agent(X, L, _), not vertice(L), not new_start(X).
 
new_start(X) :- nstart(X, L).
at(X,  L, 0) :- nstart(X, L).

njobs(GID, N) :- group(GID,_), N = #count {ID : task(ID, GID, _, _)}.

%==============================================================================
% Capture knowledge when increasing t
#program cumulative(t). 
 
step(t).

%% move to the next vertice (written with one parameter fewer than usual) 
%% will work in this case 

at(Y, L1, t) :- at(Y, L, t-1), move(Y, L1, t-1), edge(L, L1).
at(Y, L, t)  :- at(Y, L, t-1), stay(Y, L, t-1).

%% action generation 

%{move(Y,L1,t-1): edge(L,L1); stay(Y, L, t-1)} 1 :- agent(Y, _, _), at(Y, L,t-1).
%
%move(R, N, t-1) :- agent(R, _, _), at(R, L, t-1), active(R), next(R, L, N), not conflict(R, t-1).
%
%conflict(R,t-1):- agent(R, _, _), agent(R1,_,_), R!=R1, at(R, L, t-1), active(R), next(R, L, N), at(R1, N, t-1). 


1 { move(R, N, t-1):edge(L,N); stay(R, L, t-1) } 1 :- agent(R, _, _), at(R, L, t-1),  not goal(R, _, _, _).


% stay(R, L, t-1)   :- agent(R, _, _), at(R, L, t-1), not active(R).


1 { 
stay(R, L, t-1); 
move(R, N, t-1): possible(R, L, N, t-1), strong_move_count(R, X, t-1), X == 0;
move(R, N, t-1): possible(R, L, N, t-1), may_conflict(R, t-1);
move(R, N, t-1): strong_possible(R, L, N, t-1)
} 1 :- at(R, L, t-1), goal(R, _, _, _).

strong_move_count(R, X, t-1):- X = #count {N: strong_possible(R, L, N, t-1)}, at(R, L, t-1), goal(R, _, _, _).

2 {may_conflict(R1, t-1); may_conflict(R, t-1)} :- strong_possible(R, L, N, t-1), at(R1, N, t-1), R != R1.

%% Choose an agent and give it a lead
1 {strong_possible(R, L, N, t-1): next(R, L, N), at(R, L, t-1)} 1:- vertice(N), #count { A,P: next(A, P, N), at(A, P, t-1)} > 1.   

strong_possible(R, L, N, t-1) :- next(R, L, N), at(R, L, t-1), #count { A: next(A, P, N), at(A, P, t-1)} = 1.

possible(R, N, B, t-1) :- next(R, L, N), at(R, N, t-1), edge(N, B).
possible(R, L, B, t-1):- next(R, L, N), at(R, L, t-1), edge(L, B).
possible(R, B, L, t-1):- next(R, L, N), at(R, B, t-1), edge(B, L).
possible(R, B, N, t-1):- next(R, L, N), at(R, B, t-1), edge(B, N).

%% no same location 

:- at( R, L, t), at(R1, L, t), R!=R1, t > 0.

%% no exchange places 

:- at( R, L, t), at(R1, L1, t), R!=R1, edge(L,L1), at( R, L1, t-1), at(R1, L, t-1). 

%done(O, t) :- order(GID, O), njobs(GID, N),  
%         #count{ID : accomplished(R, ID, _, 3,  t), goal(R, ID, _, O)} == N. 
  
2 {visited(R, S1 ,S, t);   
accomplished(R, TID, G, 1, t) } :-  at( R, S, t), store(TID, S1), 
                         goal_kiva(R, TID, S, G, D, 1),
                         not accomplished(R, TID, G, 1, t-1).

2 {visited(R, G1 ,G, t); 
accomplished(R, TID, G, 2, t)}   :-  at( R, G, t),  task(TID, _, G1, _), 
                         goal_kiva(R, TID, S, G, D, 1),
                         accomplished(R, TID,  G, 1, t-1), 
                         not accomplished(R, TID,  G, 2, t-1).

2 {visited(R, D1 ,D, t); 
accomplished(R, TID, G, 3, t)}   :-  at( R, D, t),  depot(TID, D1),                                                         
                         goal_kiva(R, TID, S, G, D, 1),
                         accomplished(R, TID,  G, 2, t-1), 
                         not accomplished(R, TID,  G, 3, t-1).

accomplished(R, TID, G, K, t) :-  accomplished(R, TID, G, K, t-1).

%accomplished(R, TID, G, 1, t)  :-  at( R, G, t), 
%                         goal_kiva(R, TID, G, S, D, Order),
%                         Order > 1, 
%                         done(Order-1, t),                       
%                         not accomplished(R, TID, G, 1, t-1).
%
%accomplished(R, TID, G, 2, t)  :-  at( R, S, t),
%                         goal_kiva(R, TID, G, S, D, Order), 
%                         Order > 1, 
%                         done(Order-1, t),                       
%                         accomplished(R, TID,  G, 1, t-1).
%
%accomplished(R, TID, G, 3, t)  :-  at( R, D, t), 
%                         goal_kiva(R, TID, G, S, D, Order),
%                         Order > 1, 
%                         done(Order-1, t),                       
%                         accomplished(R, TID,  G, 2, t-1).
%

                          
%==============================================================================
% Volatile part. Change goal when increasing t
%==============================================================================
 
% Volatile part. Change goal when increasing t
#external query(t).

% Goal checking
:- not accomplished(R, TID, Y, 3, t), goal_kiva(R, TID, _, Y, _ , 1), query(t). 

%==============================================================================
#program goal_def. 
#external activate(I) : job(I).
 
 
 
%next(1,51,39) next(1,39,38) next(1,38,37) next(1,37,25) next(1,25,13) next(1,13,1) 
%next(2,52,40) next(2,40,39) next(2,39,38) next(2,38,37) next(2,37,25) next(2,25,13) next(2,13,1) next(2,1,0) 
%next(1,1,2) next(1,2,3) next(1,3,4) next(1,4,5) next(1,5,17) next(1,17,5) next(1,5,4) next(1,4,16) next(2,0,1) next(2,1,2) next(2,2,3) next(2,3,4) next(2,4,5) next(2,5,6) next(2,6,18) next(2,18,30) next(2,30,42) next(2,42,43) next(2,43,44) next(2,44,45) next(2,45,46) next(2,46,58) next(2,58,46) next(2,46,45) next(2,45,44) next(2,44,43) next(2,43,42) next(2,42,30) next(2,30,18) next(2,18,6) next(2,6,5) next(2,5,4) next(2,4,3) next(2,3,2) next(2,2,14)

