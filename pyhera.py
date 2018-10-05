#! /usr/bin/python

import sys, os
import paramsparser
import PAFutils
import math
import random
import time
from datetime import datetime

# To enable importing from samscripts submodule
SCRIPT_PATH = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(SCRIPT_PATH, 'samscripts/src'))

import utility_sam

from fastqparser import read_fastq
from PAFutils import load_paf
from graphs import *

import multiprocessing

SImin = .10     # Minimum sequence identity for the HERA algorithm
                # testing will be required to find the optimal value
                # NOTE: current value is very low!

OHmax = .40     # Maximim allowed overhang percentage, relative to aligned length

# Direction of extending a contig with reads
directionLEFT = 1
directionRIGHT = 0

compbase = {'A' : 'T',
            'T' : 'A',
            'C' : 'G',
            'G' : 'C',
            'N' : 'N'}

# Parameter definitions for paramparser
paramdefs = {'--version' : 0,
             '-v' : 0,
             '-o' : 1,
             '--output' : 1,
             '-t' : 1,
             '--threads' : 1}

# Function that test if an overlap (PAF line) is usable or not
# Overall, an overlap is not usable if:
# - one read contains the other - returns -1 
# - length of aligned part is to short compared to overhangs - returns -2
# - mapping quality is too low - returns -3
# If the read is usable, the function returns 1
def test_overlap(pafline, reads_to_discard, test_contained_reads = True, test_short_length = True, test_low_quality = True):

    # Fixing PAF line attributes so that they are strain independent
    # KK: I think this is not correct!!
    # if pafline['STRAND'] == '-':
    #     tstart = pafline['TSTART']
    #     tend = pafline['TEND']
    #     tlen = pafline['TLEN']
    #     new_tstart = tlen - tend
    #     new_tend = tlen - tstart
    #     pafline['TSTART'] = new_tstart
    #     pafline['TEND'] = new_tend

    QOH1 = pafline['QSTART']                        # Query left overhang
    QOH2 = pafline['QLEN'] - pafline['QEND']        # Query right overhang
    TOH1 = pafline['TSTART']                        # Target left overhang
    TOH2 = pafline['TLEN'] - pafline['TEND']        # Target right overhang

    QOL = pafline['QEND'] - pafline['QSTART'] + 1   # Query overlap length
    TOL = pafline['TEND'] - pafline['TSTART'] + 1   # Target overlap length

    SI = float(pafline['NRM']) / pafline['ABL']     # Sequence identity
                                                    # TODO: check if this is correctly calculated
                                                    # PAF fil might not give us completely correct information
    avg_ovl_len = (QOL + TOL)/2
    OS = avg_ovl_len * SI                           # Overlap score
    QES1 = OS + TOH1/2 - (QOH1 + TOH2)/2            # Extension score for extending Query with Target to the left
    QES2 = OS + TOH2/2 - (QOH2 + TOH1)/2            # Extension score for extending Query with Target to the right
    TES1 = OS + QOH1/2 - (QOH2 + TOH1)/2            # Extension score for extending Target with Query to the left
    TES2 = OS + QOH2/2 - (QOH1 + TOH2)/2            # Extension score for extending Target with Query to the right

    # NOTE: This seeme logical:
    # If a query extends further right or left then the target, it makes no sense to extend it in that direction
    # Therefore setting a corresponding extension score to 0
    if QOH1 >= TOH1:
        QES1 = 0
    else:
        TES1 = 0
    if QOH2 >= TOH2:
        QES2 = 0
    else:
        TES2 = 0

    minQOH = QOH1 if QOH1 < QOH2 else QOH2          # Smaller query overhang, will be used to determine if the overlap is discarded
    minTOH = TOH1 if TOH1 < TOH2 else TOH2          # Smaller target overhang, will be used to determine if the overlap is discarded

    minOH1 = QOH1 if QOH1 < TOH1 else TOH1          # Smaller left overhang
    minOH2 = QOH2 if QOH2 < TOH2 else TOH2          # Smaller right overhang

    # Test for too short aligned length
    # In this case the overlap is discarded, but both reads are kept
    # if test_short_length:
    #     if  float(minQOH + minTOH)/avg_ovl_len > OHmax:
    #         return -2

    # New test for short overlaps
    if test_short_length:
        if  float(minOH1 + minOH2)/avg_ovl_len > OHmax:
            return -2

    # Test for contained reads
    # Has to come after test for short aligned length, if the overlap is of too short a length
    # Its probably a false overlap
    if test_contained_reads:
        if QOH1 >= TOH1 and QOH2 >= TOH2:
            # Target is contained within the query
            # Discarding the overlap and target read
            tname = pafline['TNAME']
            reads_to_discard[tname] = 1
            return -1
        if TOH1 >= QOH1 and TOH2 >= QOH2:
            # Query is contained within the target
            # Discarding the overlap and query read
            qname = pafline['QNAME']
            reads_to_discard[qname] = 1
            return -1

    # Test for low quality overlap
    if test_low_quality:
        if SI < SImin:
            return -3

    # If there are some overlaps with zero extension score on both ends, duscard those as well
    if QES1 <= 0 and QES2 <= 0 and TES1 <= 0 and TES2 <= 0:
        return -4

    # If the overlap is correct, write relevant info to the pafline dictionary and return True
    pafline['SI'] = SI
    pafline['OS'] = OS
    pafline['QES1'] = QES1
    pafline['QES2'] = QES2
    pafline['TES1'] = TES1
    pafline['TES2'] = TES2

    return 1

def load_anchornodes(contigs_file, output=True):
    [cheaders, cseqs, cquals] = load_fast(contigs_file, output)
    anchornodes = {}

    # Adding contigs as anchor nodes
    for i in xrange(len(cheaders)):
        header = cheaders[i]
        idx = header.find(' ')          # Removing everything from header, after the first space
        if idx > -1:
            header = header[:idx]
        seq = cseqs[i]
        qual = cquals[i]
        node = AnchorNode(header, seq, qual)
        anchornodes[header] = node

    return anchornodes

def load_readnodes(reads_file, output=True):
    [rheaders, rseqs, rquals] = load_fast(reads_file, output)
    readnodes = {}

    # Adding reads as read nodes
    for i in xrange(len(rheaders)):
        header = rheaders[i]
        idx = header.find(' ')          # Removing everything from header, after the first space
        if idx > -1:
            header = header[:idx]
        seq = rseqs[i]
        qual = rquals[i]
        node = ReadNode(header, seq, qual)
        readnodes[header] = node

    return readnodes

def load_cr_overlaps(cr_overlaps_file, anchornodes, readnodes, reads_to_discard, output=True):
    crovledges = []             # Edges representing overlaps between reads and contigs

    cr_paf_lines = load_paf(cr_overlaps_file, output)

    ncontained = nshort = nlowqual = nusable = nzeroes = 0
    for pafline in cr_paf_lines:
        qcontig = True              # Is PAF query a contig? If false, PAF target is contig
        rnode = anode = None
        qname = pafline['QNAME']
        tname = pafline['TNAME']

        if qname in anchornodes:
            anode = anchornodes[qname]
        elif qname in readnodes:
            rnode = readnodes[qname]
        else:
            sys.stderr.write('\nERROR CROVL: QNAME from PAF (%s) doesn\'t exist in reads or contigs!' % qname)

        if tname in anchornodes:
            anode = anchornodes[tname]
            qcontig = False
        elif tname in readnodes:
            rnode = readnodes[tname]
        else:
            sys.stderr.write('\nERROR CROVL: TNAME from PAF (%s) doesn\'t exist in reads or contigs!' % tname)

        # retval = test_overlap(pafline, reads_to_discard, test_contained_reads = False)
        retval = test_overlap(pafline, reads_to_discard)
        if retval == 1:
            nusable += 1
            startNode = endNode = None
            if qcontig:
                startNode = anode
                endNode = rnode
            else:
                startNode = rnode
                endNode = anode
            edge1 = OvlEdge(pafline)
            edge2 = OvlEdge(pafline, reverse=True)
            edge1.startNode = startNode
            edge1.endNode = endNode
            startNode.outEdges.append(edge1)
            edge2.startNode = endNode
            edge2.endNode = startNode
            endNode.outEdges.append(edge2)
            crovledges.append(edge1)
            crovledges.append(edge2)
        elif retval == -1:
            ncontained += 1
        elif retval == -2:
            nshort += 1
        elif retval == -3:
            nlowqual += 1
        elif retval == -4:
            nzeroes += 1
        else:
            sys.stderr.write('\nERROR: unknown return value by test_overlap()!')

    isolated_anodes = {}
    for aname, anode in anchornodes.iteritems():
        if len(anode.outEdges) == 0:
            isolated_anodes[aname] = anode

    # for aname in isolated_anodes:
    #     del anchornodes[aname]


    if output == True:
        sys.stdout.write('\nProcessing overlaps between contigs and reads!')
        sys.stdout.write('\nNumber of overlaps: %d' % len(cr_paf_lines))
        sys.stdout.write('\nUsable: %d' % nusable)
        sys.stdout.write('\nContained: %d' % ncontained)
        sys.stdout.write('\nShort: %d' % nshort)
        sys.stdout.write('\nLow quality: %d' % nlowqual)
        sys.stdout.write('\nZero ES: %d' % nzeroes)
        sys.stdout.write('\n')

    return crovledges, isolated_anodes


