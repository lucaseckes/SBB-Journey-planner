import pandas as pd
import itertools
from collections import defaultdict
from datetime import datetime
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import shortest_path
from datetime import datetime, timedelta
import copy
import sys

important_columns = ['stop_id_s', 'trip_id', 'arrival_time', 'departure_time', 'next_stop_id_s', 'next_trip_id',\
                'next_arrival_time', 'next_departure_time', 'Travel_time', 'stop_name', 'arrival_time_80',\
               'arrival_time_85', 'arrival_time_90', 'arrival_time_95', 'arrival_time_99']

class Graph:
    """ Class representing the transport network as a graph given a schedule. 
    Attributes:
        start_node: the station identifier of the starting point.
        goal_node: the station identifier of the destination.
        edges_list: the existing list of edges between stations.
        end_time: the desired arrival time defined by the user.
    """
    def __init__(self, start_node, goal_node, edges_list, end_time, confidence_proba, walking_table):
        self.start_node = start_node
        self.goal_node = goal_node
        self.end_time = end_time
        self.confidence_proba = confidence_proba
        self.walking_table = walking_table
        self.filter_edges_list = self.filtering(edges_list, end_time)
        self.final_edges_list = self.new_edges(self.filter_edges_list)
        
    def __repr__(self):
        """ SciPy sparse adjacency matrix representation of the graph and a dictionnary where each node has their respective indices in the matrix.
        """
        edges_list = self.filter_edges_list[:]
        length = len(edges_list)
        final_edges_list = self.final_edges_list[:]
        nodes = {}
        for i,edge in enumerate(edges_list):
            nodes[edge[:4]] = i
        
        col = []
        row = []
        data = []
        for edge in final_edges_list:
            if edge[4] is not None:
                try:
                    row.append(nodes[edge[4:8]])
                    col.append(nodes[edge[:4]])
                    data.append(edge[8])
                except KeyError:
                    pass
        
        adj_matrix = csr_matrix((data,(row,col)), shape=(length,length))
        
        return adj_matrix, nodes
    
    def filtering(self, edges_list, end_time):
        """ Filter the nodes where the arrival time is between the end_time and end_time minus 2 hours and drop delays for
        confidence probability not specified by the user.
        Parameters:
            edges_list: the existing list of edges between stations.
            end_time: the desired arrival time defined by the user.
        Return:
            The filtered edge list.
        """
        start_time = datetime.strftime(datetime.strptime(end_time, "%H:%M:%S")-timedelta(hours=2), "%H:%M:%S")
        keep_col = important_columns.index('arrival_time_'+str(self.confidence_proba))
        return [(edges[:9] + (edges[9], edges[keep_col])) for edges in edges_list if (edges[3]<=end_time)&(edges[3]>start_time)]
        
    def new_edges(self, edges_list):
        """ Create edges between nodes of same station and edges between stations that are 10 minutes of walking.
        Parameters: 
            edges_list: the existing list of edges between stations.
        Return:
            The edge list that is used for the graph representation.
        """
        final_edges = []
        d = defaultdict(list)
        for edge in self.filter_edges_list:
            d[edge[0]].append((edge[1:3] + (edge[3], edge[10])))
        
        # Create edges between nodes of same station
        for key, value in d.items():
            
            # Can't wait in the starting station. Need to take the latest possible transport that can arrive at destination.
            if (key!=self.start_node):

                value.sort(key=lambda tup: tup[3])
                comb = itertools.combinations(value, 2)
            
                for pair in comb:
                    if (datetime.strptime(pair[0][1], "%H:%M:%S"))<(datetime.strptime(pair[1][1], "%H:%M:%S")+timedelta(minutes=2)):
                        weight = ((datetime.strptime(pair[1][3], "%H:%M:%S")-datetime.strptime(pair[0][3], "%H:%M:%S")).seconds//60)%60
                        if weight > 2:
                            final_edges.append((key, pair[0][0], pair[0][1], pair[0][2], key, pair[1][0], pair[1][1], pair[1][2], weight, pair[0][3]))
                     
            # The wait at the arrival station is zero. Guarantee that the user can arrive before the end time and that no useless transport are taken. 
            if (key==self.goal_node):
                value.sort(key=lambda tup: tup[3])
                comb = itertools.combinations(value, 2)
            
                for pair in comb:
                    if (pair[0][1]<pair[1][1]):
                        final_edges.append((key, pair[0][0], pair[0][1], pair[0][2], key, pair[1][0], pair[1][1], pair[1][2], 0, pair[0][3]))
            
            # Create edges between nodes that are reachable by walking
            df_searchable = self.walking_table.set_index("stop_id_s")
            walk_edges = df_searchable[df_searchable.index==key]
            
            if not walk_edges.empty:
                for _, row in walk_edges.iterrows():
                    for time in value:
                        if (d.get(row.close_stop_id_s, "test") != "test"):
                            close_time = list(d.get(row.close_stop_id_s))
                            close_time.sort(key=lambda tup: tup[3])
                            possible_time = datetime.strptime(time[3], "%H:%M:%S")+timedelta(minutes=row.time+2)
                        
                            while (close_time) and (datetime.strptime(close_time[0][3], "%H:%M:%S")<possible_time):
                                close_time.pop(0)
                        
                            if close_time:
                                i=0
                                while (i<len(close_time)) and (datetime.strptime(close_time[i][3], "%H:%M:%S")<possible_time+timedelta(minutes=2)):
                                    if (datetime.strptime(time[1], "%H:%M:%S")+timedelta(minutes=row.time+2))<(datetime.strptime(close_time[i][1], "%H:%M:%S")):
                                        weight = ((datetime.strptime(close_time[i][3], "%H:%M:%S")-datetime.strptime(time[3], "%H:%M:%S")).seconds//60)%60 
                                        final_edges.append((key, time[0], time[1], time[2], row.close_stop_id_s, close_time[i][0], close_time[i][1], close_time[i][2], weight, time[3]))
                                    i += 1
            
        return final_edges+self.filter_edges_list
            
    def make_itinary(self):
        """ Make the itinary from the destination. The shotest path algorithm was performed backwards.
        Return: 
             predecessors: The list of predecessors to compute the shortest path.
             stop_idx: the indices in the graph representation for the destination.
             nodes: Dictionnary where each node has their respective indices in the matrix.
        """
        graph, nodes = self.__repr__()
        stop = [edge for edge in self.final_edges_list if edge[4]==self.goal_node]
        stop.sort(key=lambda tup: (tup[9], tup[6]), reverse=True)
        compt = 0
        while stop[compt][7] > self.end_time:
            compt += 1
        stop_idx = nodes[stop[compt][4:8]]

        dist, predecessors = shortest_path(csgraph=graph, indices=stop_idx, directed=True, unweighted=False, return_predecessors=True)
        
        return predecessors, stop_idx, nodes
    
    def show_itinary(self):
        """ DataFrame where each intermediate stations of the itinary are represented as well as their trip id and times.
        """
        df_itinary = pd.DataFrame(columns=['stop_id_s', 'stop_name', 'trip_id', 'arrival_time', 'departure_time'])
        predecessors, stop_idx, nodes = self.make_itinary()

        start = [edge for edge in self.final_edges_list if edge[0]==self.start_node]
        start.sort(key=lambda tup: (tup[3], tup[2]), reverse=True)
        start_idx = nodes[start[0][:4]]
        
        i=0
        while predecessors[start_idx]==-9999:
            i += 1
            try:
                start_idx = nodes[start[i][:4]]
            except IndexError:
                print("Tehere is no path possible less than two hours")
                sys.exit(1)
        
        idx = start_idx
        compt = 0
        while (idx != stop_idx):
            info = self.filter_edges_list[idx]
            df_itinary.loc[compt] = [info[0], info[9], info[1], info[2], info[3]]
            idx = predecessors[idx]
            compt += 1
                
        info = self.filter_edges_list[idx]
        df_itinary.loc[compt] = [info[0], info[9], info[1], info[2], info[3]]
        
        return df_itinary
    
    def clean_itinary(self):
        """ DataFrame representing the itinary with the stations, trip id, the time and the connections changes to be made.
        """
        
        df_clean_itinary = pd.DataFrame(columns=['stop_id_s', 'stop_name', 'trip_id', 'arrival_time', 'departure_time'])
        df_itinary = self.show_itinary()
        
        if (df_itinary.trip_id.loc[0]==df_itinary.trip_id.loc[1]):
            df_clean_itinary.loc[0] = [df_itinary["stop_id_s"].loc[0], df_itinary["stop_name"].loc[0], df_itinary["trip_id"].loc[0], None, df_itinary["departure_time"].loc[0]]
            compt = 1
        else:
            df_clean_itinary.loc[0] = [df_itinary["stop_id_s"].loc[0], df_itinary["stop_name"].loc[0], "walking", None, df_itinary["arrival_time"].loc[0]]
            df_clean_itinary.loc[1] = [df_itinary["stop_id_s"].loc[1], df_itinary["stop_name"].loc[1], df_itinary["trip_id"].loc[1], None, df_itinary["departure_time"].loc[1]]
            compt = 2
        
        trip1 = list(df_itinary.trip_id)[1:-1]
        trip2 = list(df_itinary.trip_id)[2:]
        
        # When there is a change in the trip
        changes = [idx for idx, (t1, t2) in enumerate(zip(trip1, trip2)) if t1!=t2]

        for change in changes:
            # Case where the change occurs in the same station this mean a trip connection
            if (df_itinary["stop_id_s"].loc[change+1] == df_itinary["stop_id_s"].loc[change+2]):
                df_clean_itinary.loc[compt] = [df_itinary["stop_id_s"].loc[change+1], df_itinary["stop_name"].loc[change+1], df_itinary["trip_id"].loc[change+1], df_itinary["arrival_time"].loc[change+1], None]
                compt += 1
                df_clean_itinary.loc[compt] = [df_itinary["stop_id_s"].loc[change+2], df_itinary["stop_name"].loc[change+2], df_itinary["trip_id"].loc[change+2], None, df_itinary["departure_time"].loc[change+2]]
                compt += 1
            # Case where the change occurs on different stations this mean a walking connection between two stations
            else:
                
                if change-1 in changes:
                    if (df_itinary["stop_id_s"].loc[change] == df_itinary["stop_id_s"].loc[change+1]):
                        df_clean_itinary = df_clean_itinary[:-1]
                        df_clean_itinary.loc[compt] = [df_itinary["stop_id_s"].loc[change+1], df_itinary["stop_name"].loc[change+1], "Walking", df_itinary["arrival_time"].loc[change+1], None]
                        compt += 1
                    else:
                        df_clean_itinary = df_clean_itinary[:-1]
                        df_clean_itinary.loc[compt] = [df_itinary["stop_id_s"].loc[change+1], df_itinary["stop_name"].loc[change+1], "Walking", df_itinary["arrival_time"].loc[change+1], None]
                        compt += 1
                     
                elif change+1 in changes:
                    
                    if (df_itinary["stop_id_s"].loc[change] == df_itinary["stop_id_s"].loc[change+1]):
                        df_clean_itinary = df_clean_itinary[:-1]
                        compt -= 1
                        df_clean_itinary.loc[compt] = [df_itinary["stop_id_s"].loc[change+1], df_itinary["stop_name"].loc[change+1], df_itinary["trip_id"].loc[change], df_itinary["arrival_time"].loc[change], None]
                        compt += 1
                        df_clean_itinary.loc[compt] = [df_itinary["stop_id_s"].loc[change+2], df_itinary["stop_name"].loc[change+2], "Walking", df_itinary["arrival_time"].loc[change+2], None]
                        compt += 1
                    else:
                        df_clean_itinary.loc[compt] = [df_itinary["stop_id_s"].loc[change+1], df_itinary["stop_name"].loc[change+1], df_itinary["trip_id"].loc[change+1], df_itinary["arrival_time"].loc[change+1], None]
                        compt += 1
                        df_clean_itinary.loc[compt] = [df_itinary["stop_id_s"].loc[change+2], df_itinary["stop_name"].loc[change+2], "Walking", df_itinary["arrival_time"].loc[change+2], None]
                        compt += 1
                    
                else:
                    if (df_itinary["stop_id_s"].loc[change] == df_itinary["stop_id_s"].loc[change+1]):
                        df_clean_itinary = df_clean_itinary[:-1]
                        compt -= 1
                        df_clean_itinary.loc[compt] = [df_itinary["stop_id_s"].loc[change+1], df_itinary["stop_name"].loc[change+1], df_itinary["trip_id"].loc[change], df_itinary["arrival_time"].loc[change], None]
                        compt += 1
                        df_clean_itinary.loc[compt] = [df_itinary["stop_id_s"].loc[change+2], df_itinary["stop_name"].loc[change+2], "Walking", df_itinary["arrival_time"].loc[change+2], None]
                        compt += 1
                        df_clean_itinary.loc[compt] = [df_itinary["stop_id_s"].loc[change+2], df_itinary["stop_name"].loc[change+2], df_itinary["trip_id"].loc[change+2], None, df_itinary["departure_time"].loc[change+2]]
                        compt += 1
                    else:
                        df_clean_itinary.loc[compt] = [df_itinary["stop_id_s"].loc[change+1], df_itinary["stop_name"].loc[change+1], df_itinary["trip_id"].loc[change+1], df_itinary["arrival_time"].loc[change+1], None]
                        compt += 1
                        df_clean_itinary.loc[compt] = [df_itinary["stop_id_s"].loc[change+2], df_itinary["stop_name"].loc[change+2], "Walking", df_itinary["arrival_time"].loc[change+2], None]
                        compt += 1
                        df_clean_itinary.loc[compt] = [df_itinary["stop_id_s"].loc[change+2], df_itinary["stop_name"].loc[change+2], df_itinary["trip_id"].loc[change+2], None, df_itinary["departure_time"].loc[change+2]]
                        compt += 1
        
        if (df_itinary["stop_id_s"].loc[len(df_itinary)-1]==df_itinary["stop_id_s"].loc[len(df_itinary)-2]):
            i = len(df_itinary)-2
            while df_itinary["stop_id_s"].loc[len(df_itinary)-1]==df_itinary["stop_id_s"].loc[i]:
                if i==len(df_itinary)-2:
                    df_clean_itinary = df_clean_itinary[:-1]
                else:
                    df_clean_itinary = df_clean_itinary[:-1]
                    df_clean_itinary = df_clean_itinary[:-1]
                i -= 1
            
        else:
            df_clean_itinary.loc[len(df_itinary)-1] = [df_itinary["stop_id_s"].loc[len(df_itinary)-1], df_itinary["stop_name"].loc[len(df_itinary)-1], "Walking", df_itinary["arrival_time"].loc[len(df_itinary)-1], None]
                
        
        
        return df_clean_itinary