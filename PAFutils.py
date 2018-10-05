#! /usr/bin/python

###################################################################
### PAF file structure
# 1. QNAME:     Query name
# 2. QLEN:      Query length
# 3. QSTART:    Query start (0-based)
# 4. QEND:      Query end (0-based)
# 5. STRAND:    Relative strand '+' or '-'
# 6. TNAME:     Target name
# 7. TLEN:      Target length
# 8. TSTART:    Target start on original strand (0-based)
# 9. TEND:      Target end on original strand (0-based)
# 10. TRM:      Number of residue matches
# 11. ABL:      Alignment block length
# 12. MQUAL:    Mapping quality (0-255; 255 for missing)


# OPTIONAL:
# SAM-like key-value pairs

# If PAF is generated from an alignment, column 10 equals the number of sequence matches, 
# and column 11 equals the total number of sequence matches, mismatches, insertions and 
# deletions in the alignment. If alignment is not available, column 10 and 11 are still
# required but may be highly inaccurate.

###################################################################

# Reads a PAF file and return mappings as PAF lines
# Last e
def load_paf(paf_file):
    
    paf_lines = []
    attributes = {}

    with open(paf_file, 'rU') as pfile:
        for line in pfile:
            # Ignoring header lines (copied from GTF)
            if line.startswith('#') or line.startswith('track') or line.startswith('browser'):
                pass
            else:
                elements = line.split('\t')    # splitting with tab as delimitters
                elcount = len(elements)

                pafline = {}
                attributes = {}

                pafline['QNAME'] = elements[0]
                pafline['QLEN'] = int(elements[1])
                pafline['QSTART'] = int(elements[2])
                pafline['QEND'] = int(elements[3])
                pafline['STRAND'] = elements[4]
                pafline['TNAME'] = elements[5]
                pafline['TLEN'] = int(elements[6])
                pafline['TSTART'] = int(elements[7])
                pafline['TEND'] = int(elements[8])
                pafline['NRM'] = int(elements[9])
                pafline['ABL'] = int(elements[10])
                pafline['MQUAL'] = int(elements[11])

                if elcount > 12:
                    for i in range(12, elcount):
                        element = elements[i]
                        att_list = element.split(':')
                        attributes['TAG'] = att_list[0]
                        attributes['TYPE'] = att_list[1]
                        attributes['VALUE'] = att_list[2]
                pafline['ATTRIB'] = attributes

            paf_lines.append(pafline)

        pfile.close()

    return paf_lines


    