# Load read/read overlaps in a signle thread
def load_rr_overlaps_ST(rr_overlaps_file, readnodes, reads_to_discard, output=True):
    rrovledges = []             # Edges representing overlaps between reads and reads

    rr_paf_lines = load_paf(rr_overlaps_file, output)
    dummy_reads_to_discard = {}         # When checking overlaps between reads, only discarding overlaps
                                        # and not the actual reads

    ncontained = nshort = nlowqual = nusable = 0
    for pafline in rr_paf_lines:
        rnode1 = rnode2 = None
        qname = pafline['QNAME']
        tname = pafline['TNAME']

        if qname in readnodes:
            rnode1 = readnodes[qname]
        else:
            sys.stderr.write('\nERROR RROVL: QNAME from PAF (%s) doesn\'t exist in reads!' % qname)

        if tname in readnodes:
            rnode2 = readnodes[tname]
        else:
            sys.stderr.write('\nERROR RROVL: TNAME from PAF (%s) doesn\'t exist in reads!' % tname)

        # retval = test_overlap(pafline, reads_to_discard, test_contained_reads=False, test_short_length=False)
        retval = test_overlap(pafline, dummy_reads_to_discard)
        if retval == 1:
            nusable += 1
            edge1 = OvlEdge(pafline)
            edge2 = OvlEdge(pafline, reverse=True)
            edge1.startNode = rnode1
            edge1.endNode = rnode2
            rnode1.outEdges.append(edge1)
            edge2.startNode = rnode2
            edge2.endNode = rnode1
            rnode2.outEdges.append(edge2)
            rrovledges.append(edge1)
            rrovledges.append(edge2)
        elif retval == -1:
            ncontained += 1
        elif retval == -2:
            nshort += 1
        elif retval == -3:
            nlowqual += 1
        else:
            sys.stderr.write('\nERROR: unknown return value by test_overlap()!')

    if output == True:
        sys.stdout.write('\nProcessing overlaps between reads and reads!')
        sys.stdout.write('\nNumber of overlaps: %d' % len(rr_paf_lines))
        sys.stdout.write('\nUsable: %d' % nusable)
        sys.stdout.write('\nContained: %d' % ncontained)
        sys.stdout.write('\nShort: %d' % nshort)
        sys.stdout.write('\nLow quality: %d' % nlowqual)
        sys.stdout.write('\n')

    return rrovledges

def load_rr_overlaps_part(proc_id, rr_paf_lines_part, readnodes, out_q):

    sys.stdout.write('\nPYHERA: Starting process %d...\n' % proc_id)

    rrovledges_part = []
    readnodes_part = {}             # A dictionary to collect partial graph
                                    # created by this function
    ncontained = nshort = nlowqual = nusable = 0

    dummy_reads_to_discard = {}     # Currently not used, but a placeholder for maybe using it later

    for pafline in rr_paf_lines_part:
        rnode1 = rnode2 = None
        qname = pafline['QNAME']
        tname = pafline['TNAME']

        if qname in readnodes:
            rnode1 = readnodes[qname]
        else:
            sys.stderr.write('\nERROR RROVL: QNAME from PAF (%s) doesn\'t exist in reads!' % qname)

        if tname in readnodes:
            rnode2 = readnodes[tname]
        else:
            sys.stderr.write('\nERROR RROVL: TNAME from PAF (%s) doesn\'t exist in reads!' % tname)

        # retval = test_overlap(pafline, reads_to_discard, test_contained_reads=False, test_short_length=False)
        retval = test_overlap(pafline, dummy_reads_to_discard)
        if retval == 1:
            nusable += 1
            edge1 = OvlEdge(pafline)
            edge2 = OvlEdge(pafline, reverse=True)
            edge1.startNode = rnode1
            edge1.endNode = rnode2
            # rnode1.outEdges.append(edge1)
            t_edges = []
            if qname in readnodes_part:
                t_edges = readnodes_part[qname]
            t_edges.append(edge1)
            readnodes_part[qname] = t_edges

            edge2.startNode = rnode2
            edge2.endNode = rnode1
            # rnode2.outEdges.append(edge2)
            t_edges = []
            if tname in readnodes_part:
                t_edges = readnodes_part[tname]
            t_edges.append(edge2)
            readnodes_part[tname] = t_edges

            rrovledges_part.append(edge1)
            rrovledges_part.append(edge2)
        elif retval == -1:
            ncontained += 1
        elif retval == -2:
            nshort += 1
        elif retval == -3:
            nlowqual += 1
        else:
            sys.stderr.write('\nERROR: unknown return value by test_overlap()!')

    out_q.put((rrovledges_part, readnodes_part, ncontained, nshort, nlowqual, nusable))
    sys.stdout.write('\nEnding process %d...\n' % proc_id)
    pass


# Load read/read overlaps in multiple threads
def load_rr_overlaps_MT(rr_overlaps_file, readnodes, reads_to_discard, numthreads, output=True):
    rrovledges = []             # Edges representing overlaps between reads and reads
    readnodes_parts = []

    rr_paf_lines = load_paf(rr_overlaps_file, output)
    dummy_reads_to_discard = {}         # When checking overlaps between reads, only discarding overlaps
                                        # and not the actual reads
    chunk_size = int(math.ceil(float(len(rr_paf_lines))/numthreads))
    rr_paf_lines_split = [rr_paf_lines[i:i+chunk_size] for i in xrange(0, len(rr_paf_lines), chunk_size)]

   
    # Spawning and calling processes
    out_q = multiprocessing.Queue()
    jobs = []
    proc_id = 0
    for rr_paf_lines_part in rr_paf_lines_split:
        proc_id += 1
        partname = 'THREAD%d' % proc_id
        proc = multiprocessing.Process(name=partname, target=load_rr_overlaps_part, args=(proc_id, rr_paf_lines_part, readnodes, out_q,))
        jobs.append(proc)
        proc.start()

    # Summarizing results from different processes
    ncontained = nshort = nlowqual = nusable = 0
    for i in xrange(len(jobs)):
        (rrovledges_part, readnodes_part, t_ncontained, t_nshort, t_nlowqual, t_nusable) = out_q.get()
        rrovledges += rrovledges_part
        ncontained += t_ncontained
        nshort += t_nshort
        nlowqual += t_nlowqual
        nusable += t_nusable
        readnodes_parts.append(readnodes_part)
    
    if output:
        sys.stdout.write('\nPYHERA: All processes finished!')

    # Wait for all processes to end
    for proc in jobs:
        proc.join()        

    for readnodes_part in readnodes_parts:
        for rname, t_outedges in readnodes_part.iteritems():
            rnode = readnodes[rname]
            rnode.outEdges += t_outedges

    ncontained = nshort = nlowqual = nusable = 0
    for pafline in rr_paf_lines:
        rnode1 = rnode2 = None
        qname = pafline['QNAME']
        tname = pafline['TNAME']

        if qname in readnodes:
            rnode1 = readnodes[qname]
        else:
            sys.stderr.write('\nERROR RROVL: QNAME from PAF (%s) doesn\'t exist in reads!' % qname)

        if tname in readnodes:
            rnode2 = readnodes[tname]
        else:
            sys.stderr.write('\nERROR RROVL: TNAME from PAF (%s) doesn\'t exist in reads!' % tname)

        # retval = test_overlap(pafline, reads_to_discard, test_contained_reads=False, test_short_length=False)
        retval = test_overlap(pafline, dummy_reads_to_discard)
        if retval == 1:
            nusable += 1
            edge1 = OvlEdge(pafline)
            edge2 = OvlEdge(pafline, reverse=True)
            edge1.startNode = rnode1
            edge1.endNode = rnode2
            rnode1.outEdges.append(edge1)
            edge2.startNode = rnode2
            edge2.endNode = rnode1
            rnode2.outEdges.append(edge2)
            rrovledges.append(edge1)
            rrovledges.append(edge2)
        elif retval == -1:
            ncontained += 1
        elif retval == -2:
            nshort += 1
        elif retval == -3:
            nlowqual += 1
        else:
            sys.stderr.write('\nERROR: unknown return value by test_overlap()!')

    if output == True:
        sys.stdout.write('\nProcessing overlaps between reads and reads!')
        sys.stdout.write('\nNumber of overlaps: %d' % len(rr_paf_lines))
        sys.stdout.write('\nUsable: %d' % nusable)
        sys.stdout.write('\nContained: %d' % ncontained)
        sys.stdout.write('\nShort: %d' % nshort)
        sys.stdout.write('\nLow quality: %d' % nlowqual)
        sys.stdout.write('\n')

    return rrovledges
    
