#! /usr/bin/python

# General node
class Node:
    NONE = 0
    ANCHOR = 1
    READ = 2

    def __init__(self, name=''):
        self.nodetype = Node.NONE
        self.name =  name

        self.outEdges = []   # a list of outgoing edges

    def connectsTo(self, node):
    	for edge in self.outEdges:
    		if edge.endNode == node:
    			return True

    	return False


# Anchor node for HERA scaffolder
class AnchorNode(Node):
    def __init__(self, name='', seq='', qual=''):
        # super(AnchorNode, self).__init__(name)
        Node.__init__(self, name)
        self.nodetype = Node.ANCHOR
        self.seq = seq
        self.qual = qual

# Read node in HERA scaffolder
class ReadNode(Node):
    def __init__(self, name='', seq='', qual=''):
        # super(ReadNode, self).__init__(name)
        Node.__init__(self, name)
        self.nodetype = Node.READ
        self.seq = seq
        self.qual = qual


# General edge
# Graphs are directed, undirected graphs will be simulated by adding another edge
# with different direction
class Edge:
    def __init__(self):
        self.startNode = None
        self.endNode = None

# Edge representing an overlap in HERA scaffolder graph
# It contains all the columns of a PAF line plus some extra calculated information
#   
# QNAME:     Query name
# QLEN:      Query length
# QSTART:    Query start (0-based)
# QEND:      Query end (0-based)
# STRAND:    Relative strand '+' or '-'
# TNAME:     Target name
# TLEN:      Target length
# TSTART:    Target start on original strand (0-based)
# TEND:      Target end on original strand (0-based)
# TRM:       Number of residue matches
# ABL:       Alignment block length
# MQUAL:     Mapping quality (0-255; 255 for missing)
#
# SI:        Sequence identity
# OS:        Overlap score
# ESleft:    Extension sore for extending start node with the end node to the left
# ESright:   Extension sore for extending start node with the end node to the right
class OvlEdge(Edge):
    def __init__(self, pafline = None, reverse = False):
        Edge.__init__(self)
        if pafline is None:
        	# Start node information
	        self.SName = ''
	        self.SLen = -1
	        self.SStart = -1
	        self.SEnd = -1
	        self.Strand = '+'
	        # End node information
	        self.EName = ''
	        self.ELen = -1
	        self.EStart = -1
	        self.EEnd = -1
	        # Other PAF information
	        self.NRM = 0
	        self.ABL = 0
	        self.MapQual = 0
	        # Calculated information
	        self.SI = 0.0
	        self.OS = 0.0
	        self.ESleft = 0.0
	        self.ESright = 0.0
        elif reverse == False:                # Query is start node and target is end node
            # Start node information
            self.SName = pafline['QNAME']
            self.SLen = pafline['QLEN']
            self.SStart = pafline['QSTART']
            self.SEnd = pafline['QEND']
            self.Strand = pafline['STRAND']
            # End node information
            self.EName = pafline['TNAME']
            self.ELen = pafline['TLEN']
            self.EStart = pafline['TSTART']
            self.EEnd = pafline['TEND']
            # Other PAF information
            self.NRM = pafline['NRM']
            self.ABL = pafline['ABL']
            self.MapQual = pafline['MQUAL']
            # Calculated information
            self.SI = pafline['SI']
            self.OS = pafline['OS']
            self.ESleft = pafline['QES1']
            self.ESright = pafline['QES2']
            # If extension scores are negative, set them to 0
            if self.ESleft < 0:
            	self.ESleft = 0
            if self.ESright < 0:
            	self.ESright = 0
        else:                               # Target is start node and query is end node
            # Start node information
            self.SName = pafline['TNAME']
            self.SLen = pafline['TLEN']
            self.SStart = pafline['TSTART']
            self.SEnd = pafline['TEND']
            self.Strand = pafline['STRAND']
            # End node information
            self.EName = pafline['QNAME']
            self.ELen = pafline['QLEN']
            self.EStart = pafline['QSTART']
            self.EEnd = pafline['QEND']
            # Other PAF information
            self.NRM = pafline['NRM']
            self.ABL = pafline['ABL']
            self.MapQual = pafline['MQUAL']
            # Calculated information
            self.SI = pafline['SI']
            self.OS = pafline['OS']
            self.ESleft = pafline['TES1']
            self.ESright = pafline['TES2']
            # If extension scores are negative, set them to 0
            if self.ESleft < 0:
            	self.ESleft = 0
            if self.ESright < 0:
            	self.ESright = 0

    # Calculated the reversed edge, query becomes the target and vice-versa
    def reversed(self):
    	newEdge = OvlEdge()
    	newEdge.startNode = self.endNode
    	newEdge.endNode   = self.startNode
    	# Start node information
    	newEdge.SName  = self.EName
    	newEdge.SLen   = self.ELen
    	newEdge.SStart = self.EStart
    	newEdge.SEnd   = self.EEnd
    	newEdge.Strand = self.Strand
    	# End node information
        newEdge.EName  = self.SName
        newEdge.ELen   = self.SLen
        newEdge.EStart = self.SStart
        newEdge.EEnd   = self.SEnd
        # Other PAF information
        newEdge.NRM     = self.NRM
        newEdge.ABL     = self.ABL
        newEdge.MapQual = self.MapQual
        # Calculated information
        newEdge.SI      = self.SI
        newEdge.OS      = self.OS
        newEdge.ESleft  = self.ESright
        newEdge.ESright = self.ESleft

    	return newEdge
