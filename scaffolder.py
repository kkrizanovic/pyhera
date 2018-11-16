#! /usr/bin/python

import sys, os
import commands
import time
from datetime import datetime

import paramsparser

# Parameter definitions for paramparser
paramdefs = {'--version' : 0,
             '-v' : 0,
             '-p' : 1
             '--plan' : 1,
             '-r' : 1,
             '--results' : 1}

# A default scaffolding plan, run Pyhera once and then Ezra three times
# NOTE: A plan is a series 
default_plan = '1P3E'

# Placeholders for default options for running PyHera and Ezra
default_PHoptions = ''
default_Eoptions = ''

# Setting run names for Pyhera, Ezra, Minimap2 and Python
SCRIPT_PATH = os.path.dirname(os.path.realpath(__file__))
PYHERA = os.path.join(SCRIPT_PATH, 'pyhera.py')
MINIMAP2 = os.path.join(SCRIPT_PATH, 'minimap2', 'minimap2')
EZRA = os.path.join(SCRIPT_PATH, 'ezra', 'build', 'ezra')
PYTHON = 'python'


def print_version():
	sys.stdout.write('\nCombined scaffolding script, version 1.0');


def check_tools():
	if not os.path.exists(SCRIPT_PATH):
		sys.stderr.write('\nChecking tools: folder %s does not exist!' % SCRIPT_PATH)
		return False
	elif not os.path.exists(PYHERA):
		sys.stderr.write('\nChecking tools: Pyhera script (%s) does not exist!' % PYHERA)
		return False
	elif not os.path.exists(MINIMAP2):
		sys.stderr.write('\nChecking tools: Minmap2 executable (%s) does not exist!' % MINIMAP2)
		return False
	elif not os.path.exists(EZRA):
		sys.stderr.write('\nChecking tools: Ezra executable (%s) does not exist!' % EZRA)
		return False

	(status, output) = commands.getstatusoutput(PYTHON)
	if not output.startswith('Python 2.7'):
		PYTHON = 'python2'
		(status, output) = commands.getstatusoutput(PYTHON)
		if not output.startswith('Python 2.7'):
			sys.stderr.write('\nThis script requires python 2.7 to run! Cannot find appropriate python!')
			return False

	return True



def run_pyhera(contigsfile, readsfile, resultfile, c2r_ovl_file = None, r2r_ovl_file = None, PHoptions = default_PHoptions):
	pass



def run_ezra(runfolder, resultfile, contigsfile = None, readsfile=None, c2r_ovl_file = None, Eoptions = default_Eoptions):
	pass



def scaffold_with_plan(contigsfile, readsfile, paramdict, resultsfolder = None, plan = default_plan):

	if resultsfolder is None:
		runfolder = os.getcwd()
		resultsfolder = os.path.join(runfolder, 'scaffolding_results')
		if not os.path.exists(resultsfolder):
			os.mkdir(resultsfolder)

	pass




def scaffolding_script(contigsfile, readsfile, paramdict):

	if check_tools() == False:
		return False
	
	scaffolding_plan = default_plan
	if '-p' in paramdict:
		scaffolding_plan = paramdict['-p']
	elif '--plan' in paramdict:
		scaffolding_plan = paramdict['--plan']

	resultsfolder = None
	if '-r' in paramdict:
		resultsfolder = paramdict['-r']
	elif '--results' in paramdict:
		resultsfolder = paramdict['--results']


	scaffold_with_plan(contigs_file, reads_file, paramdict, scaffolding_plan)

	return True



def verbose_usage_and_exit():
    sys.stderr.write('scaffolder - scaffold combining PYHERA and EZRA algorithms.\n')
    sys.stderr.write('\n')
    sys.stderr.write('Usage:\n')
    sys.stderr.write('\t%s [contigs file] [reads file] options\n' % sys.argv[0])
    sys.stderr.write('options:"\n')
    sys.stderr.write('-o (--output) <file> : output file to which the report will be written\n')
    sys.stderr.write('\n')
    exit(0)

if __name__ == '__main__':
    if (len(sys.argv) < 3):
    	if '-v' in paramdict or '--version' in paramdict:
    		print_version()
        verbose_usage_and_exit()

    contigs_file = sys.argv[1]
    reads_file = sys.argv[2]

    pparser = paramsparser.Parser(paramdefs)
    paramdict = pparser.parseCmdArgs(sys.argv[3:])
    paramdict['command'] = ' '.join(sys.argv)

    scaffolding_script(reads_file, contigs_file, paramdict)