# 1st Approach
# For every anchor node consider all connecting read nodes
# For further extension consider only the read with the highest OVERLAP score
def getPaths_maxovl(anchornodes, readnodes, crovledges, rrovledges, output=True):
    paths = []      # A list of paths
                    # Each path is a list of its own, containing edges that are traversed
    reads_traversed = {}    # A dictionary of reads that have already been traversed
                            # Each read can only be used once
    N = 20           # Number of nodes placed on stack in each steop of graph traversal

    if output:
        sys.stdout.write('\nPYHERA: Starting collecting paths using maximum overlap score!')
    for (aname, anode) in anchornodes.iteritems():
        for edge in anode.outEdges:
            path = []               # Initializing a path
            stack = []              # and a stack for graph traversal
                                    # A stack will contain a list of edges to be processed

            # For each read determine the direction of extension (LEFT or RIGHT)
            # Needs to be preserved throughout the path
            direction = directionLEFT
            if edge.ESright > edge.ESleft:
                direction = directionRIGHT

            # KK: Control
            if edge.ESright <= 0 and edge.ESleft <= 0:
                continue

            stack.append(edge)      # For each inital node, place only its edge on the stack
            # In each step of graph traversal:
            # - Pop the last node
            # - Check if it can connect to an anchor node
            # - If it can, the path is complete
            # - If not, get a number of connected read nodes with the greatest OS and place them on the stack
            # - If no reads are available, adjust the path and continue
            while stack:
                redge = stack.pop()                             # Pop an edge from the stack
                rnode = redge.endNode                           # And the corresponding node
                path.append(redge)                              # Add edge to the path
                reads_traversed[rnode.name] = 1                 # And mark the node as traversed

                Aedges = []                                     # Edges to anchor nodes
                Redges = []                                     # Edges to read nodes

                for edge2 in rnode.outEdges:
                    # KK: Control
                    if edge2.ESright <= 0 and edge2.ESleft <= 0:
                        continue

                    endNode = edge2.endNode
                    if endNode.name in reads_traversed:         # Each read can only be used once
                        continue
                    direction2 = directionLEFT
                    if edge2.ESright > edge2.ESleft:
                        direction2 = directionRIGHT
                    if direction2 != direction:                 # Direction of extension must be maintained
                        continue

                    if endNode.nodetype == Node.ANCHOR:
                        if endNode.name != aname:               # We only want nodes that are different from the starting node!
                            Aedges.append(edge2)                # NOTE: this might change, as we migh want scaffold circulat genomes!
                    elif endNode.nodetype == Node.READ:
                        Redges.append(edge2)
                    else:
                        sys.stderr.write("PYHERA: ERROR - invalid node type: %d" % endNode.nodetype)

                if Aedges:                                                  # If anchor nodes have been reached find the best one
                    Aedges.sort(key=lambda edge: edge.OS, reverse=True)     # by sorting them according to OS and taking the first one
                    Aedge = Aedges[0]                                       # Create a path and end this instance of tree traversal
                    path.append(Aedge)
                    paths.append(path)
                    break
                elif Redges:                                                # If no anchor nodes have been found we have to continue with read nodes
                    Redges.sort(key=lambda edge: edge.OS, reverse=True)     # Sort them and take top N to put on the stack
                    # Redge = Redges[0]
                    # stack.append(Redge.endNode)
                    stack += [redge for redge in reversed(Redges[0:N])]     # Place N best edges on the stack in reverse orded, so that the best one ends on top
                    
                    # KK: this is node at a different place in the code
                    # path.append(Redge)
                    # reads_traversed[Redge.endNode.name] = 1
                else:                                                       # Graph traversal has come to a dead end
                    try:
                        edge2 = path.pop()                                      # Remove the last edge from the path
                        del reads_traversed[rnode.name]                         # Remove current read node from the list of traversed ones
                    except:
                        import pdb
                        pdb.set_trace()
                        pass


    if output:
        sys.stdout.write('\nPYHERA: Finishing collecting paths using maximum overlap score!')

    return paths


# 2nd Approach
# For every anchor node consider all connecting read nodes
# For further extension consider only the read with the highest EXTENSION score
def getPaths_maxext(anchornodes, readnodes, crovledges, rrovledges, output=True):
    paths = []      # A list of paths
                    # Each path is a list of its own, containing edges that are traversed
    reads_traversed = {}    # A dictionary of reads that have already been traversed
                            # Each read can only be used once
    N = 20           # Number of nodes placed on stack in each steop of graph traversal

    if output:
        sys.stdout.write('\nPYHERA: Starting collecting paths using maximum extension score!')

    for (aname, anode) in anchornodes.iteritems():
        for edge in anode.outEdges:
            path = []               # Initializing a path
            stack = []              # and a stack for graph traversal
                                    # A stack will contain a list of edges to be processed

            # For each read determine the direction of extension (LEFT or RIGHT)
            # Needs to be preserved throughout the path
            direction = directionLEFT
            if edge.ESright > edge.ESleft:
                direction = directionRIGHT

            stack.append(edge)      # For each inital node, place only its edge on the stack
            # In each step of graph traversal:
            # - Pop the last node
            # - Check if it can connect to an anchor node
            # - If it can, the path is complete
            # - If not, get a number of connected read nodes with the greatest ES and place them on the stack
            # - If no reads are available, adjust the path and continue
            while stack:
                redge = stack.pop()                             # Pop an edge from the stack
                rnode = redge.endNode                           # And the corresponding node
                path.append(redge)                              # Add edge to the path
                reads_traversed[rnode.name] = 1                 # And mark the node as traversed

                Aedges = []                                     # Edges to anchor nodes
                Redges = []                                     # Edges to read nodes

                for edge2 in rnode.outEdges:
                    endNode = edge2.endNode
                    if endNode.name in reads_traversed:          # Each read can only be used once
                        continue
                    direction2 = directionLEFT
                    if edge2.ESright > edge2.ESleft:
                        direction2 = directionRIGHT
                    if direction2 != direction:                # Direction of extension must be maintained
                        continue

                    if endNode.nodetype == Node.ANCHOR:
                        if endNode.name != aname:               # We only want nodes that are different from the starting node!
                            Aedges.append(edge2)                # NOTE: this might change, as we migh want scaffold circulat genomes!
                    elif endNode.nodetype == Node.READ:
                        Redges.append(edge2)

                if Aedges:                                                  # If anchor nodes have been reached find the best one
                    if direction == directionLEFT:                          # by sorting them according to ES and taking the first one
                        Aedges.sort(key=lambda edge: edge.ESleft, reverse=True)
                    else:
                        Aedges.sort(key=lambda edge: edge.ESright, reverse=True)
                    Aedge = Aedges[0]                                       # Create a path and end this instance of tree traversal
                    path.append(Aedge)
                    paths.append(path)
                    break
                elif Redges:                                                # If no anchor nodes have been found we have to continue with read nodes
                    if direction == directionLEFT:                          # Sort them and take top N to put on the stack (currently testing with N=1)
                        Redges.sort(key=lambda edge: edge.ESleft, reverse=True)
                        stack += [redge for redge in reversed(Redges[0:N]) if redge.ESleft > 0]
                    else:
                        Redges.sort(key=lambda edge: edge.ESright, reverse=True)
                        stack += [redge for redge in reversed(Redges[0:N]) if redge.ESright > 0]
                    
                    # stack += [redge for redge in reversed(Redges[0:N])]     # Place N best edges on the stack in reverse orded, so that the best one ends on top

                else:                                                       # Graph traversal has come to a dead end
                    try:
                        edge2 = path.pop()                                      # Remove the last edge from the path
                        del reads_traversed[rnode.name]                         # Remove current read node from the list of traversed ones
                    except:
                        import pdb
                        pdb.set_trace()
                        pass

    if output:
        sys.stdout.write('\nPYHERA: Finishing collecting paths using maximum extension score!')

    return paths

