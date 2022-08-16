import argparse
from time import time
from typing import Any

from gekko import GEKKO

from frame.geometry.geometry import Shape, Point, Rectangle
from frame.die.die import Die
from frame.netlist.netlist import Netlist
from frame.allocation.allocation import AllocDescriptor, Alloc, Allocation

from tools.glbfloor.plots import plot_grid


def parse_options(prog: str | None = None, args: list[str] | None = None) -> dict[str, Any]:
    """
    Parse the command-line arguments for the tool
    :param prog: tool name
    :param args: command-line arguments
    :return: a dictionary with the arguments
    """
    parser = argparse.ArgumentParser(prog=prog)  # TODO: write description
    parser.add_argument("netlist",
                        help="input file (netlist)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="print the optimization logs and additional information")
    parser.add_argument("-d", "--die", metavar="<width>x<height> or filename", default="1x1",
                        help="size of the die (width x height) or name of the file")
    parser.add_argument("-g", "--grid", metavar="<rows>x<cols>", required=True,
                        help="size of the initial grid (rows x columns)", )
    parser.add_argument("-a", "--alpha", type=float, required=True,
                        help="tradeoff hyperparameter between 0 and 1 to control the balance between dispersion and "
                             "wire length")
    parser.add_argument("-t", "--threshold", type=float, default=0.95,
                        help="threshold hyperparameter between 0 and 1 to decide if allocations must be refined")
    parser.add_argument("-i", "--max-iter", type=int,
                        help="maximum number of optimizations performed (if not present, until no more refinements can "
                             "be performed)")
    parser.add_argument("-p", "--plot",
                        help="plot name (if not present, no plots are produced)")
    parser.add_argument("--simple-plot", action="store_true",
                        help="simplify the plots by not including borders nor text annotations")
    parser.add_argument("--out-netlist",
                        help="output netlist file (if not present, no file is produced)")
    parser.add_argument("--out-allocation",
                        help="output allocation file (if not present, no file is produced)")
    return vars(parser.parse_args(args))


def get_value(v) -> float:
    """
    Get the value of the GEKKO object v
    :param v: a variable or a value
    :return: the value of v
    """
    if not isinstance(v, float):
        v = v.value.value
        if hasattr(v, "__getitem__"):
            v = v[0]
    if not isinstance(v, float):
        try:
            v = float(v)
        except TypeError:
            raise ValueError(f"Could not get value of {v} (type: {type(v)}")
    return v


def create_initial_allocation(netlist: Netlist, n_rows: int, n_cols: int, cell_shape: Shape) -> Allocation:
    """
    Creates the initial allocation grid. The allocation ratios are assigned according to the intersection of the module
    rectangles with the grid cells. All modules without rectangles are assigned a square
    :param netlist: netlist containing the modules with centroids initialized
    :param n_rows: initial number of rows in the grid
    :param n_cols: initial number of columns in the grid
    :param cell_shape: shape of the cells (typically the shape of the die scaled by the number of rows and columns)
    :return: the initial allocation
    """
    n_cells = n_rows * n_cols

    cells = [Rectangle()] * n_cells
    for r in range(n_rows):
        for c in range(n_cols):
            cells[r * n_cols + c] = Rectangle(center=Point((0.5 + c) * cell_shape.w, (0.5 + r) * cell_shape.h),
                                              shape=cell_shape)

    allocation_list: list[AllocDescriptor | None] = [None] * n_cells
    for c in range(n_cells):
        c_alloc = Alloc()
        for module in netlist.modules:
            # Initialize to 1 for all modules so the center can be computed (0 raises ZeroDivisionError)
            # This value will be ignored when calling the initial_allocation method.
            c_alloc[module.name] = 1.0
        allocation_list[c] = (cells[c].vector_spec, c_alloc, 0)

    return Allocation(allocation_list).initial_allocation(netlist, include_area_zero=True)


def calculate_dispersions(netlist: Netlist, allocation: Allocation) -> dict[str, tuple[float, float]]:
    """
    Calculate the dispersions of the modules
    :param netlist: netlist containing the modules with centroids initialized
    :param allocation: the allocation of the modules
    :return: a dictionary from module name to float pair which indicates the dispersion of each module in the
    given netlist and allocation
    """
    dispersions = {}
    for module in netlist.modules:
        assert module.center is not None
        dx, dy = 0.0, 0.0
        for c, cell in enumerate(allocation.allocations):
            area = cell.rect.area * allocation.allocation_module(module.name)[c].area
            dx += area * (module.center.x - cell.rect.center.x)**2
            dy += area * (module.center.y - cell.rect.center.y)**2
        dispersions[module.name] = dx, dy
    return dispersions


def optimize_allocation(netlist: Netlist, allocation: Allocation, dispersions: dict[str, tuple[float, float]],
                        alpha: float, verbose: bool = False) \
        -> tuple[Netlist, Allocation, dict[str, tuple[float, float]]]:
    """
    Optimizes the given allocation to minimize the dispersion and the wire length of the floor plan
    :param netlist: netlist containing the modules with centroids initialized
    :param allocation: allocation to optimize
    :param dispersions: a dictionary from module name to float pair which indicates the dispersion of each module in the
    given netlist and allocation
    :param alpha: hyperparameter between 0 and 1 to control the balance between dispersion and wire length.
    Smaller values will reduce the dispersion and increase the wire length, and greater ones the other way around
    :param verbose: if True, the GEKKO optimization log is displayed
    :return: the optimal solution found:
    - netlist - netlist with the centroids of the modules updated
    - allocation - optimized allocation
    - dispersions - a dictionary from module name to float pair which indicates the dispersion of each module
    """
    n_modules = netlist.num_modules
    n_cells = allocation.num_rectangles
    allocs = allocation.allocations

    (x_min, y_min), (x_max, y_max) = allocation.bounding_box.bounding_box

    g = GEKKO(remote=False)

    # Centroid of modules
    g.x = g.Array(g.Var, n_modules, lb=x_min, ub=x_max)
    g.y = g.Array(g.Var, n_modules, lb=y_min, ub=y_max)

    # Dispersion of modules
    g.dx = g.Array(g.Var, n_modules, lb=0)
    g.dy = g.Array(g.Var, n_modules, lb=0)

    # Ratios of area of c used by module m
    g.a = g.Array(g.Var, (n_modules, n_cells), lb=0, ub=1)

    # Set initial values
    for m, module in enumerate(netlist.modules):
        center = module.center
        assert center is not None
        g.x[m].value, g.y[m].value = center

        g.dx[m].value, g.dy[m].value = dispersions[module.name]

        for c in range(n_cells):
            g.a[m][c].value = allocation.allocation_module(module.name)[c].area

    # Make not refined or almost zero cells and fixed or completed modules constant
    max_refinement_depth = allocation.max_refinement_depth()
    for m, module in enumerate(netlist.modules):
        const_module = True
        if not module.fixed:
            for c in range(n_cells):
                a_mc_value = get_value(g.a[m][c])
                if allocs[c].depth != max_refinement_depth or a_mc_value < 0.001:
                    g.a[m][c] = a_mc_value
                elif const_module:
                    const_module = False
        if const_module:
            g.x[m] = get_value(g.x[m])
            g.y[m] = get_value(g.y[m])
            g.dx[m] = get_value(g.dx[m])
            g.dy[m] = get_value(g.dy[m])
            for c in range(n_cells):
                g.a[m][c] = get_value(g.a[m][c])

    # Cell constraints
    for c in range(n_cells):
        # Cells cannot be over-occupied
        g.Equation(g.sum([g.a[m][c] for m in range(n_modules)]) <= 1)

    # Module constraints
    for m in range(n_modules):
        m_area = netlist.modules[m].area()

        # Modules must have sufficient area
        g.Equation(g.sum([allocs[c].rect.area * g.a[m][c] for c in range(n_cells)]) >= m_area)

        # Centroid of modules
        g.Equation(1 / m_area * g.sum([allocs[c].rect.area * allocs[c].rect.center.x * g.a[m][c]
                                       for c in range(n_cells)]) == g.x[m])
        g.Equation(1 / m_area * g.sum([allocs[c].rect.area * allocs[c].rect.center.y * g.a[m][c]
                                       for c in range(n_cells)]) == g.y[m])

        # Dispersion of modules
        g.Equation(g.sum([allocs[c].rect.area * g.a[m][c] * (g.x[m] - allocs[c].rect.center.x)**2
                          for c in range(n_cells)]) == g.dx[m])
        g.Equation(g.sum([allocs[c].rect.area * g.a[m][c] * (g.y[m] - allocs[c].rect.center.y)**2
                          for c in range(n_cells)]) == g.dy[m])

    module2m = {}
    for m, module in enumerate(netlist.modules):
        module2m[module] = m

    # Objective function: alpha * total wire length + (1 - alpha) * total dispersion

    # Total wire length
    for e in netlist.edges:
        if len(e.modules) == 2:
            m0 = module2m[e.modules[0]]
            m1 = module2m[e.modules[1]]
            g.Minimize(alpha * e.weight * ((g.x[m0] - g.x[m1])**2 + (g.y[m0] - g.y[m1])**2) / 2)
        else:
            ex = g.Var()
            g.Equation(g.sum([g.x[module2m[module]] for module in e.modules]) / len(e.modules) == ex)
            ey = g.Var()
            g.Equation(g.sum([g.y[module2m[module]] for module in e.modules]) / len(e.modules) == ey)
            for module in e.modules:
                m = module2m[module]
                g.Minimize(alpha * e.weight * ((ex - g.x[m])**2 + (ey - g.y[m])**2))

    # Total dispersion
    g.Minimize((1 - alpha) * g.sum([g.dx[m] + g.dy[m] for m in range(netlist.num_modules)]))

    g.solve(disp=verbose)

    # Extract solution
    allocation_list: list[AllocDescriptor | None] = [None] * n_cells
    for c in range(n_cells):
        c_alloc = Alloc()
        for m, module in enumerate(netlist.modules):
            c_alloc[module.name] = get_value(g.a[m][c])
        allocation_list[c] = (allocs[c].rect.vector_spec, c_alloc, 0)
    allocation = Allocation(allocation_list)

    dispersions = {}
    for m, module in enumerate(netlist.modules):
        module.center = Point(get_value(g.x[m]), get_value(g.y[m]))
        dispersions[module.name] = get_value(g.dx[m]), get_value(g.dy[m])

    return netlist, allocation, dispersions


def glbfloor(netlist: Netlist, n_rows: int, n_cols: int, cell_shape: Shape,
             threshold: float, alpha: float, max_iter: int | None = None,
             verbose: bool = False, plot_name: str | None = None, simple_plot: bool = False) \
        -> tuple[Netlist, Allocation]:
    """
    Calculates the initial allocation and optimizes it to minimize the dispersion and the wire length of the floor plan.
    Afterwards, the allocation is repeatedly refined and optimized until it cannot be further refined or the maximum
    number of iterations is reached
    :param netlist: netlist containing the modules with centroids initialized
    :param n_rows: initial number of rows in the grid
    :param n_cols: initial number of columns in the grid
    :param cell_shape: shape of the cells (typically the shape of the die scaled by the number of rows and columns)
    :param threshold: hyperparameter between 0 and 1 to decide if allocations must be refined
    :param alpha: hyperparameter between 0 and 1 to control the balance between dispersion and wire length.
    Smaller values will reduce the dispersion and increase the wire length, and greater ones the other way around
    :param max_iter: maximum number of optimization iterations performed, or None to stop when no more refinements
    can be performed
    :param verbose: If True, the GEKKO optimization log and iteration numbers are displayed
    :param plot_name: name of the plot to be produced in each iteration. The iteration number and the PNG extension
    are added automatically. If None, no plots are produced
    :param simple_plot: If True, the plots are simpler by not including borders nor text annotations
    :return: the optimal solution found:
    - netlist - Netlist with the centroids of the modules updated.
    - allocation - Refined allocation with the ratio of each module in each cell of the grid.
    """
    n_iter = 0
    allocation = None
    dispersions = None
    while max_iter is None or n_iter <= max_iter:
        if n_iter == 0:
            allocation = create_initial_allocation(netlist, n_rows, n_cols, cell_shape)
            dispersions = calculate_dispersions(netlist, allocation)

            if plot_name is not None:
                plot_grid(netlist, allocation, dispersions,
                          suptitle=f"alpha = {alpha}", filename=f"{plot_name}-{n_iter}.png", simple_plot=simple_plot)

            n_iter += 1
        else:  # n_iter > 0
            # Assertion to suppress Mypy errors (should never happen)
            assert allocation is not None and dispersions is not None

            if allocation.must_be_refined(threshold):
                allocation = allocation.refine(threshold)
            else:
                break

        netlist, allocation, dispersions = optimize_allocation(netlist, allocation, dispersions, alpha, verbose)

        if plot_name is not None:
            plot_grid(netlist, allocation, dispersions,
                      suptitle=f"alpha = {alpha}", filename=f"{plot_name}-{n_iter}.png", simple_plot=simple_plot)

        if verbose:
            print(f"Iteration {n_iter} finished\n")

        n_iter += 1

    assert allocation is not None  # Assertion to suppress Mypy error (should never happen)
    return netlist, allocation


def main(prog: str | None = None, args: list[str] | None = None):
    """Main function."""

    options = parse_options(prog, args)

    # Initial netlist
    netlist = Netlist(options["netlist"])

    # Die shape
    die = Die(options["die"])
    die_shape = Shape(die.width, die.height)

    # Initial grid
    n_rows, n_cols = map(int, options["grid"].split("x"))
    assert n_rows > 0 and n_cols > 0, "The number of rows and columns of the grid must be positive"
    cell_shape = Shape(die_shape.w / n_cols, die_shape.h / n_rows)

    alpha: bool = options["alpha"]
    assert 0 <= alpha <= 1, "alpha must be between 0 and 1"

    threshold: float = options["threshold"]
    assert 0 <= threshold <= 1, "threshold must be between 0 and 1"

    max_iter: int = options["max_iter"]
    assert max_iter > 0, "The maximum number of iterations must be positive"

    verbose: bool = options["verbose"]
    plot_name: str = options["plot"]
    simple_plot: bool = options["simple_plot"]

    start_time = 0.0
    if verbose:
        start_time = time()

    netlist, allocation = glbfloor(netlist, n_rows, n_cols, cell_shape, threshold, alpha, max_iter,
                                   verbose, plot_name, simple_plot)

    if verbose:
        print(f"Elapsed time: {time() - start_time:.3f} s")

    out_netlist_file: str | None = options["out_netlist"]
    if out_netlist_file is not None:
        netlist.write_yaml(out_netlist_file)

    out_allocation_file: str | None = options["out_allocation"]
    if out_allocation_file is not None:
        allocation.write_yaml(out_allocation_file)


if __name__ == "__main__":
    main()
