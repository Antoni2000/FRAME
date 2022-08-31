from typing import Any, TypeVar, Callable, Union
from enum import Enum
from gekko import GEKKO
from gekko.gk_variable import GKVariable
from gekko.gk_operators import GK_Value

from tools.rect.canvas import Canvas
from argparse import ArgumentParser

BoxType = tuple[float, float, float, float]
InputModule = tuple[BoxType, list[BoxType], list[BoxType], list[BoxType], list[BoxType]]
OptionalList = dict[int, float]
OptionalMatrix = dict[int, OptionalList]
Hyperedge = tuple[float, list[int]]
Hypergraph = list[Hyperedge]
GekkoType = Union[float, GKVariable]
# Think of GekkoType as either a constant, a variable or an expression.
# Aka. Something that evaluates to a number


def value_of(v: GekkoType) -> float:
    if v is float:
        return v
    if isinstance(v, list):
        return v[0]
    if isinstance(v, GKVariable):
        if type(v.value) == GK_Value:
            return v.value[0]
        if v.value is float:
            return v.value
    raise Exception("Unknown GekkoType")


def parse_options(prog: str | None = None, args: list[str] | None = None) -> dict[str, Any]:
    """
    Parse the command-line arguments for the tool
    :param prog: tool name
    :param args: command-line arguments
    :return: a dictionary with the arguments
    """
    parser = ArgumentParser(prog=prog, description="A tool for module legalization", usage='%(prog)s [options]')
    parser.add_argument("filename", type=str, help="Input file (.yaml)")
    parser.add_argument("--max_ratio", type=float, dest='max_ratio', default=2.00,
                        help="The maximum allowable ratio for a rectangle")
    return vars(parser.parse_args(args))


def hsv_to_rgb(h: float, s: float = 0.7, v: float = 1.0) -> tuple[float, float, float]:
    h = h % 1.0
    r = max(0.0, min(1.0, abs(6.0 * h - 3.0) - 1.0))
    g = max(0.0, min(1.0, 2.0 - abs(6.0 * h - 2.0)))
    b = max(0.0, min(1.0, 2.0 - abs(6.0 * h - 4.0)))

    r = r * s + 1 - s
    g = g * s + 1 - s
    b = b * s + 1 - s

    return r * v, g * v, b * v


def rgb_to_str(r: float, g: float, b: float) -> str:
    rs = hex(int(r * 255))[2:]
    gs = hex(int(g * 255))[2:]
    bs = hex(int(b * 255))[2:]
    if len(rs) < 2:
        rs = "0" + rs
    if len(gs) < 2:
        gs = "0" + gs
    if len(bs) < 2:
        bs = "0" + bs
    return "#" + rs + gs + bs


def hsv_to_str(h: float, s: float = 0.7, v: float = 1.0) -> str:
    r, g, b = hsv_to_rgb(h, s, v)
    return rgb_to_str(r, g, b)


T = TypeVar('T')


def optional_get(opt: dict[int, T] | None, index: int) -> T | None:
    if opt is None:
        return None
    if index in opt:
        return opt[index]
    return None


def smax(x: GekkoType, y: GekkoType, sroot: Callable[[GekkoType], GekkoType], tau: GekkoType = 0.01) -> GekkoType:
    return 0.5 * (x + y + sroot((x - y) ** 2 + 4 * tau * tau))


def thin(w: GekkoType, h: GekkoType = 1) -> GekkoType:
    return 2 * w * h / (w * w + h * h)


class Cardinal(Enum):
    NORTH = 0
    SOUTH = 1
    EAST = 2
    WEST = 3