# 3rd Approach
# Monte Carlo method - randomly select reads for each extension
# probability of selecting a read is proportional to extension score
def getPaths_MC(anchornodes, readnodes, crovledges, rrovledges, numpaths, output=True):
    paths = []      # A list of paths
                    # Each path is a list of its own, containing edges that are traversed
    reads_traversed = {}    # A dictionary of reads that have already been traversed
                            # Each read can only be used once
                            # NOTE: should this be used with Monte Carlo!

    N = 10
    max_iterations = 10000
    iteration = 0
    igoal = 1000
    random.seed()
    if output:
        sys.stdout.write('\nPYHERA: Starting collecting paths using Monte Carlo method!')
        sys.stdout.write('\nITERATIONS:')
    anames = anchornodes.keys()
    while len(paths) < numpaths and iteration < max_iterations:
        iteration += 1
        if output and iteration > igoal:
            sys.stdout.write(' %d' % igoal)
            igoal += 1000
        # Randomly choose an anchor node
        aname = random.choice(anames)
        anode = anchornodes[aname]
    
        totalES_A = 0.0
        problist_A = []                                         # Used to randomly select an edge to use
        problist_A.append(totalES_A)
        if len(anode.outEdges) == 0:                            # Skip nodes that have no edges (NOTE: this can probably be removed since such nodes have been discarded)
            continue
        for edge in anode.outEdges:                             # Calculate total Extension score, for random selection
            maxES = edge.ESleft if edge.ESleft > edge.ESright else edge.ESright
            totalES_A += maxES
            problist_A.append(totalES_A)

        rand = random.random()*totalES_A
        k=1
        try:
            while problist_A[k] < rand:
                k += 1
        except:
            import pdb
            pdb.set_trace()
            pass

        edge = anode.outEdges[k-1]
        # KK: control
        if edge.ESleft <= 0 and edge.ESright <= 0:
            continue

        path = []               # Initializing a path
        stack = []              # and a stack for graph traversal
                                # A stack will contain a list of edges to be processed

        # For each read determine the direction of extension (LEFT or RIGHT)
        # Needs to be preserved throughout the path
        direction = directionLEFT
        if edge.ESright > edge.ESleft:
            direction = directionRIGHT

        stack.append(edge)      # For each inital node, place only its edge on the stack
        # In each step of graph traversal:
        # - Pop the last node
        # - Check if it can connect to an anchor node
        # - If it can, the path is complete
        # - If not, randomly generate a number of connected read nodes with the probability of generation
        #   proportional to ES and place them on the stack
        # - If no reads are available, adjust the path and continue
        while stack:
            redge = stack.pop()                             # Pop an edge from the stack
            rnode = redge.endNode                           # And the corresponding node
            path.append(redge)                              # Add edge to the path
            reads_traversed[rnode.name] = 1                 # And mark the node as traversed

            Aedges = []                                     # Edges to anchor nodes
            Redges = []                                     # Edges to read nodes

            for edge2 in rnode.outEdges:
                # KK: control
                if edge2.ESleft <= 0 and edge2.ESright <= 0:
                    continue
                endNode = edge2.endNode
                if endNode.name in reads_traversed:          # Each read can only be used once
                    continue
                direction2 = directionLEFT
                if edge2.ESright > edge2.ESleft:
                    direction2 = directionRIGHT
                if direction2 != direction:                # Direction of extension must be maintained
                    continue

                if endNode.nodetype == Node.ANCHOR:
                    if endNode.name != aname:               # We only want nodes that are different from the starting node!
                        Aedges.append(edge2)                # NOTE: this might change, as we migh want scaffold circulat genomes!
                elif endNode.nodetype == Node.READ:
                    Redges.append(edge2)

            if Aedges:                                                  # If anchor nodes have been reached find the best one
                if direction == directionLEFT:                          # by sorting them according to ES and taking the first one
                    Aedges.sort(key=lambda edge: edge.ESleft, reverse=True)
                else:
                    Aedges.sort(key=lambda edge: edge.ESright, reverse=True)
                Aedge = Aedges[0]                                       # Create a path and end this instance of tree traversal
                path.append(Aedge)
                paths.append(path)
                break
            elif Redges:                                                # If no anchor nodes have been found we have to continue with read nodes
                totalES = 0.0                                           # Randomly select N to put on the stack
                problist = []                                        
                problist.append(totalES)
                if direction == directionLEFT:                          # Extending to left
                    for redge in Redges:
                        totalES += redge.ESleft
                        problist.append(totalES)
                else:                                                   # Extending to RIGHT
                    for redge in Redges:
                        totalES += redge.ESright
                        problist.append(totalES)
                
                try:
                    for j in range(N):                                      # Randomly generating N nodes to place on stack
                        rand = random.random()*totalES                      # NOTE: currently its possible for the same node to be placed more than once
                        k = 1
                        while problist[k] < rand:
                            k += 1
                        stack.append(Redges[k-1])
                except:
                    import pdb
                    pdb.set_trace()
                    pass
            else:                                                       # Graph traversal has come to a dead end
                try:
                    edge2 = path.pop()                                      # Remove the last edge from the path
                    del reads_traversed[rnode.name]                         # Remove current read node from the list of traversed ones
                except:
                    import pdb
                    pdb.set_trace()
                    pass

    if output:
        sys.stdout.write('\nPYHERA: Finishing collecting paths using Monte Carlo method!')
        if iteration >= max_iterations:
            sys.stdout.write('\nPYHERA: Finished by running out of itterations!')

    return paths


