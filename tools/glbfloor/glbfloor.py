"""
glbfloor tool. See README.md for more information

This file contains the code to parse the command line arguments and the main function of the tool
"""

import argparse
from time import time
from typing import Any

from frame.die.die import Die
from frame.netlist.netlist import Netlist

from tools.glbfloor.optimization import glbfloor


def parse_options(prog: str | None = None, args: list[str] | None = None) -> dict[str, Any]:
    """
    Parse the command-line arguments for the tool
    :param prog: tool name
    :param args: command-line arguments
    :return: a dictionary with the arguments
    """
    parser = argparse.ArgumentParser(prog=prog)  # TODO: write description
    parser.add_argument("--netlist", required=True,
                        help="input netlist filename")
    parser.add_argument("-d", "--die", metavar="<WIDTH>x<HEIGHT> or FILENAME", required=True,
                        help="size of the die (width x height) or name of the file")
    parser.add_argument("-g", "--grid", metavar="<ROWS>x<COLS>",
                        help="size of the initial grid (rows x columns) "
                             "(only supported if there are no fixed modules nor blockages, "
                             "and incompatible with --aspect-ratio and --num-rectangles)")
    parser.add_argument("-r", "--aspect-ratio", type=float)  # TODO: write help
    parser.add_argument("-n", "--num-rectangles", type=int)  # TODO: write help
    parser.add_argument("-a", "--alpha", type=float, required=True,
                        help="tradeoff hyperparameter between 0 and 1 to control the balance between dispersion and "
                             "wire length. Smaller values will reduce the dispersion and increase the wire length, and "
                             "greater ones the other way around")
    parser.add_argument("-t", "--threshold", type=float, default=0.95,
                        help="threshold hyperparameter between 0 and 1 to decide if allocations must be refined. "
                             "Allocations with a greater occupancy will not be further refined")
    parser.add_argument("-i", "--max-iter", type=int,
                        help="maximum number of optimizations performed (if not present, until no more refinements can "
                             "be performed)")
    parser.add_argument("-p", "--plot",
                        help="plot name (if not present, no plots are produced)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="print the optimization logs and additional information")
    parser.add_argument("--visualize", action="store_true",
                        help="produce animations to visualize the optimizations (might take a long time to execute)")
    parser.add_argument("--out-netlist",
                        help="output netlist file (if not present, no file is produced)")
    parser.add_argument("--out-allocation",
                        help="output allocation file (if not present, no file is produced)")
    return vars(parser.parse_args(args))


def main(prog: str | None = None, args: list[str] | None = None):
    """Main function."""

    options = parse_options(prog, args)

    netlist = Netlist(options["netlist"])
    die = Die(options["die"], netlist)

    aspect_ratio = options["aspect_ratio"]
    num_rectangles = options["num_rectangles"]

    if options["grid"]:
        assert aspect_ratio is None and num_rectangles is None, \
            "--grid is incompatible with --aspect-ratio and --num-rectangles"
        n_rows, n_cols = map(int, options["grid"].split("x"))
        die.initial_grid(n_rows, n_cols)

    if aspect_ratio is not None:
        if num_rectangles is None:
            die.split_refinable_regions(aspect_ratio)
        else:
            die.split_refinable_regions(aspect_ratio, num_rectangles)
    else:
        assert num_rectangles is None, "--aspect-ratio must be specified when using --num-rectangles"

    alpha: bool = options["alpha"]
    assert 0 <= alpha <= 1, "alpha must be between 0 and 1"

    threshold: float = options["threshold"]
    assert 0 <= threshold <= 1, "threshold must be between 0 and 1"

    max_iter: int = options["max_iter"]
    assert max_iter > 0, "The maximum number of iterations must be positive"

    plot_name: str = options["plot"]
    verbose: bool = options["verbose"]
    visualize: bool = options["visualize"]
    assert not visualize or visualize and plot_name, "--plot_name is required when using --visualize"

    start_time = 0.0
    if verbose:
        start_time = time()

    die, allocation = glbfloor(die, threshold, alpha, max_iter, plot_name, verbose, visualize)

    if verbose:
        print(f"Elapsed time: {time() - start_time:.3f} s")

    out_netlist_file: str | None = options["out_netlist"]
    if out_netlist_file is not None:
        assert die.netlist is not None, "No netlist associated to the die"  # Assertion to suppress Mypy error
        die.netlist.write_yaml(out_netlist_file)

    out_allocation_file: str | None = options["out_allocation"]
    if out_allocation_file is not None:
        allocation.write_yaml(out_allocation_file)


if __name__ == "__main__":
    main()
