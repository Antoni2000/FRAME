"""glbfloor tool. See README.md for more information"""

import argparse
from time import time
from typing import Any

from gekko import GEKKO
from PIL import Image

from frame.geometry.geometry import Shape, Point, Rectangle
from frame.die.die import Die
from frame.netlist.netlist import Netlist
from frame.allocation.allocation import AllocDescriptor, Alloc, Allocation

from tools.glbfloor.plots import get_grid_image, plot_grid


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
    parser.add_argument("-d", "--die", metavar="<WIDTH>x<HEIGHT> or FILENAME", default="1x1",
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
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="print the optimization logs and additional information")
    parser.add_argument("--visualize", action="store_true",
                        help="produce animations to visualize the optimizations (might take a long time to execute)")
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


def touch(r1: Rectangle, r2: Rectangle, epsilon: float = 0.001) -> bool:
    """Checks whether two rectangles touch. Overlapping rectangles are considered to be touching too"""
    r1min, r1max = r1.bounding_box
    r2min, r2max = r2.bounding_box
    return r2min.x - r1max.x < epsilon and r1min.x - r2max.x < epsilon \
        and r2min.y - r1max.y < epsilon and r1min.y - r2max.y < epsilon


def get_neighbouring_cells(allocation: Allocation, cell_index: int) -> list[int]:
    """
    Given an allocation and a cell index, returns a list of the indices of the cells neighbouring the specified cell
    :param allocation: the allocation
    :param cell_index: the index of the cell
    :return: the list of indices of the neighbouring cells
    """
    n_cells = allocation.num_rectangles
    allocs = allocation.allocations
    cell_rect = allocs[cell_index].rect
    neighbouring_cells = []
    for c in range(n_cells):
        if c != cell_index and touch(cell_rect, allocs[c].rect):
            neighbouring_cells.append(c)
    return neighbouring_cells


def extract_solution(g: GEKKO, netlist: Netlist, allocation: Allocation) \
        -> tuple[Netlist, Allocation, dict[str, tuple[float, float]]]:
    """
    Extracts the solution from the GEKKO model
    :param g: GEKKO model
    :param netlist: netlist containing the modules with centroids initialized
    :param allocation: allocation to optimize
    :return:
    - netlist - netlist with the centroids of the modules updated
    - allocation - optimized allocation
    - dispersions - a dictionary from module name to float pair which indicates the dispersion of each module
    """
    n_cells = allocation.num_rectangles
    allocs = allocation.allocations

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


def solve(g: GEKKO, netlist: Netlist, allocation: Allocation, max_iter: int = 100, verbose: bool = False,
          visualize: bool = False) -> tuple[GEKKO, list[Image.Image]]:
    """
    Solves the optimization problem in the given GEKKO model
    :param g: GEKKO model
    :param netlist: netlist containing the modules with centroids initialized
    :param allocation: allocation to optimize
    :param max_iter: maximum number of iterations for GEKKO
    :param verbose: if True, the GEKKO optimization log is displayed (not supported if visualize is True)
    :param visualize: if True, a list of PIL images is returned visualizing the optimization
    :return:
    - g - the solved GEKKO model
    - vis_imgs - if visualize is True, a list of images visualizing the optimization, otherwise, an empty list
    """
    vis_imgs = []
    if not visualize:
        g.options.MAX_ITER = max_iter
        g.solve(disp=verbose)
    else:
        # See https://stackoverflow.com/a/73196238/10152624 for the method used here
        i = 0
        while i < max_iter:
            g.options.MAX_ITER = i
            g.options.COLDSTART = 1
            g.solve(disp=False, debug=0)

            netlist, allocation, _ = extract_solution(g, netlist, allocation)
            vis_imgs.append(get_grid_image(netlist, allocation, draw_text=False))
            print(i, end=" ", flush=True)

            if g.options.APPSTATUS == 1:
                print("\nThe solution was found.")
                break
            else:
                i += 1
        else:
            print(f"Maximum number of iterations ({max_iter}) reached! The solution was not found.")
    return g, vis_imgs