# 3rd Approach
# Monte Carlo method - randomly select reads for each extension
# probability of selecting a read is proportional to extension score
def getPaths_MC_OLD(anchornodes, readnodes, crovledges, rrovledges, numpaths, output=True):
    paths = []      # A list of paths
                    # Each path is a list of its own, containing edges that are traversed
    reads_traversed = {}    # A dictionary of reads that have already been traversed
                            # Each read can only be used once
                            # NOTE: should this be used with Monte Carlo!

    N = 10
    pathspernode = int(math.ceil(float(numpaths)/len(anchornodes)) + 1)   # The number of path generated for each anchor node
    random.seed()

    if output:
        sys.stdout.write('\nPYHERA: Starting collecting paths using Monte Carlo method!')

    for (aname, anode) in anchornodes.iteritems():
        totalES_A = 0.0
        problist_A = []                                         # Used to randomly select an edge to use
        problist_A.append(totalES_A)
        if len(anode.outEdges) == 0:                            # Skip nodes that have no edges
            continue
        for edge in anode.outEdges:                             # Calculate total Extension score, for random selection
            maxES = edge.ESleft if edge.ESleft > edge.ESright else edge.ESright
            totalES_A += maxES
            problist_A.append(totalES_A)
        for i in xrange(pathspernode):                          # For each anchor node generate "pathspernode" paths
            rand = random.random()*totalES_A
            k=1
            try:
                while problist_A[k] < rand:
                    k += 1
            except:
                import pdb
                pdb.set_trace()
                pass

            edge = anode.outEdges[k-1]
            path = []               # Initializing a path
            stack = []              # and a stack for graph traversal
                                    # A stack will contain a list of edges to be processed

            # For each read determine the direction of extension (LEFT or RIGHT)
            # Needs to be preserved throughout the path
            direction = directionLEFT
            if edge.ESright > edge.ESleft:
                direction = directionRIGHT

            stack.append(edge)      # For each inital node, place only its edge on the stack
            # In each step of graph traversal:
            # - Pop the last node
            # - Check if it can connect to an anchor node
            # - If it can, the path is complete
            # - If not, randomly generate a number of connected read nodes with the probability of generation
            #   proportional to ES and place them on the stack
            # - If no reads are available, adjust the path and continue
            while stack:
                redge = stack.pop()                             # Pop an edge from the stack
                rnode = redge.endNode                           # And the corresponding node
                path.append(redge)                              # Add edge to the path
                reads_traversed[rnode.name] = 1                 # And mark the node as traversed

                Aedges = []                                     # Edges to anchor nodes
                Redges = []                                     # Edges to read nodes

                for edge2 in rnode.outEdges:
                    endNode = edge2.endNode
                    if endNode.name in reads_traversed:          # Each read can only be used once
                        continue
                    direction2 = directionLEFT
                    if edge2.ESright > edge2.ESleft:
                        direction2 = directionRIGHT
                    if direction2 != direction:                # Direction of extension must be maintained
                        continue

                    if endNode.nodetype == Node.ANCHOR:
                        if endNode.name != aname:               # We only want nodes that are different from the starting node!
                            Aedges.append(edge2)                # NOTE: this might change, as we migh want scaffold circulat genomes!
                    elif endNode.nodetype == Node.READ:
                        Redges.append(edge2)

                if Aedges:                                                  # If anchor nodes have been reached find the best one
                    if direction == directionLEFT:                          # by sorting them according to ES and taking the first one
                        Aedges.sort(key=lambda edge: edge.ESleft, reverse=True)
                    else:
                        Aedges.sort(key=lambda edge: edge.ESright, reverse=True)
                    Aedge = Aedges[0]                                       # Create a path and end this instance of tree traversal
                    path.append(Aedge)
                    paths.append(path)
                    break
                elif Redges:                                                # If no anchor nodes have been found we have to continue with read nodes
                    totalES = 0.0                                           # Randomly select N to put on the stack
                    problist = []                                        
                    problist.append(totalES)
                    if direction == directionLEFT:                          # Extending to left
                        for redge in Redges:
                            totalES += redge.ESleft
                            problist.append(totalES)
                    else:                                                   # Extending to RIGHT
                        for redge in Redges:
                            totalES += redge.ESright
                            problist.append(totalES)
                    
                    try:
                        for j in range(N):                                      # Randomly generating N nodes to place on stack
                            rand = random.random()*totalES                      # NOTE: currently its possible for the same node to be placed more than once
                            k = 1
                            while problist[k] < rand:
                                k += 1
                            stack.append(Redges[k-1])
                    except:
                        import pdb
                        pdb.set_trace()
                        pass
                else:                                                       # Graph traversal has come to a dead end
                    try:
                        edge2 = path.pop()                                      # Remove the last edge from the path
                        del reads_traversed[rnode.name]                         # Remove current read node from the list of traversed ones
                    except:
                        import pdb
                        pdb.set_trace()
                        pass

    if output:
        sys.stdout.write('\nPYHERA: Finishing collecting paths using Monte Carlo method!')

    return paths


# Remove readnode from the graph
# - Remove from all anchornodes' outgoing edges
# - Remove from all readnodes' outgoing edges
# - remove from readnodes
# - Remove from crovl edges
# - remove from rrovl edges
def remove_readnode(rname, anchornodes, readnodes, crovledges, rrovledges):

    if rname not in readnodes:
        sys.stderr.write('\nERROR: trying to remove nonexisting read node: %s!' % rname)

    # Fetchng readnode to delete
    rnode = readnodes[rname]

    numRemovedEdges = 0

    # Removing from crovledges
    # Not sure if I can remove from the list I am iterating on so doing this instead
    edgesToRemove = []
    for edge in crovledges:
        if edge.startNode == rnode or edge.endNode == rnode:
            edgesToRemove.append(edge)
    # Removing selected edges
    for edgeTR in edgesToRemove:
        crovledges.remove(edgeTR)
        numRemovedEdges += 1

    # Removing from rrovledges
    edgesToRemove = []
    for edge in rrovledges:
        if edge.startNode == rnode or edge.endNode == rnode:
            edgesToRemove.append(edge)
    # Removing selected edges
    for edgeTR in edgesToRemove:
        rrovledges.remove(edgeTR)
        numRemovedEdges += 1

    # Removing node from readnodes
    del readnodes[rname]

    # Removing outgoing edges from readnodes
    for rnode2 in readnodes.itervalues():
        edgesTR = []
        for edge in rnode2.outEdges:
            if edge.startNode == rnode or edge.endNode == rnode:
                edgesTR.append(edge)
        for edge in edgesTR:
            rnode2.outEdges.remove(edge)

    # Removing outgoing edges from anchornodes
    for anode in anchornodes.itervalues():
        edgesTR = []
        for edge in anode.outEdges:
            if edge.startNode == rnode or edge.endNode == rnode:
                edgesTR.append(edge)
        for edge in edgesTR:
            anode.outEdges.remove(edge)

    return numRemovedEdges


### Cleaning up the graph
# - Read nodes can connect only to a single anchor node, with maximum overlap score
# - removing overlaps for discarded reads
# - TODO: Anything else I can think of
def graph_cleanup(anchornodes, readnodes, crovledges, rrovledges, reads_to_discard=None, output=True):

    edgesRemoved = 0

    if output:
        sys.stdout.write('\nPYHERA: Starting graph cleanup!')
        sys.stdout.write('\nPYHERA: Discarding reads ...')

    # Discading reads that are in the discard dictionary
    # To make thing more efficient, have to reverse the logic
    # Discarding from anchornodes
    if output:
        sys.stdout.write('\nPYHERA: Discarding from anchor nodes ...')
    for anode in anchornodes.itervalues():
        edgesTR = []
        for edge in anode.outEdges:
            if edge.endNode.name in reads_to_discard:
                edgesTR.append(edge)
        for edge in edgesTR:
            anode.outEdges.remove(edge)
            # KK: commented to speed thng up, whether this list will be usefull remain to be seen
            # crovledges.remove(edge)

    if output:
        sys.stdout.write('\nPYHERA: Discarding from read nodes ...')
    for rnode in readnodes.itervalues():
        edgesTR = []
        for edge in rnode.outEdges:
            if edge.endNode.name in reads_to_discard:
                edgesTR.append(edge)
        for edge in edgesTR:
            rnode.outEdges.remove(edge)
            # KK: commented to speed thng up, whether this list will be usefull remain to be seen
            # rrovledges.remove(edge)

    for rname in reads_to_discard.iterkeys():
        if rname in readnodes:
            del readnodes[rname]
        elif output:
            sys.stdout.write('\nPYHERA: ERROR trying to delete a read: %s' % rname)

    # OLD:
    # if reads_to_discard is not None:
    #     for rname in reads_to_discard.iterkeys():
    #         remove_readnode(rname, anchornodes, readnodes, crovledges, rrovledges)

    if output:
        sys.stdout.write('\nPYHERA: Preserving only the best overlap with anchor node!')
        sys.stdout.write('\nCompleted: ')
    total = len(readnodes)
    count = 0
    next_step = 0.1
    # For each readnode discarding all overlap for contigs except the one with the best overlap score
    for rnode in readnodes.itervalues():
        count += 1
        if output and count > next_step*total:
            sys.stdout.write('%d%% ' % (next_step*100))
            next_step += 0.1

        bestANode = None
        maxOS = 0
        for edge in rnode.outEdges:
            outnode = edge.endNode
            if outnode.nodetype == Node.ANCHOR and edge.OS > maxOS:
                maxOS = edge.OS
                bestANode = outnode

        # If a read connects to at least one anchor node (bestANode exists)
        # Remove aonnections to all other anchor nodes
        # This must be done in 3 places:
        # - outEdges in other anchor nodes
        # - outEdges in the readnode
        # - crovledges (these are the same edges as in first two cases)
        if bestANode is not None:
            edgesTR = []
            for edge in rnode.outEdges:
                if edge.endNode.nodetype == Node.ANCHOR and edge.endNode != bestANode:
                    edgesTR.append(edge)
            for edge in edgesTR:
                rnode.outEdges.remove(edge)
                crovledges.remove(edge)
                edgesRemoved += 1

            for anode in anchornodes.itervalues():
                if anode != bestANode:
                    edgesTR = []
                    for edge in anode.outEdges:
                        if edge.endNode == rnode:
                            edgesTR.append(edge)
                    for edge in edgesTR:
                        anode.outEdges.remove(edge)
                        crovledges.remove(edge)
                        edgesRemoved += 1

    return edgesRemoved


