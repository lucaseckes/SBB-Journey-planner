# Robust Journey Planning

## Project description
Given a desired departure, or arrival time, our route planner computes the fastest route between two stops within a provided uncertainty tolerance expressed as interquartiles. 

## Video description
A video description of our work is available through this [link](https://filesender.switch.ch/filesender/?vid=78378e70-0216-9949-aa6a-00006075e59a).

## Files

The notebooks containing the different parts of our implementation are the following:
*  **1_Preprocessing_delay_computation.ipynb**: This notebook contains data pre-processing. It also predicts delays for any trips in the provided data. 
* **2_Graph_function**: This notebook contains the graph class  and applies the algorithm on graphs to output the best itinerary.
* **3_Results_Validation**: This notebook validates the results of our algorithm.
* **4_Dashboard** : This notebook contains a user interface where, given a starting station id, a destination station id, a list of edges, a time of arrival, and a certainty level of the journey success, the proposed itinerary is output.
* **myfunctions.py**: This file contains the code present in 2_Graph_function.

# Team
* Maya Abou-Rjeili
* Sarah Nicole Antille
* Lucas Eckes
* Lilia Ellouz