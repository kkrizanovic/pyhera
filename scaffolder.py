#! /usr/bin/python

import sys, os
import commands
import time
import re
import shutil
from datetime import datetime

import paramsparser

# Parameter definitions for paramparser
paramdefs = {'--version' : 0,
             '-v' : 0,
             '-p' : 1,
             '--plan' : 1,
             '-r' : 1,
             '--results' : 1}

# A default scaffolding plan, run Pyhera once and then Ezra three times
default_plan = 'P1E3'

# Placeholders for default options for running PyHera and Ezra
default_PHoptions = ''
default_Eoptions = ''
default_MM2options = '-x ava-pb --dual=yes'

# Setting run names for Pyhera, Ezra, Minimap2 and Python
SCRIPT_PATH = os.path.dirname(os.path.realpath(__file__))
PYHERA = os.path.join(SCRIPT_PATH, 'pyhera.py')
MINIMAP2 = os.path.join(SCRIPT_PATH, 'minimap2', 'minimap2')
EZRA = os.path.join(SCRIPT_PATH, 'ezra', 'build', 'ezra')
PYTHON = 'python'


def print_version():
	sys.stdout.write('\nCombined scaffolding script, version 1.0');


def check_tools():
	global SCRIPT_PATH, PYHERA, MINIMAP2, EZRA, PYTHON
	if not os.path.exists(SCRIPT_PATH):
		sys.stderr.write('\nChecking tools: folder %s does not exist!\n' % SCRIPT_PATH)
		return False
	elif not os.path.exists(PYHERA):
		sys.stderr.write('\nChecking tools: Pyhera script (%s) does not exist!\n' % PYHERA)
		return False
	elif not os.path.exists(MINIMAP2):
		sys.stderr.write('\nChecking tools: Minmap2 executable (%s) does not exist!\n' % MINIMAP2)
		return False
	elif not os.path.exists(EZRA):
		sys.stderr.write('\nChecking tools: Ezra executable (%s) does not exist!\n' % EZRA)
		return False

	(status, output) = commands.getstatusoutput(PYTHON + ' --verion')
	if not output.startswith('Python 2.7'):
		PYTHON = 'python2'
		(status, output) = commands.getstatusoutput(PYTHON + ' --version')
		if not output.startswith('Python 2.7'):
			sys.stderr.write('\nThis script requires python 2.7 to run! Cannot find appropriate python!\n')
			return False

	return True



# TODO:
def run_pyhera(contigsfile, readsfile, resultfile, c2r_ovl_file = None, r2r_ovl_file = None, PHoptions = default_PHoptions):
	pass


# TODO:
def run_ezra(runfolder, resultfile, contigsfile = None, readsfile=None, c2r_ovl_file = None, Eoptions = default_Eoptions):
	pass