# Returns info on the path
# Length in bases, number of nodes and names of starting and ending nodes
def calc_path_info(path):
    length = 0
    numNodes = len(path) + 1
    SIsum = 0
    SIavg = 0.0

    if not path:                    # If the path is empty
        return (0, 0, None, None)

    startNode = path[0].startNode
    endNode = path[-1].endNode

    direction = directionLEFT
    if path[0].ESleft < path[0].ESright:
        direction = directionRIGHT

    for edge in path:
        llength = 0
        SIsum += edge.SI
        if direction == directionRIGHT:
            llength = edge.SStart - edge.EStart
        else:
            llength = (edge.SLen - edge.SEnd) - (edge.ELen - edge.EEnd)

        if llength <= 0:
            sys.stderr.write('\nPYHERA: ERRROR calculating path length!')
            import pdb
            pdb.set_trace()
        length += llength
    
    length += path[-1].ELen
    SIavg = float(SIsum) / len(path)

    return (length, numNodes, startNode.name, endNode.name, direction, SIavg)


# Calculate and return reverse coomplement of a sequence
def revcomp(seq):
    rcseq = []

    for char in reversed(seq):
        if char.upper() in compbase.keys():
            rcchar = compbase[char.upper()]
        else:
            char = 'N'
    rcseq.append(char)

    return ''.join(rcseq)


# Reverses a path represented by a list of edges
# Reverses the order of edges and also each edge in the list
def reversed_path(path):
    reversed_path = []

    for edge in reversed(path):
        reversed_edge = edge.reversed()
        reversed_path.append(reversed_edge)

    return reversed_path


# Generates a fasta sequence for a path consisting of a list of edges
# All edges should extend the path in the same direction, either left or right
# NOTE: currently the script generates fasta sequences only for nodes extending to the right
# Each node can be anchor or read node
# NOTE: anchornodes and readnodes dictionaries are probably not necessary
#       edges have references to starting and ending nodes
def generate_fasta_for_path(path, anchornodes, readnodes):
    seq = []

    # Empty path - return empty sequence
    if len(path) == 0:
        return ''

    startNode = path[0].startNode
    seq.append(startNode.seq)
    direction = directionLEFT if path[0].ESleft > path[0].ESright else directionRIGHT
    strand = '+'

    for edge in path:
        direction2 = directionLEFT if edge.ESleft > edge.ESright else directionRIGHT
        strand2 = edge.Strand
        if direction2 != direction:
            sys.stderr.write('\nPYHERA ERROR: inconsistent direction in a path!')
        nextseq = edge.endNode.seq
        if strand2 == '-':          # If strand on the edge is "-", switch global strand
            strand = '-' if strand == '+' else '+'
        if strand == '-':                       # If global strand is '-', meaning different from the original strand
            nextseq = revcomp(nextseq)          # Work with the reverse complement of the sequence

        if direction == directionRIGHT:
            start = edge.EEnd +(edge.SLen-edge.SEnd) + 1
            seq.append(nextseq[start:])
        else:
            end = edge.EStart - edge.SStart 
            seq.insert(0, nextseq[:end])        # Since in this case we are extending to the left, adding to the beginning of the list

    return ''.join(seq)


# A function that receives a list of paths, each path is a list of edges
# The paths are grouped according to staring node and direction (or ending node),
# so that each group can be later processed separately
def group_paths(path_list, anchornodes):
    filtered_paths = []
    path_info_groups = []

    connected_anodes = {}
    path_info_list = []
    # 1. Collecting path info and calculating connected nodes
    for path in path_list:
        (length, numNodes, sname, ename, direction, SIavg) = calc_path_info(path)
        connected_anodes[sname] = anchornodes[sname]
        connected_anodes[ename] = anchornodes[ename]
        # path_info_list contains info on all paths, putting it also in reverse order (endnode, startnode)
        # So that I can use it to quickly determine best connections for each node in left and right direction
        # Last element of the tuple (index 5) say if the info i in reverse order compared to the path
        opposite_direction = directionLEFT if direction == directionRIGHT else directionRIGHT
        path_info_list.append((sname, ename, length, numNodes, direction, SIavg, path))
        path_info_list.append((ename, sname, length, numNodes, opposite_direction, SIavg, reversed_path(path)))

    if len(path_info_list) == 0:
        return path_info_groups, connected_anodes

    # 2. Group the paths according to starting node, ending node and direction
    path_info_list.sort(key=lambda pathinfo: pathinfo[1])               # sort path_info_list first cording to end node
    path_info_list.sort(key=lambda pathinfo: pathinfo[0])               # and then acording to start node
    (sname, ename, length, numNodes, direction, SIavg, path) = path_info_list[0]     # Data for the first path
    left_paths = right_paths = []
    if direction == directionLEFT:
        left_paths.append((sname, ename, length, numNodes, direction, SIavg, path))
    else:
        right_paths.append((sname, ename, length, numNodes, direction, SIavg, path))

    for (sname2, ename2, length2, numNodes2, direction2, SIavg2, path2) in path_info_list[1:]:
        if sname2 != sname or ename2 != ename:              # Start or end node has changed, have to wrap up the path group and start a new one
            if left_paths:
                path_info_groups.append(left_paths)
            elif right_paths:
                path_info_groups.append(right_paths)
            else:
                sys.stderr.write('\nPYHERA ERROR while processing paths: left and right groups are empty (%s)!' % sname)
            left_paths = []
            right_paths = []
            sname = sname2              # Numnodes, pathlength, SIavg and path are not used for grouping
            ename = ename2
            direction = direction2

        if direction2 == directionLEFT:
            left_paths.append((sname2, ename2, length2, numNodes2, direction2, SIavg2, path2))
        else:
            right_paths.append((sname2, ename2, length2, numNodes2, direction2, SIavg2, path2))

    # At the end, add the last group to the group list
    if left_paths:
        path_info_groups.append(left_paths)
    elif right_paths:
        path_info_groups.append(right_paths)
    else:
        sys.stderr.write('\nPYHERA ERROR while processing paths: left and right groups are empty (%s)!' % sname)

    # import pdb
    # pdb.set_trace()

    return path_info_groups, connected_anodes


# A function that filters paths
# Each anchoring node can have at most one path extending it to the left and at most one path
# extending it to the right. Only the best paths are preserved
# pathinfo: (sname, ename, length, numNodes, direction. SIavg, path)
# NOTE: pgroup[0] represents the first path in the group, all paths in the group should have the same
#       start node, end node and direction
def filter_path_groups(path_groups):
    temp_groups = []
    filtered_groups = []
    discarded_groups = []

    # 1. Since each path is entered twice, once for each direction, we can look only at path
    # extending in one direction - in this case direction RIGHT
    for pgroup in path_groups:
        if pgroup[0][4] == directionRIGHT:
            temp_groups.append(pgroup)
        else:
            discarded_groups.append(pgroup)

    # 2. Sort groups by group size, from larger to smaller
    # For each node retain only the largest group
    temp_groups.sort(key=lambda group: len(group), reverse=True)
    used_enodes = {}
    used_snodes = {}
    for pgroup in temp_groups:
        sname = pgroup[0][0]
        ename = pgroup[0][1]
        if sname not in used_snodes and ename not in used_enodes:
            filtered_groups.append(pgroup)
            used_snodes[sname] = 1
            used_enodes[ename] = 1
        else:
            discarded_groups.append(pgroup)

    return filtered_groups, discarded_groups


