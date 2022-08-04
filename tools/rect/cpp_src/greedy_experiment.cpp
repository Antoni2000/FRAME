#include <iostream>
#include <fstream>
#include <vector>
#include <sys/time.h>
#include <iomanip>
#include "boxfinder_cubic.cpp"
#include "boxfinder_slicing.cpp"
#include "boxfinder_complete.cpp"

#define MIN_AREA 0
#define MIN_ERROR 1

#define print_box(b) b.x1 << " " << b.y1 << " " << b.x2 << " " << b.y2 << std::endl

unsigned char METHOD = MIN_ERROR;

int nboxes;
double w, h, proportion;
std::vector<cubic::box>    cubic_inputProblem;
std::vector<cubic::box>    cubic_allBoxes;
std::vector<slicing::box>  slicing_inputProblem;
std::vector<slicing::box>  slicing_allBoxes;
std::vector<complete::box> complete_inputProblem;
std::vector<complete::box> complete_allBoxes;


void readFile(const char * filename){
	std::ifstream indata;
	indata.open(filename);
	if(!indata) {
		std::cerr << "Error: File " << filename << " could not be opened!" << std::endl;
		exit(-2);
	}
	
	indata >> w >> h >> nboxes >> proportion;
	if(proportion < 1) METHOD == MIN_AREA;
	cubic_inputProblem    = std::vector<   cubic::box>( nboxes, (   cubic::box) { 0.0, 0.0, 0.0, 0.0, 0.0 } );
	slicing_inputProblem  = std::vector< slicing::box>( nboxes, ( slicing::box) { 0.0, 0.0, 0.0, 0.0, 0.0 } );
	complete_inputProblem = std::vector<complete::box>( nboxes, (complete::box) { 0.0, 0.0, 0.0, 0.0, 0.0 } );
	for(int i = 0; i < nboxes; ++i){
		indata >> cubic_inputProblem[i].x1 >> cubic_inputProblem[i].y1 >> cubic_inputProblem[i].x2 >> cubic_inputProblem[i].y2 >> cubic_inputProblem[i].p;
		slicing_inputProblem[i].x1 = cubic_inputProblem[i].x1;
		slicing_inputProblem[i].x2 = cubic_inputProblem[i].x2;
		slicing_inputProblem[i].y1 = cubic_inputProblem[i].y1;
		slicing_inputProblem[i].y2 = cubic_inputProblem[i].y2;
		slicing_inputProblem[i].p  = cubic_inputProblem[i].p;
		complete_inputProblem[i].x1 = cubic_inputProblem[i].x1;
		complete_inputProblem[i].x2 = cubic_inputProblem[i].x2;
		complete_inputProblem[i].y1 = cubic_inputProblem[i].y1;
		complete_inputProblem[i].y2 = cubic_inputProblem[i].y2;
		complete_inputProblem[i].p  = cubic_inputProblem[i].p;
	}
	
	indata.close();
}


void usage(const char * appname){
	std::cerr << "Usage: " << appname << " [inputfile]\n";
	exit(-1);
}


double elapsed(struct timeval & t0, struct timeval & t1){
	long seconds = t1.tv_sec - t0.tv_sec;
    long microseconds = t1.tv_usec - t0.tv_usec;
    double elapsed = seconds + microseconds * 1e-6;
}

int main(int argc, char * argv[]){
	if(argc != 2){
		usage(argv[0]);
	}
	readFile(argv[1]);
	
	struct timeval cub0, cub1, sli0, sli1, com0, com1;
	
	cubic_allBoxes = std::vector<cubic::box>(0);
	gettimeofday(&cub0, 0);
	cubic::all_rectangles(cubic_inputProblem, cubic_allBoxes);
	gettimeofday(&cub1, 0);
	
	slicing_allBoxes = std::vector<slicing::box>(0);
	gettimeofday(&sli0, 0);
	slicing::all_rectangles(slicing_inputProblem, slicing_allBoxes);
	gettimeofday(&sli1, 0);
	
	complete_allBoxes = std::vector<complete::box>(0);
	gettimeofday(&com0, 0);
	complete::all_rectangles(complete_inputProblem, complete_allBoxes);
	gettimeofday(&com1, 0);
	
	std::cout << std::fixed << std::setprecision(20) << elapsed(cub0, cub1) << " " << elapsed(sli0, sli1) << " " << elapsed(com0, com1) << '\n';
}