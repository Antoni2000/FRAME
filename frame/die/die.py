from collections import deque
from itertools import combinations
from typing import Set, Deque
from dataclasses import dataclass

from .yaml_parse_die import parse_yaml_die
from frame.geometry.geometry import Shape, Rectangle, Point
from frame.netlist.netlist import Netlist
from frame.utils.keywords import KW_CENTER, KW_SHAPE, KW_REGION, KW_GROUND, KW_BLOCKAGE
from frame.utils.utils import TextIO_String


@dataclass()
class GroundRegion:
    rmin: int
    rmax: int
    cmin: int
    cmax: int
    area: float
    ratio: float

    def __str__(self) -> str:
        return f'<rows=({self.rmin}-{self.rmax}), cols=({self.cmin}-{self.cmax}), area={self.area}, ratio={self.ratio}>'

    def __hash__(self) -> int:
        return hash(37 * self.rmin + 13 * self.rmax + 7 * self.cmin + 23 * self.cmax)


class Die:
    """
    Class to represent the die (ground and tagged rectangles)
    """
    _shape: Shape  # Shape of the die (width and height)
    _regions: list[Rectangle]  # List of non-ground regions
    _ground_regions: list[Rectangle]  # List of ground regions (not covered by fixed rectangles)
    _blockages: list[Rectangle]  # List of blockages
    _fixed: list[Rectangle]  # List of fixed rectangles (obtained from a netlist)
    _epsilon: float  # Precision when dealing with coordinates
    _x: list[float]  # List of x coordinates of potential rectangles
    _y: list[float]  # List of y coordinates of potential rectangles
    _cells: list[list[bool]]  # Matrix of rectangles (True occupied, False available)

    def __init__(self, stream: TextIO_String, netlist: Netlist | None = None):
        """
        Constructor of a die from a file or from a string of text
        :param stream: name of the YAML file (str) or handle to the file
        :param netlist: the netlist associated to the die (necessary for fixed modules)
        """
        regions: list[Rectangle]
        self._shape, regions = parse_yaml_die(stream)
        self._epsilon = min(self.width, self.height) * 10e-12

        # Selectec blockages from the other regions
        self._regions, self._blockages = [], []
        for r in regions:
            self._blockages.append(r) if r.region == KW_BLOCKAGE else self._regions.append(r)

        # Obtained the fixed rectangles from the netlist
        self._fixed = [] if netlist is None else netlist.fixed_rectangles()

        self._calculate_region_points()
        self._calculate_cell_matrix()
        self._calculate_ground_rectangles()
        self._check_rectangles()

    @property
    def width(self) -> float:
        """Returns the width of the die."""
        return self._shape.w

    @property
    def height(self) -> float:
        """Returns the height of the die."""
        return self._shape.h

    @property
    def regions(self) -> list[Rectangle]:
        """Returns the list of non-ground regions."""
        return self._regions

    @property
    def blockages(self) -> list[Rectangle]:
        """Returns the list of blockages."""
        return self._blockages

    @property
    def fixed(self) -> list[Rectangle]:
        """Returns the list of fixed rectangles."""
        return self._fixed

    @property
    def ground_regions(self) -> list[Rectangle]:
        """Returns the list of ground regions not covered by fixed rectangles"""
        return self._ground_regions

    def allocation_rectangles(self) -> tuple[list[Rectangle], list[Rectangle]]:
        """
        Returns the two lists of rectangles usable for module allocation. The first list contains
        the rectangles that a refinable during allocation. The second list contains the rectangles
        that correspond to fixed modules.
        """
        return self.regions + self.ground_regions, self.fixed

    def _calculate_region_points(self):
        """
        Calculates the list of points to be candidates for rectangle corners in the ground.
        """
        x, y = [0], [0]
        for r in self.regions + self.blockages + self.fixed:
            bb = r.bounding_box
            x.append(bb[0].x)
            x.append(bb[1].x)
            y.append(bb[0].y)
            y.append(bb[1].y)
        x.append(self.width)
        y.append(self.height)
        x.sort()
        y.sort()
        # Remove duplicates
        self._x = []
        for i, val in enumerate(x):
            if i == 0 or val > self._x[-1] + self._epsilon:
                self._x.append(float(val))
        self._y = []
        for i, val in enumerate(y):
            if i == 0 or val > self._y[-1] + self._epsilon:
                self._y.append(float(val))

    def _cell_center(self, i: int, j: int) -> Point:
        """
        Returns the center of a cell
        :param i: row of the cell
        :param j: column of the cell
        :return: the center of the cell
        """
        return Point((self._x[i] + self._x[i + 1]) / 2, (self._y[j] + self._y[j + 1]) / 2)

    def _calculate_cell_matrix(self):
        """
        Calculates the matrix of cells. It indicates which cells are occupied by regions, blockages or fixed rectangles
        """
        self._cells = [[False] * (len(self._x) - 1) for _ in range(len(self._y) - 1)]
        for i in range(len(self._x) - 1):
            for j in range(len(self._y) - 1):
                p = self._cell_center(i, j)
                for r in self.regions + self.blockages + self.fixed:
                    if r.point_inside(p):
                        self._cells[j][i] = True

    def _cell_inside_rectangle(self, i: int, j: int, r: Rectangle) -> bool:
        """
        Determines whether cell[i,j] is inside a rectangle
        :param i: row of the cell
        :param j: column of the cell
        :param r: rectantle
        :return: True if it is inside the rectangle, and False otherwise
        """
        return r.point_inside(self._cell_center(i, j))

    def _calculate_ground_rectangles(self):
        self._ground_regions = []
        g_rect = self._find_largest_ground_region()
        while g_rect is not None:
            self._ground_regions.append(g_rect)
            g_rect = self._find_largest_ground_region()

    def _find_largest_ground_region(self) -> Rectangle | None:
        """
        Calculates the largest non-occupied rectangular region of the die
        :return: the largest region
        """
        all_regions: Set[GroundRegion] = set()  # Set of all rectangular regions
        for r in range(len(self._cells)):
            height = self._y[r + 1] - self._y[r]
            for c in range(len(self._cells[r])):
                if not self._cells[r][c]:
                    width = self._x[c + 1] - self._x[c]
                    area = width * height
                    ratio = height / width
                    if ratio < 1.0:
                        ratio = 1 / ratio
                    reg: GroundRegion = GroundRegion(r, r, c, c, area, ratio)
                    more_regions = self._expand_rectangle(reg)
                    all_regions = all_regions | more_regions

        if len(all_regions) == 0:
            return None

        max_area = -1
        best_reg: GroundRegion | None = None
        for reg in all_regions:
            if reg.area > max_area:
                max_area = reg.area  # type: ignore
                best_reg = reg

        # Occupy the cells
        assert best_reg is not None
        for row in range(best_reg.rmin, best_reg.rmax + 1):  # type: ignore
            for col in range(best_reg.cmin, best_reg.cmax + 1):
                self._cells[row][col] = True

        x_center = (self._x[best_reg.cmin] + self._x[best_reg.cmax + 1]) / 2
        y_center = (self._y[best_reg.rmin] + self._y[best_reg.rmax + 1]) / 2
        width = self._x[best_reg.cmax + 1] - self._x[best_reg.cmin]
        height = self._y[best_reg.rmax + 1] - self._y[best_reg.rmin]
        kwargs = {KW_CENTER: Point(x_center, y_center), KW_SHAPE: Shape(width, height), KW_REGION: KW_GROUND}
        return Rectangle(**kwargs)

    def _expand_rectangle(self, r: GroundRegion) -> Set[GroundRegion]:
        """
        Expands a rectangle of regions and generates all the valid regions.
        The expansion is done by increasing rows and columns
        :param r: a ground region
        :return: the set of rectangles of ground regions
        """
        g_regions: Set[GroundRegion] = {r}
        pending: Deque[GroundRegion] = deque()
        pending.append(r)
        while len(pending) > 0:
            r = pending.popleft()
            if r.rmax < len(self._cells) - 1:  # Add one row
                row = r.rmax + 1
                valid = not any(self._cells[row][j] for j in range(r.cmin, r.cmax + 1))
                if valid:
                    height = self._y[r.rmax + 2] - self._y[r.rmin]
                    width = self._x[r.cmax + 1] - self._x[r.cmin]
                    area = height * width
                    ratio = height / width
                    if ratio < 1.0:
                        ratio = 1 / ratio
                    new_r = GroundRegion(r.rmin, r.rmax + 1, r.cmin, r.cmax, area, ratio)
                    if new_r not in g_regions:
                        g_regions.add(new_r)
                        pending.append(new_r)

            if r.cmax < len(self._cells[0]) - 1:  # Add one column
                col = r.cmax + 1
                valid = not any(self._cells[i][col] for i in range(r.rmin, r.rmax + 1))
                if valid:
                    height = self._y[r.rmax + 1] - self._y[r.rmin]
                    width = self._x[r.cmax + 2] - self._x[r.cmin]
                    area = height * width
                    ratio = height / width
                    if ratio < 1.0:
                        ratio = 1 / ratio
                    new_r = GroundRegion(r.rmin, r.rmax, r.cmin, r.cmax + 1, area, ratio)
                    if new_r not in g_regions:
                        g_regions.add(new_r)
                        pending.append(new_r)

        return g_regions

    def _check_rectangles(self) -> None:
        """
        Checks that the list of rectangles is correct, i.e., they do not overlap and the sum of the
        areas is equal to the area of the die. An assertion is raised of something is wrong.
        """
        all_rectangles = self.regions + self.ground_regions + self.blockages + self.fixed
        die = Rectangle(center=Point(self.width / 2, self.height / 2), shape=Shape(self.width, self.height))

        # Check that all rectangles are inside
        for r in all_rectangles:
            ll, ur = r.bounding_box
            assert die.point_inside(ll) and die.point_inside(ur), "Some rectangle is outside the die"

        # Check that no rectangles overlap
        pairs = list(combinations(all_rectangles, 2))
        for r1, r2 in pairs:
            assert not r1.overlap(r2), "Some rectangles overlap"

        # Check that the total area of the rectangles is equal to the area of the die
        area_rect = sum(r.area for r in all_rectangles)
        assert abs(area_rect - die.area) < self._epsilon, "Incorrect total area of rectangles"


def gather_boundaries(rectangles: list[Rectangle], epsilon: float = 1e-15) -> tuple[list[float], list[float]]:
    """
    Gathers the x and y coordinates of the sides of a list of rectangles
    :param rectangles: list of rectangles
    :param epsilon: minimum distance between two adjacent coordinates
    :return: the list of x and y coordinates, sorted in ascending order
    """
    x, y = [], []
    for r in rectangles:
        bb = r.bounding_box
        x.append(bb[0].x)
        x.append(bb[1].x)
        y.append(bb[0].y)
        y.append(bb[1].y)
    x.sort()
    y.sort()
    # Remove duplicates
    uniq_x = []
    for i, val in enumerate(x):
        if i == 0 or val > uniq_x[-1] + epsilon:
            uniq_x.append(float(val))
    uniq_y = []
    for i, val in enumerate(y):
        if i == 0 or val > uniq_y[-1] + epsilon:
            uniq_y.append(float(val))
    return uniq_x, uniq_y