# A function that for each path group determines a representative paths
# If a group contains only paths of similar length, the path with greatest average SI is chosen
# If path length varies a lot, then path are split according to length into buckets of 1000 bases
# For the start, choosing a bucket with the most paths
# pathinfo: (sname, ename, length, numNodes, direction, SIavg, path)
def finalize_paths(filtered_groups, paths):
    final_paths = []
    STEP = 1000

    for fgroup in filtered_groups:
        buckets = []
        bucket = []
        fgroup.sort(key=lambda pathinfo: pathinfo[2])       # sort paths in a group according to length
        minlength = fgroup[0][2]
        bucket.append(fgroup[0])
        for pathinfo in fgroup[1:]:
            length = pathinfo[2]
            if length > minlength + STEP:
                buckets.append(bucket)
                bucket = []
                bucket.append(pathinfo)
                minlength = length
            else: 
                bucket.append(pathinfo)
        buckets.append(bucket)

        # Sort bucket according to size and choose a largest one
        # Then chose a best representative path from the top bucket
        buckets.sort(key=lambda bucket: len(bucket), reverse=True)
        bucket = buckets[0]
        bucket.sort(key=lambda pathinfo: pathinfo[5], reverse=True)           # Sort according to SIavg
        final_paths.append(bucket[0])

    return final_paths


# Generate fasta from final paths and write them to a file if specified
# Contings not used for scaffolds are written as is
# pathinfo: (sname, ename, length, numNodes, direction, SIavg, path)
def generate_fasta(final_paths, anchornodes, readnodes, filename = None):
    # Calculate anchor nodes used for scaffolding
    used_nodes = {}
    path_dict = {}
    for pathinfo in final_paths:
        sname = pathinfo[0]
        ename = pathinfo[1]
        path_dict[sname] = pathinfo
        used_nodes[sname] = 1
        used_nodes[ename] = 1

    # Combine linked paths
    # Example: If path1 connects node1 and node2, and path2 connects node2 and node3
    #          They are combined into a single path connectind node1 to node3 (via node2)
    leftmost_nodes = []
    right_nodes = {}
    for pathinfo in final_paths:
        ename = pathinfo[1]
        right_nodes[ename] = 1

    for node in used_nodes:
        if node not in right_nodes:
            leftmost_nodes.append(node)

    combined_paths = {}
    for node in leftmost_nodes:                     # For each leftmost anchor node (node that is not on the right end in any path)
        nodelist = []
        initial_pathinfo = path_dict[node]          # Get the initial path
        snode = initial_pathinfo[0]                 # Put start and end nodes in node list
        enode = initial_pathinfo[1]
        combined_path = initial_pathinfo[6]         # Create the initial combined path as a initial list of edges
        nodelist.append(snode)
        nodelist.append(enode)

        while (enode) in path_dict:                 # If the currend end node can be extended further
            next_pathinfo = path_dict[enode]
            snode = next_pathinfo[0]
            enode = next_pathinfo[1]
            nextpath = next_pathinfo[6]
            nodelist.append(enode)                  # Append the new end anchor node to the node list
            combined_path += nextpath[1:]           # Combine thenew path with the current combine path

        combined_paths[node] = (nodelist, combined_path)

    headers = []
    seqs = []
    # Generate headers and fasta sequences for each combined path
    i = 1
    for node, (nodelist, combined_path) in combined_paths.iteritems():
        header = 'Scaffold%04d %s' % (i, nodelist[0])
        seq = generate_fasta_for_path(combined_path, anchornodes, readnodes)
        for node2 in nodelist[1:]:
            header += ',%s' % node2

        headers.append(header)
        seqs.append(seq)
        i += 1

    # Add unused anchor nodes to the output
    for aname, anode in anchornodes.iteritems():
        if aname not in used_nodes:
            header = '%s' % aname
            seq = anode.seq
            headers.append(header)
            seqs.append(seq)

    # Testing if the generation is correct
    if len(headers) != len(seqs):
        sys.stderr.write('\nPYHERA ERROR: generating headers (%d) and sequences (%d)!' % (len(headeers), len(seqs)))

    # Writting output to a file
    if filename is not None:
        file = open(filename, 'w')
        for i in xrange(len(headers)):
            header = headers[i]
            seq = seqs[i]
            file.write('>%s\n%s\n' % (header, seq))
        file.close()

    return headers, seqs