class ModelModule:
    def __init__(self,
                 x: list[GekkoType],
                 y: list[GekkoType],
                 w: list[GekkoType],
                 h: list[GekkoType],
                 gekko: GEKKO,
                 trunk: BoxType,
                 die_width: float,
                 die_height: float,
                 max_ratio: float,
                 nmods: int):
        self.N: list[int] = []
        self.S: list[int] = []
        self.E: list[int] = []
        self.W: list[int] = []
        self.x: list[GekkoType] = x
        self.y: list[GekkoType] = y
        self.w: list[GekkoType] = w
        self.h: list[GekkoType] = h
        self.c: int = 0
        self.id: int = nmods
        self.dw: float = die_width
        self.dh: float = die_height
        self.area: GekkoType = 0
        self.xsum: GekkoType = 0
        self.ysum: GekkoType = 0
        self.max_ratio: float = max_ratio
        self.set_trunk(gekko, trunk)

    def set_trunk(self, gekko: GEKKO, trunk: BoxType) -> None:
        assert self.c == 0, "!"
        self.c = 1
        self._define_vars(gekko, trunk)

    def add_rect_north(self, gekko: GEKKO, rect: BoxType) -> tuple[GekkoType, GekkoType, GekkoType, GekkoType]:
        assert self.c > 0, "!"
        self.N.append(self.c)
        self.c += 1
        xv, yv, wv, hv = self._define_vars(gekko, rect)

        # Keep the box attached
        gekko.Equation(yv == self.y[0] + 0.5 * self.h[0] + 0.5 * hv)
        gekko.Equation(xv >= self.x[0] - 0.5 * self.w[0] + 0.5 * wv)
        gekko.Equation(xv <= self.x[0] + 0.5 * self.w[0] - 0.5 * wv)

        return xv, yv, wv, hv

    def add_rect_south(self, gekko: GEKKO, rect: BoxType) -> tuple[GekkoType, GekkoType, GekkoType, GekkoType]:
        assert self.c > 0, "!"
        self.S.append(self.c)
        self.c += 1
        xv, yv, wv, hv = self._define_vars(gekko, rect)

        # Keep the box attached
        gekko.Equation(yv == self.y[0] - 0.5 * self.h[0] - 0.5 * hv)
        gekko.Equation(xv >= self.x[0] - 0.5 * self.w[0] + 0.5 * wv)
        gekko.Equation(xv <= self.x[0] + 0.5 * self.w[0] - 0.5 * wv)

        return xv, yv, wv, hv

    def add_rect_east(self, gekko: GEKKO, rect: BoxType) -> tuple[GekkoType, GekkoType, GekkoType, GekkoType]:
        assert self.c > 0, "!"
        self.E.append(self.c)
        self.c += 1
        xv, yv, wv, hv = self._define_vars(gekko, rect)

        # Keep the box attached
        gekko.Equation(xv == self.x[0] + 0.5 * self.w[0] + 0.5 * wv)
        gekko.Equation(yv >= self.y[0] - 0.5 * self.h[0] + 0.5 * hv)
        gekko.Equation(yv <= self.y[0] + 0.5 * self.h[0] - 0.5 * hv)

        return xv, yv, wv, hv

    def add_rect_west(self, gekko: GEKKO, rect: BoxType) -> tuple[GekkoType, GekkoType, GekkoType, GekkoType]:
        assert self.c > 0, "!"
        self.W.append(self.c)
        self.c += 1
        xv, yv, wv, hv = self._define_vars(gekko, rect)

        # Keep the box attached
        gekko.Equation(xv == self.x[0] - 0.5 * self.w[0] - 0.5 * wv)
        gekko.Equation(yv >= self.y[0] - 0.5 * self.h[0] + 0.5 * hv)
        gekko.Equation(yv <= self.y[0] + 0.5 * self.h[0] - 0.5 * hv)

        return xv, yv, wv, hv

    def _define_vars(self, gekko: GEKKO, rect: BoxType) -> tuple[GekkoType, GekkoType, GekkoType, GekkoType]:
        var_x = gekko.Var(lb=0, ub=self.dw, name="x" + str(self.id) + "i" + str(len(self.x)))
        var_y = gekko.Var(lb=0, ub=self.dh, name="y" + str(self.id) + "i" + str(len(self.x)))
        var_w = gekko.Var(lb=0.1, ub=self.dw, name="w" + str(self.id) + "i" + str(len(self.x)))
        var_h = gekko.Var(lb=0.1, ub=self.dh, name="h" + str(self.id) + "i" + str(len(self.x)))
        var_x.value = [rect[0]]
        var_y.value = [rect[1]]
        var_w.value = [rect[2]]
        var_h.value = [rect[3]]
        self.x.append(var_x)
        self.y.append(var_y)
        self.w.append(var_w)
        self.h.append(var_h)

        self.area += var_w * var_h
        self.xsum += var_x * var_w * var_h
        self.ysum += var_y * var_w * var_h

        # The box must stay inside the dice
        gekko.Equation(var_x - 0.5 * var_w >= 0)
        gekko.Equation(var_y - 0.5 * var_h >= 0)
        gekko.Equation(var_x + 0.5 * var_w <= self.dw)
        gekko.Equation(var_y + 0.5 * var_h <= self.dh)

        # The ratio cannot exceed a maximum value
        gekko.Equation(thin(var_w, var_h) >= thin(self.max_ratio))

        return var_x, var_y, var_w, var_h


