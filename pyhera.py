#! /usr/bin/python

import paramsparser


def start_pyhera(contigs_file, reads_file, overlaps_file):
	pass


def verbose_usage_and_exit():
    sys.stderr.write('pyhera - a scaffolding tool in python.\n')
    sys.stderr.write('\n')
    sys.stderr.write('Usage:\n')
    sys.stderr.write('\t%s [mode]\n' % sys.argv[0])
    sys.stderr.write('\n')
    sys.stderr.write('\tmode:\n')
    sys.stderr.write('\t\tscaffold\n')
    sys.stderr.write('\n')
    exit(0)

if __name__ == '__main__':
    if (len(sys.argv) < 2):
        verbose_usage_and_exit()

    mode = sys.argv[1]

    if (mode == 'scaffold'):
        if (len(sys.argv) < 5):
            sys.stderr.write('Setup the folder structures and install necessary tools.\n')
            sys.stderr.write('Usage:\n')
            sys.stderr.write('%s %s <contigs FASTA> <reads FASTA> <overlaps PAF> options\n' % (sys.argv[0], sys.argv[1]))
            sys.stderr.write('options:"\n')
            sys.stderr.write('-o (--output) <file> : output file to which the report will be written\n')
            sys.stderr.write('\n')

            contigs_file = sys.argv[2]
            reads_file = sys.argv[3]
            overlaps_file = sys.argv[4]

			start_pyhera(contigs_file, reads_file, overlaps_file)        

    else:
        print 'Invalid mode!'