def start_pyhera(contigs_file, reads_file, cr_overlaps_file, rr_overlaps_file, paramdict, output=True):

    reads_to_discard = {}

    if output:
        sys.stdout.write('\n[%s]PYHERA: Starting ...' % datetime.now().time().isoformat())
    ### Creating a graph
    # 1. Adding contigs as anchor nodes
    if output:
        sys.stdout.write('\n[%s]PYHERA: Loading contigs ...' % datetime.now().time().isoformat())
    anchornodes = load_anchornodes(contigs_file)

    # 2. Adding reads as read nodes
    if output:
        sys.stdout.write('\n[%s]PYHERA: Loading reads ...' % datetime.now().time().isoformat())
    readnodes = load_readnodes(reads_file)

    # 3. processing overlaps between contigs and reads
    # NOTE: for the overlaps file, we can not be sure whether query or target
    #       corresponds to reads or overlaps
    # NOTE: OVERLAPS NEED TO BE FITLERED!
    if output:
        sys.stdout.write('\n[%s]PYHERA: Loading contig/read overlaps ...' % datetime.now().time().isoformat())
    crovledges, isolated_anodes = load_cr_overlaps(cr_overlaps_file, anchornodes, readnodes, reads_to_discard)
    if output:
        sys.stdout.write('\nPYHERA: %d anchor nodes are isolated!' % len(isolated_anodes))

    # 4. processing overlaps between reads
    if output:
        sys.stdout.write('\n[%s]PYHERA: Loading read/read overlaps ...' % datetime.now().time().isoformat())

    numthreads = 1
    if '-t' in paramdict:
        numthreads = int(paramdict['-t'][0])
    if '--threads' in paramdict:
        numthreads = int(paramdict['--threads'][0])
    if numthreads == 1:
        rrovledges = load_rr_overlaps_ST(rr_overlaps_file, readnodes, reads_to_discard)
    else:
        rrovledges = load_rr_overlaps_MT(rr_overlaps_file, readnodes, reads_to_discard, numthreads)

    if output:
        sys.stdout.write('\nPYHERA before cleanup: ANODES: %d, RNODES: %d, CROVL: %d, RROVL: %d' % (len(anchornodes), len(readnodes), len(crovledges), len(rrovledges)))

    ### Cleaning up the graph
    if output:
        sys.stdout.write('\n[%s]PYHERA: Cleaning up the graph ...' % datetime.now().time().isoformat())
    edgesRemoved = graph_cleanup(anchornodes, readnodes, crovledges, rrovledges, reads_to_discard)

    if output:
        sys.stdout.write('\nPYHERA cleanup removed %d edges/ovelaps:' % edgesRemoved)
        sys.stdout.write('\nPYHERA after cleanup: ANODES: %d, RNODES: %d, CROVL: %d, RROVL: %d' % (len(anchornodes), len(readnodes), len(crovledges), len(rrovledges)))
    
    ### Calculating paths through the graph
    if output:
        sys.stdout.write('\n[%s]PYHERA: Calculating paths ...' % datetime.now().time().isoformat())
    # 1. Approach
    # For every anchor node consider all connecting read nodes
    # For further extension consider only the read with the highest OVERLAP score
    paths1 = getPaths_maxovl(anchornodes, readnodes, crovledges, rrovledges)
    if output:
        sys.stdout.write('\nPYHERA: Approach 1 returned %d paths!\n' % len(paths1))


    # 2. Approach
    # For every anchor node consider all connecting read nodes
    # For further extension consider only the read with the highest EXTENSION score
    paths2 = getPaths_maxext(anchornodes, readnodes, crovledges, rrovledges)
    if output:
        sys.stdout.write('\nPYHERA: Approach 2 returned %d paths!\n' % len(paths2))

    # 3. Approach
    # Monte Carlo method - randomly select reads for each extension
    # probability of selecting a read is proportional to extension score
    # This approach must generate more paths then first two approaches combined
    numMCpaths = 2*(len(paths1) + len(paths2) + 1)
    paths3 = getPaths_MC(anchornodes, readnodes, crovledges, rrovledges, numMCpaths)
    if output:
        sys.stdout.write('\nPYHERA: Approach 3 returned %d paths!\n' % len(paths3))

    paths = paths1 + paths2 + paths3

    ### Processing generated paths
    if output:
        sys.stdout.write('\n[%s]PYHERA: Processing paths ...' % datetime.now().time().isoformat())
        sys.stdout.write('\nPYHERA: Grouping paths ...\n')

    if len(paths) == 0:
        sys.stdout.write('\nPYHERA WARNING: No paths generated! Unable to proceed. Quiting ...\n')
        return
    path_info_groups, connected_anodes = group_paths(paths, anchornodes)

    # Determine initial connected nodes
    for aname, anode in anchornodes.iteritems():
        if aname not in connected_anodes:
            isolated_anodes[aname] = anode

    if output:
        sys.stdout.write('\nPYHERA: Isolated anchor nodes (%d) : ' % len(isolated_anodes))
        # for aname in sorted(isolated_anodes.keys()):
        #     sys.stdout.write(' %s,' % aname)
        sys.stdout.write('\nPYHERA: Connected anchor nodes (%d) : ' % len(connected_anodes))
        # for aname in sorted(connected_anodes):
        #     sys.stdout.write(' %s,' % aname)


    if output:
        sys.stdout.write('\n\nPYHERA: Path group info: SNODE, ENODE, DIRECTION, NUMPATHS')
        for pinfo_group in path_info_groups:
            (sname, ename, length, numNodes, direction, SIavg, path) = pinfo_group[0]
            sdirection = 'LEFT' if direction == directionLEFT else 'RIGHT'
            sys.stdout.write('\nPYHERA: %s %s %s %d' % (sname, ename, sdirection, len(pinfo_group)))

    if output:
        sys.stdout.write('\n\nPYHERA: Filtering path groups ...\n')

    filtered_groups, discarded_groups = filter_path_groups(path_info_groups)

    if output:
        sys.stdout.write('\nPYHERA: Discarded groups: SNODE, ENODE, DIRECTION, NUMPATHS')
        for pinfo_group in discarded_groups:
            (sname, ename, length, numNodes, direction, SIavg, path) = pinfo_group[0]
            sdirection = 'LEFT' if direction == directionLEFT else 'RIGHT'
            sys.stdout.write('\nPYHERA: %s %s %s %d' % (sname, ename, sdirection, len(pinfo_group)))

        sys.stdout.write('\n\nPYHERA: Remaining groups: SNODE, ENODE, DIRECTION, NUMPATHS')
        for pinfo_group in filtered_groups:
            (sname, ename, length, numNodes, direction, SIavg, path) = pinfo_group[0]
            sdirection = 'LEFT' if direction == directionLEFT else 'RIGHT'
            sys.stdout.write('\nPYHERA: %s %s %s %d' % (sname, ename, sdirection, len(pinfo_group)))


    if output:
        sys.stdout.write('\n\nPYHERA: Final path filtering ...\n')

    final_paths = finalize_paths(filtered_groups, paths)

    # pathinfo: (sname, ename, length, numNodes, direction, SIavg, path)
    if output:
        sys.stdout.write('\nPYHERA FINAL PATHS: SNODE, ENODE, LENGTH, NUMNODES, DIRECTION, SIAVG')
        for (sname, ename, length, numNodes, direction, SIavg, path) in final_paths:
            sdirection = 'LEFT' if direction == directionLEFT else 'RIGHT'
            sys.stdout.write('\nPYHERA: %s %s %d %d %s %f' % (sname, ename, length, numNodes, sdirection, SIavg))

    if output:
        sys.stdout.write('\n\n[%s]PYHERA: Generating FASTA ...' % datetime.now().time().isoformat())
    out_filename = 'scaffolds.fasta'
    if '-o' in paramdict:
        out_filename = paramdict['-o'][0]
    elif '--output' in paramdict:
        out_filename = paramdict['--output'][0]
    headers, seqs = generate_fasta(final_paths, anchornodes, readnodes, filename = out_filename)

    if output:
        sys.stdout.write('\nPYHERA: FASTA sequences generated: %d' % len(headers))
        # for header in headers:
        #     sys.stdout.write('\n%s' % header)

    # import pdb
    # pdb.set_trace()

    sys.stderr.write('\n\n[%s]SCAFFOLDIND with HERA DONE!\n' % datetime.now().time().isoformat())


def load_fast(reads_file, output = True):

    filename, file_extension = os.path.splitext(reads_file)
    ftype = ''

    if file_extension.upper() in ('.FA', '.FNA', '.FASTA'):
        ftype = 'FASTA'
    elif file_extension.upper() in ('.FQ', '.FASTQ'):
        ftype = 'FASTQ'
    else:
        sys.stderr.write('\nERROR: Invalid file extension: %s' % reads_file)
        return

    [headers, seqs, quals] = read_fastq(reads_file)
    if output == True:
        sys.stdout.write('\n%s | File type: %s' % (reads_file, ftype))
        sys.stdout.write('\nNumber of enteries: %d\n' % len(seqs))

    return [headers, seqs, quals]



def load_paf(paf_file, output = True):
    filename, file_extension = os.path.splitext(paf_file)
    ftype = ''

    if file_extension.upper() in ('.PAF'):
        ftype = 'PAF'
    else:
        sys.stderr.write('\nERROR: Invalid file extension: %s' % paf_file)
        return

    paf_lines = PAFutils.load_paf(paf_file)

    if output == True:
        sys.stdout.write('\n%s | File type: %s' % (paf_file, ftype))
        sys.stdout.write('\nNumber of enteries: %d\n' % len(paf_lines))

    return paf_lines


def verbose_usage_and_exit():
    sys.stderr.write('pyhera - a scaffolding tool in python.\n')
    sys.stderr.write('\n')
    sys.stderr.write('Usage:\n')
    sys.stderr.write('\t%s [mode]\n' % sys.argv[0])
    sys.stderr.write('\n')
    sys.stderr.write('\tmode:\n')
    sys.stderr.write('\t\tscaffold\n')
    sys.stderr.write('\t\tload_fast\n')
    sys.stderr.write('\t\tload_paf\n')
    sys.stderr.write('\n')
    exit(0)

if __name__ == '__main__':
    if (len(sys.argv) < 2):
        verbose_usage_and_exit()

    mode = sys.argv[1]

    if (mode == 'scaffold'):
        if (len(sys.argv) < 6):
            sys.stderr.write('Scaffold given contigs with given reads and their overlaps.\n')
            sys.stderr.write('Usage:\n')
            sys.stderr.write('%s %s <contigs FASTA> <reads FASTA> <reads-contigs overlaps PAF> <reads-reads overlaps PAF> options\n' % (sys.argv[0], sys.argv[1]))
            sys.stderr.write('options:"\n')
            sys.stderr.write('-o (--output) <file> : output file to which the report will be written\n')
            sys.stderr.write('\n')
            exit(1)

        contigs_file = sys.argv[2]
        reads_file = sys.argv[3]
        cr_overlaps_file = sys.argv[4]
        rr_overlaps_file = sys.argv[5]

        pparser = paramsparser.Parser(paramdefs)
        paramdict = pparser.parseCmdArgs(sys.argv[6:])
        paramdict['command'] = ' '.join(sys.argv)

        start_pyhera(contigs_file, reads_file, cr_overlaps_file, rr_overlaps_file, paramdict)

    elif (mode == 'load_fast'):
        if (len(sys.argv) != 3):
            sys.stderr.write('Load FASTA / FASTQ file with reads.\n')
            sys.stderr.write('Usage:\n')
            sys.stderr.write('%s %s <reads FASTA>\n' % (sys.argv[0], sys.argv[1]))
            sys.stderr.write('\n')
            exit(1)

        reads_file = sys.argv[2]
        load_fast(reads_file)

    elif (mode == 'load_paf'):
        if (len(sys.argv) != 3):
            sys.stderr.write('Load PAF file with overlaps.\n')
            sys.stderr.write('Usage:\n')
            sys.stderr.write('%s %s <overlaps PAF>\n' % (sys.argv[0], sys.argv[1]))
            sys.stderr.write('\n')
            exit(1)

        overlaps_file = sys.argv[2]
        load_paf(overlaps_file)

    else:
        print 'Invalid mode!'