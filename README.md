# Scaffolding with pyhera
This repository contains python scripts and binaries comprising our tools for genome scaffolding.

The  tools are currently under development and any feedback on them is very welcome and will be greatly appreciated.

## Tools
### PyHera
PyHera is a python implementation of HERA scaffolder.
The paper on the HERA is available at bioRchiv: https://www.biorxiv.org/content/early/2018/06/13/345983.

### Ezra
Ezra is a result of a graduation thesis work done by Ivan Krpelnik on University of Zareb Faculty of Electrical Engineering and Computing. This thesis is available here: http://complex.zesoi.fer.hr/data/pdf/Ivan_Krpelnik_diplomski.pdf.

Ezra is included as a submodule, with main repository at: https://gitlab.com/Krpa/ezra.

### Scaffolding script
Scaffolding script combines PYHera and Ezra, according to a given scaffolding plan, to iteratively perform the scaffolding, using output of the previous iteration as input for the next one. THe script will use Minimap2 to produce overlaps needed for the scaffolding.

## Installation

  1. Clone the repository, and include all submodules.
  
    git clone --recursive https://github.com/kkrizanovic/pyhera.git
  
  __Note:__ if you omitted `<--recursive>` from `<git clone>`, run `<git submodule update --init --recursive>` before proceeding.
  
  2. Build Ezra
  
    cd Ezra
    mkdir build
    cd build
    cmake ..
    make

  3. Build Minimap2
  
    cd Minimap2
    make

  Pythons scripts, such as PyHery, Scaffolder script and samscripts tool do not need to be installed.

### Dependencies
Python scripts require PYthon2.7. Ezra requires CMake 3.5.

## Running the scripts


