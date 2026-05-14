p_vertice(X) :- vertice(X), pods(Y), edge(X, Y).  

vertice_3(X) :- vertice(X), #count {Y : edge(Y, X)} == 3, p_vertice(X).   

same_group(X, Y):- vertice_3(X), vertice_3(Y), edge(X, Y). 
same_group(X, Y):- vertice_3(X), vertice_3(Y), X!=Y,  same_group(X,Z), edge(Z, Y). 
 
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