def scaffold_with_plan(contigsfile, readsfile, paramdict, resultsfolder = None, plan = default_plan):

	global SCRIPT_PATH, PYHERA, MINIMAP2, EZRA, PYTHON

	allowed_ops= ['E', 'P']
	max_cnt = 9
	pattern = '(.)(\d+)'
	operations = re.findall(pattern, plan)
	pyhera = False
	# Checking if the plan is correct
	for op in operations:
		sop = op[0]
		cnt = int(op[1])
		if sop not in allowed_ops:
			sys.stderr.write('\nERROR: Invalid operation in scaffolding plan: %s (%s)' % (sop, plan))
			return False
		if cnt < 1 or cnt > max_cnt:
			sys.stderr.write('\nERROR: Invalid operation count in scaffolding plan: %d (%s)' % (cnt, plan))
			return False
		if sop == 'P':
			pyhera = True

	sys.stderr.write('\nSTARTING SCAFFOLDING SCRIPT WITH PLAN: %s' % plan)

	# Create the results folder
	runfolder = os.getcwd()
	if resultsfolder is None:		
		resultsfolder = 'scaffolding_results'
	resultsfolder_path = os.path.join(runfolder, resultsfolder)

	if not os.path.exists(resultsfolder_path):
		os.mkdir(resultsfolder_path)
	else:
		sys.stderr.write('\nResults folder found: %s' % resultsfolder_path)

	# If running pyhera, create reads to reads overlaps using Minimap2
	reads2reads_file = os.path.join(resultsfolder, 'reads2reads_ovl.paf')
	if pyhera:
		if os.path.exists(reads2reads_file):
			sys.stderr.write('\nRead overlaps for PyHera found: %s' % reads2reads_file)
		else:
			cmd = '%s %s %s %s > %s' % (MINIMAP2, default_MM2options, readsfile, readsfile, reads2reads_file)
			sys.stderr.write('\nRUNNING COMMAND: %s' % cmd)
			(status, output) = commands.getstatusoutput(cmd)
			logfile = os.path.join(resultsfolder_path, 'Minimap2_r2r.log')
			with open(logfile, 'w') as lfile:
				lfile.write(output)

	# Executing the plan
	temp_contigs_file = contigs_file
	iteration = 1
	for op in operations:
		sop = op[0]
		cnt = int(op[1])
		for i in xrange(cnt):
			# 1. Create results subfolder
			scaffolder = 'PyHera' if sop == 'P' else 'Ezra'
			sys.stderr.write('\nScaffolding iteration %d using %s' % (iteration, scaffolder))
			results_subfolder = os.path.join(resultsfolder_path, 'iter%0d' % iteration)
			if not os.path.exists(results_subfolder):
				os.mkdir(results_subfolder)
			else:
				sys.stderr.write('\nResults subfolder found: %s' % results_subfolder)
			# Running ezra
			if sop == 'E':
				# 2E copy reads and contigs to results subfolder
				resultfile = os.path.join(results_subfolder, 'scaffolds_iter%0d.fasta' % iteration)
				new_contigs = os.path.join(results_subfolder, 'contigs.fasta')
				reads_fname, reads_fext = os.path.splitext(readsfile)
				if reads_fext.upper() == '.FASTQ' or reads_fext.upper() == '.FQ':
					new_reads = os.path.join(results_subfolder, 'reads.fastq')
				else:
					new_reads = os.path.join(results_subfolder, 'reads.fasta')
					
				reads2contigs_file = os.path.join(results_subfolder, 'readsToContigs.paf')

				if os.path.exists(new_contigs):
					sys.stderr.write('\nContigs for Ezra found: %s' % new_contigs)
				else:
					shutil.copy(temp_contigs_file, new_contigs)

				if os.path.exists(new_reads):
					sys.stderr.write('\nReads for Ezra found: %s' % new_reads)
				else:
					shutil.copy(readsfile, new_reads)

				# 2.1E Run Minimap2 to generate overlaps
				# NOTE: include minimap options in here
				if os.path.exists(reads2contigs_file):
					sys.stderr.write('\nContig-reads ovelaps for Ezra found: %s' % reads2contigs_file)
				else:
					cmd = '%s %s %s %s > %s' % (MINIMAP2, default_MM2options, new_contigs, new_reads, reads2contigs_file)
					sys.stderr.write('\nRUNNING COMMAND: %s' % cmd)
					(status, output) = commands.getstatusoutput(cmd)
					logfile = os.path.join(results_subfolder, 'Minimap2_r2c.log')
					with open(logfile, 'w') as lfile:
						lfile.write(output)


				#3E Run Ezra scaffolding
				if os.path.exists(resultfile):
					sys.stderr.write('\nResults for Ezra found: %s' % resultfile)
				else:
					# Need to add '/' to Ezra run folder
					# TODO: include this into run_ezra function
					cmd = '%s %s > %s' % (EZRA, results_subfolder + '/', resultfile)
					sys.stderr.write('\nRUNNING COMMAND: %s' % cmd)
					(status, output) = commands.getstatusoutput(cmd)
					logfile = os.path.join(results_subfolder, 'Ezra_i%0d.log' % iteration)
					with open(logfile, 'w') as lfile:
						lfile.write(output)
				
				#4E Prepare for the next iteration
				temp_contigs_file = resultfile
				iteration += 1

			elif sop == 'P':
				resultfile = os.path.join(results_subfolder, 'scaffolds_iter%0d.fasta' % iteration)
				reads2contigs_file = os.path.join(results_subfolder, 'reads2contigs.paf')

				# 2P Run Minimap2 to generate overlaps between contigs and reads
				# NOTE: include minimap options in here
				if os.path.exists(reads2contigs_file):
					sys.stderr.write('\nContig-reads ovelaps for PyHera found: %s' % reads2contigs_file)
				else:
					cmd = '%s %s %s %s > %s' % (MINIMAP2, default_MM2options, temp_contigs_file, readsfile, reads2contigs_file)
					sys.stderr.write('\nRUNNING COMMAND: %s' % cmd)
					(status, output) = commands.getstatusoutput(cmd)
					logfile = os.path.join(results_subfolder, 'Minimap2_r2c.log')
					with open(logfile, 'w') as lfile:
						lfile.write(output)

				# 3P Run Pyhera scaffolding
				if os.path.exists(resultfile):
					sys.stderr.write('\nResults for PyHera found: %s' % resultfile)
				else:
					cmd = '%s %s scaffold %s %s %s %s -o %s' % (PYTHON, PYHERA, temp_contigs_file, readsfile, reads2contigs_file, reads2reads_file, resultfile)
					sys.stderr.write('\nRUNNING COMMAND: %s' % cmd)
					(status, output) = commands.getstatusoutput(cmd)
					logfile = os.path.join(results_subfolder, 'PyHera_i%0d.log' % iteration)
					with open(logfile, 'w') as lfile:
						lfile.write(output)

				#4P Prepare for the next iteration
				temp_contigs_file = resultfile
				iteration += 1

	return True



