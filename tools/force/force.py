# (c) Marçal Comajoan Cara 2022
# For the FRAME Project.
# Licensed under the MIT License (see https://github.com/jordicf/FRAME/blob/master/LICENSE.txt).

import argparse
from time import time
from typing import Any

from frame.die.die import Die
from frame.netlist.netlist import Netlist

from tools.force.fruchterman_reingold import force_algorithm


def parse_options(prog: str | None = None, args: list[str] | None = None) -> dict[str, Any]:
    """
    Parse the command-line arguments for the tool
    :param prog: tool name
    :param args: command-line arguments
    :return: a dictionary with the arguments
    """
    parser = argparse.ArgumentParser(prog=prog,
                                     description="Relocate the modules of the netlist using a force-directed algorithm "
                                                 "to obtain better initial values for the next stages.")
    parser.add_argument("--netlist", required=True,
                        help="input netlist filename")
    parser.add_argument("-d", "--die", metavar="<WIDTH>x<HEIGHT> or FILENAME", required=True,
                        help="size of the die (width x height) or name of the file")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="print the optimization logs, elapsed time, and some additional information")
    parser.add_argument("--visualize",
                        help="name of the GIF to visualize the full optimizations process "
                             "(if not present, no visualization is produced)")
    parser.add_argument("--out-netlist",
                        help="output netlist file (if not present, no file is produced)")
    return vars(parser.parse_args(args))


def main(prog: str | None = None, args: list[str] | None = None) -> None:
    """Main function."""
    options = parse_options(prog, args)

    netlist = Netlist(options["netlist"])
    die = Die(options["die"], netlist)

    verbose: bool = options["verbose"]
    visualize: str | None = options["visualize"]

    start_time = 0.0
    if verbose:
        start_time = time()

    die = force_algorithm(die, verbose=verbose, visualize=visualize)

    if verbose:
        print(f"Elapsed time: {time() - start_time:.3f} s")

    out_netlist_file: str | None = options["out_netlist"]
    if out_netlist_file is not None:
        assert die.netlist is not None, "No netlist associated to the die"  # Assertion to suppress Mypy error
        die.netlist.write_yaml(out_netlist_file)


if __name__ == "__main__":
    main()