def optimize_allocation(netlist: Netlist, allocation: Allocation, dispersions: dict[str, tuple[float, float]],
                        threshold: float, alpha: float, verbose: bool = False, visualize: bool = False) \
        -> tuple[Netlist, Allocation, dict[str, tuple[float, float]], list[Image.Image]]:
    """
    Optimizes the given allocation to minimize the dispersion and the wire length of the floor plan
    :param netlist: netlist containing the modules with centroids initialized
    :param allocation: allocation to optimize
    :param dispersions: a dictionary from module name to float pair which indicates the dispersion of each module in the
    given netlist and allocation
    :param threshold: hyperparameter between 0 and 1 to decide if allocations can be fixed
    :param alpha: hyperparameter between 0 and 1 to control the balance between dispersion and wire length.
    Smaller values will reduce the dispersion and increase the wire length, and greater ones the other way around
    :param verbose: if True, the GEKKO optimization log is displayed
    :param visualize: if True, a list of PIL images is returned visualizing the optimization
    :return: the optimal solution found:
    - netlist - netlist with the centroids of the modules updated
    - allocation - optimized allocation
    - dispersions - a dictionary from module name to float pair which indicates the dispersion of each module
    - vis_imgs - if visualize is True, a list of images visualizing the optimization, otherwise, an empty list
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

    # Get neighbouring cells of all the cells
    neigh_cells: list[list[int]] = [[]] * n_cells
    for c in range(n_cells):
        neigh_cells[c] = get_neighbouring_cells(allocation, c)

    # Fix (make constant) cells that have an allocation close to one (or zero) and are completely surrounded by cells
    # that are also close to one (or zero). Modules with all the cells fixed, or with the fixed attribute set to True
    # are also fixed in the model.
    for m, module in enumerate(netlist.modules):
        const_module = True
        if not module.fixed:
            for c in range(n_cells):
                a_mc_val = get_value(g.a[m][c])
                if a_mc_val > threshold and all(get_value(g.a[m][i]) > threshold for i in neigh_cells[c]) or \
                        a_mc_val < 1 - threshold and all(get_value(g.a[m][i]) < 1 - threshold for i in neigh_cells[c]):
                    g.a[m][c] = a_mc_val
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
            ex = g.Var(lb=0)
            g.Equation(g.sum([g.x[module2m[module]] for module in e.modules]) / len(e.modules) == ex)
            ey = g.Var(lb=0)
            g.Equation(g.sum([g.y[module2m[module]] for module in e.modules]) / len(e.modules) == ey)
            for module in e.modules:
                m = module2m[module]
                g.Minimize(alpha * e.weight * ((ex - g.x[m])**2 + (ey - g.y[m])**2))

    # Total dispersion
    g.Minimize((1 - alpha) * g.sum([g.dx[m] + g.dy[m] for m in range(netlist.num_modules)]))

    g, vis_imgs = solve(g, netlist, allocation, verbose=verbose, visualize=visualize)

    netlist, allocation, dispersions = extract_solution(g, netlist, allocation)

    return netlist, allocation, dispersions, vis_imgs


def glbfloor(netlist: Netlist, n_rows: int, n_cols: int, cell_shape: Shape, threshold: float, alpha: float,
             max_iter: int | None = None, plot_name: str | None = None,
             verbose: bool = False, visualize: bool = False) -> tuple[Netlist, Allocation]:
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
    :param plot_name: name of the plot to be produced in each iteration. The iteration number and the PNG extension
    are added automatically. If None, no plots are produced
    :param verbose: If True, the GEKKO optimization log and iteration numbers are displayed
    :param visualize: If True, produce a GIF to visualize the complete optimization process
    :return: the optimal solution found:
    - netlist - Netlist with the centroids of the modules updated.
    - allocation - Refined allocation with the ratio of each module in each cell of the grid.
    """
    all_vis_imgs = []
    durations = []

    allocation = None
    dispersions = None

    n_iter = 0
    while max_iter is None or n_iter <= max_iter:
        if n_iter == 0:
            allocation = create_initial_allocation(netlist, n_rows, n_cols, cell_shape)
            dispersions = calculate_dispersions(netlist, allocation)

            if plot_name is not None:
                plot_grid(netlist, allocation, dispersions, alpha,
                          filename=f"{plot_name}-{n_iter}.png")

            n_iter += 1
        else:  # n_iter > 0
            # Assertion to suppress Mypy errors (should never happen)
            assert allocation is not None and dispersions is not None

            if allocation.must_be_refined(threshold):
                allocation = allocation.refine(threshold)
            else:
                break

        netlist, allocation, dispersions, vis_imgs = optimize_allocation(netlist, allocation, dispersions,
                                                                         threshold, alpha, verbose, visualize)
        if visualize:
            all_vis_imgs.extend(vis_imgs)
            durations.extend([100] * (len(vis_imgs) - 1) + [1000])

        if plot_name is not None:
            plot_grid(netlist, allocation, dispersions, alpha, filename=f"{plot_name}-{n_iter}.png")

        if verbose:
            print(f"Iteration {n_iter} finished\n")

        n_iter += 1

    if visualize:
        all_vis_imgs[0].save(f"{plot_name}.gif", save_all=True, append_images=all_vis_imgs[1:], duration=durations)

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
    visualize: bool = options["visualize"]
    plot_name: str = options["plot"]

    start_time = 0.0
    if verbose:
        start_time = time()

    netlist, allocation = glbfloor(netlist, n_rows, n_cols, cell_shape, threshold, alpha, max_iter,
                                   plot_name, verbose, visualize)

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