def scaffolding_script(contigsfile, readsfile, paramdict):

	if check_tools() == False:
		return False
	
	scaffolding_plan = default_plan
	if '-p' in paramdict:
		scaffolding_plan = paramdict['-p'][0]
	elif '--plan' in paramdict:
		scaffolding_plan = paramdict['--plan'][0]

	resultsfolder = None
	if '-r' in paramdict:
		resultsfolder = paramdict['-r'][0]
	elif '--results' in paramdict:
		resultsfolder = paramdict['--results'][0]


	scaffold_with_plan(contigs_file, reads_file, paramdict, resultsfolder, scaffolding_plan)

	return True



def verbose_usage_and_exit():
    sys.stderr.write('scaffolder - scaffold combining PYHERA and EZRA algorithms.\n')
    sys.stderr.write('\n')
    sys.stderr.write('Usage:\n')
    sys.stderr.write('\t%s [contigs file] [reads file] options\n' % sys.argv[0])
    sys.stderr.write('options:"\n')
    sys.stderr.write('-r (--results) <folder> : output folder, it will be created if it does not exist\n')
    sys.stderr.write('-p (--plan) <plan> : Execution plan for the dcaffolding script (default: 1P3E)\n')
    sys.stderr.write('\n')
    exit(0)

if __name__ == '__main__':
    if (len(sys.argv) < 3):
    	pparser = paramsparser.Parser(paramdefs)
    	paramdict = pparser.parseCmdArgs(sys.argv[1:])
    	if '-v' in paramdict or '--version' in paramdict:
    		print_version()
        verbose_usage_and_exit()

    contigs_file = sys.argv[1]
    reads_file = sys.argv[2]

    pparser = paramsparser.Parser(paramdefs)
    paramdict = pparser.parseCmdArgs(sys.argv[3:])
    paramdict['command'] = ' '.join(sys.argv)

    scaffolding_script(reads_file, contigs_file, paramdict)