class Model:
    """GEKKO model with variables"""
    gekko: GEKKO

    M: list[ModelModule]
    dw: float  # Die width
    dh: float  # Die height

    # Model variables
    # (without accurate type hints because GEKKO does not have type hints yet)
    x: list[list[GekkoType]]
    y: list[list[GekkoType]]
    w: list[list[GekkoType]]
    h: list[list[GekkoType]]
    max_ratio: float

    tau: float

    def define_module(self, trunk_box: BoxType) -> int:
        x: list[GekkoType] = []
        y: list[GekkoType] = []
        w: list[GekkoType] = []
        h: list[GekkoType] = []
        m = ModelModule(x, y, w, h, self.gekko, trunk_box, self.dw, self.dh, self.max_ratio, len(self.M))
        self.M.append(m)
        self.x.append(x)
        self.y.append(y)
        self.w.append(w)
        self.h.append(h)
        return len(self.M) - 1

    def add_rect(self, m: int, box: BoxType, direction: Cardinal) -> int:
        call = self.M[m].add_rect_west
        if direction is Cardinal.NORTH:
            call = self.M[m].add_rect_north
        elif direction is Cardinal.SOUTH:
            call = self.M[m].add_rect_south
        elif direction is Cardinal.EAST:
            call = self.M[m].add_rect_east
        # xv, yv, wv, hv =
        call(self.gekko, box)
        return len(self.M) - 1

    def fix(self,
            m: int,
            xl: OptionalList | None,
            yl: OptionalList | None,
            wl: OptionalList | None,
            hl: OptionalList | None):
        if optional_get(xl, 0) is not None:
            self.gekko.Equation(self.M[m].x[0] == optional_get(xl, 0))
        if optional_get(yl, 0) is not None:
            self.gekko.Equation(self.M[m].y[0] == optional_get(yl, 0))
        if optional_get(wl, 0) is not None:
            self.gekko.Equation(self.M[m].w[0] == optional_get(wl, 0))
        if optional_get(hl, 0) is not None:
            self.gekko.Equation(self.M[m].h[0] == optional_get(hl, 0))
        for i in range(1, self.M[m].c):
            xget = optional_get(xl, i)
            yget = optional_get(yl, i)
            wget = optional_get(wl, i)
            hget = optional_get(hl, i)
            if xget is GekkoType:
                self.gekko.Equation(self.M[m].x[i] == self.M[m].x[0] + xget)
            if yget is GekkoType:
                self.gekko.Equation(self.M[m].y[i] == self.M[m].y[0] + yget)
            if wget is GekkoType:
                self.gekko.Equation(self.M[m].w[i] == wget)
            if hget is GekkoType:
                self.gekko.Equation(self.M[m].h[i] == hget)

    def __init__(self,
                 ml: list[InputModule],
                 al: list[float],
                 xl: OptionalMatrix,
                 yl: OptionalMatrix,
                 wl: OptionalMatrix,
                 hl: OptionalMatrix,
                 die_width: float,
                 die_height: float,
                 hyper: Hypergraph,
                 max_ratio: float):
        assert len(ml) == len(al), "M and A need to have the same length!"

        self.M: list[ModelModule] = []
        self.x: list[list[GekkoType]] = []
        self.y: list[list[GekkoType]] = []
        self.w: list[list[GekkoType]] = []
        self.h: list[list[GekkoType]] = []
        self.dw: float = die_width
        self.dh: float = die_height
        self.max_ratio: float = max_ratio

        """Constructs the GEKKO object and initializes the model"""
        self.gekko = GEKKO(remote=False)

        # self.tau = self.gekko.Var(lb = 0, name="tau")
        # self.tau.value = [5]
        self.tau = 0.1 * min(die_width, die_height)

        # Variable definition
        for (trunk, Nb, Sb, Eb, Wb) in ml:
            m = self.define_module(trunk)
            for box_i in Nb:
                self.add_rect(m, box_i, Cardinal.NORTH)
            for box_i in Sb:
                self.add_rect(m, box_i, Cardinal.SOUTH)
            for box_i in Eb:
                self.add_rect(m, box_i, Cardinal.EAST)
            for box_i in Wb:
                self.add_rect(m, box_i, Cardinal.WEST)

        # Minimal area requirements
        for m in range(0, len(al)):
            self.gekko.Equation(self.M[m].area >= al[m])

        # No Intra-Module Intersection
        for m in range(0, len(al)):
            nid = self.M[m].N
            sid = self.M[m].S
            eid = self.M[m].E
            wid = self.M[m].W

            nid.sort(key=lambda z: value_of(self.M[m].x[z]))
            for i in range(0, len(nid) - 1):
                x, y = nid[i], nid[i + 1]
                self.gekko.Equation(self.M[m].y[x] + 0.5 * self.M[m].h[x] <= self.M[m].y[y] - 0.5 * self.M[m].h[y])

            sid.sort(key=lambda z: value_of(self.M[m].x[z]))
            for i in range(0, len(sid) - 1):
                x, y = sid[i], sid[i + 1]
                self.gekko.Equation(self.M[m].y[x] + 0.5 * self.M[m].h[x] <= self.M[m].y[y] - 0.5 * self.M[m].h[y])

            eid.sort(key=lambda z: value_of(self.M[m].y[z]))
            for i in range(0, len(eid) - 1):
                x, y = eid[i], eid[i + 1]
                self.gekko.Equation(self.M[m].y[x] + 0.5 * self.M[m].h[x] <= self.M[m].y[y] - 0.5 * self.M[m].h[y])

            wid.sort(key=lambda z: value_of(self.M[m].y[z]))
            for i in range(0, len(wid) - 1):
                x, y = wid[i], wid[i + 1]
                self.gekko.Equation(self.M[m].y[x] + 0.5 * self.M[m].h[x] <= self.M[m].y[y] - 0.5 * self.M[m].h[y])

        # No Inter-Module Intersection
        for m in range(0, len(al)):
            for n in range(m + 1, len(al)):
                for i in range(0, self.M[m].c):
                    for j in range(0, self.M[n].c):
                        t1 = (self.x[m][i] - self.x[n][j]) ** 2 - 0.25 * (self.w[m][i] + self.w[n][j]) ** 2
                        t2 = (self.y[m][i] - self.y[n][j]) ** 2 - 0.25 * (self.h[m][i] + self.h[n][j]) ** 2
                        self.gekko.Equation(smax(t1, t2, self.gekko.sqrt, self.tau) >= 0)

        # Fixed/Hard modules
        for m in range(0, len(al)):
            self.fix(m, optional_get(xl, m), optional_get(yl, m), optional_get(wl, m), optional_get(hl, m))

        # Objective function
        obj = 0
        for (weight, Set) in hyper:
            centroid_x: Any = 0.0
            centroid_y: Any = 0.0
            for i in Set:
                centroid_x += self.M[i].xsum / self.M[i].area
                centroid_y += self.M[i].ysum / self.M[i].area
            centroid_x = 1.0 / len(Set) * centroid_x
            centroid_y = 1.0 / len(Set) * centroid_y
            for i in Set:
                module = self.M[i]
                obj += weight * weight * ((module.xsum / module.area - centroid_x) ** 2 +
                                          (module.ysum / module.area - centroid_y) ** 2)
        self.gekko.Obj(obj + self.tau)

    def interactive_draw(self, canvas_width=500, canvas_height=500):
        canvas = Canvas(width=canvas_width, height=canvas_height)
        canvas.clear(col="#000000")
        canvas.setcoords(-1, -1, self.dw+1, self.dh+1)

        for i in range(0, len(self.M)):
            m = self.M[i]
            hue = i / len(self.M)
            for j in range(0, len(m.x)):
                a = m.x[j][0] - 0.5 * m.w[j][0]
                b = m.y[j][0] - 0.5 * m.h[j][0]
                c = m.x[j][0] + 0.5 * m.w[j][0]
                d = m.y[j][0] + 0.5 * m.h[j][0]

                canvas.drawbox(((a, b), (c, d)), col=hsv_to_str(hue) + "90")
        canvas.show()

    def solve(self):
        self.gekko.solve(disp=True)


def compute_options(options) -> tuple[list[InputModule],
                                      list[float],
                                      OptionalMatrix,
                                      OptionalMatrix,
                                      OptionalMatrix,
                                      OptionalMatrix,
                                      float,
                                      float,
                                      Hypergraph,
                                      float]:
    b1: InputModule = ((3, 4, 3, 4), [], [(2.5, 1.5, 2, 1)], [], [(1, 5.5, 1, 1), (1, 4.5, 1, 1)])
    b2: InputModule = ((2, 2, 4, 3), [], [], [], [])

    ml: list[InputModule] = [b1, b2]
    al: list[float] = [16.0, 12.0]
    xl: OptionalMatrix = {1: {0: 2.0}}
    yl: OptionalMatrix = {1: {0: 2.0}}
    wl: OptionalMatrix = {1: {0: 4.0}}
    hl: OptionalMatrix = {1: {0: 3.0}}
    die_width: float = 7.0
    die_height: float = 7.0
    hyper: Hypergraph = [(1, [0, 1])]
    max_ratio: float = options['max_ratio']
    return ml, al, xl, yl, wl, hl, die_width, die_height, hyper, max_ratio


def main(prog: str | None = None, args: list[str] | None = None) -> int:
    """
    Main function.
    """
    options = parse_options(prog, args)
    ml, al, xl, yl, wl, hl, die_width, die_height, hyper, max_ratio = compute_options(options)
    m = Model(ml, al, xl, yl, wl, hl, die_width, die_height, hyper, max_ratio)
    m.interactive_draw()
    m.solve()
    m.interactive_draw()
    return 0


if __name__ == "__main__":
    main()